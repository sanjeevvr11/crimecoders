import re
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app import config
from app.api.deps import get_store, records
from app.api.txns import sort_by_date, txn_rows
from app.graph.money_trail import money_trail
from app.graph.trail_view import trail_graph
from app.masking import mask, mask_digits, node_label, node_ref
from app.models.summary import account_ml_summary
from app.schemas.api import AccountDetail, AccountListItem, Timeline, Trail, TrailGraph
from app.scoring.reasons import top_reasons
from app.auth.deps import audited, require_role

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountListItem])
def list_accounts(
    tier: str | None = Query(None, description="HIGH, MEDIUM or LOW"),
    role: str | None = Query(None, description="collector, distributor, layering, normal-looking, unclassified"),
    ring_id: str | None = None,
    time_reliable: bool | None = None,
    q: str | None = Query(None, description="substring of the account id, e.g. SOA1"),
) -> list[dict]:
    s = get_store()
    acc = s.table("accounts").merge(s.table("scores")[["account_id", "risk_score", "tier", "rank", "ring_id"]], on="account_id", how="left")
    roles = s.optional_table("account_roles")
    acc["role"] = acc["account_id"].map(roles.set_index("account_id")["role"]) if roles is not None else None
    acc["holder_name"] = acc["holder_name"].map(mask)
    acc["account_number"] = acc["account_number"].map(mask)
    acc["source_sheet"] = acc["source_sheet"].map(mask_digits)  # ICORE sheet names embed an account number
    if tier:
        acc = acc.loc[acc["tier"] == tier.upper()]
    if role:
        acc = acc.loc[acc["role"] == role]
    if ring_id:
        acc = acc.loc[acc["ring_id"] == ring_id]
    if time_reliable is not None:
        acc = acc.loc[acc["time_reliable"] == time_reliable]
    if q:
        acc = acc.loc[acc["account_id"].str.contains(q, case=False, regex=False)]
    return records(acc.sort_values("rank"))


@router.get("/{account_id}", response_model=AccountDetail, dependencies=[audited("view_account", "account_id")])
def account_detail(account_id: str) -> dict:
    s = get_store()
    s.require_account(account_id)
    acc = s.table("accounts").set_index("account_id").loc[account_id]
    feats = s.table("account_features").set_index("account_id").loc[[account_id]]
    score = s.table("scores").set_index("account_id").loc[[account_id]]
    net = s.table("network_scores").set_index("account_id").loc[[account_id]]
    ind = s.table("indicators")
    matches = s.table("complaint_matches")
    ml = s.ml_context()
    return {
        "account_id": account_id,
        "holder_name": mask(acc["holder_name"]),
        "account_number": mask(acc["account_number"]),
        "source_file": acc["source_file"],
        "source_sheet": mask_digits(acc["source_sheet"]),
        "layout": acc["layout"],
        "time_reliable": bool(acc["time_reliable"]),
        "n_rows": int(acc["n_rows"]),
        "score": records(score.reset_index())[0],
        "reasons": top_reasons(account_id, ind, s.table("network_scores"), ml),
        **account_ml_summary(s, account_id),
        "indicators": records(ind.loc[ind["account_id"] == account_id].drop(columns="account_id")),
        "features": records(feats.reset_index())[0],
        "network": records(net.reset_index())[0],
        "complaint_matches": int((matches["account_id"] == account_id).sum()),
    }


@router.get("/{account_id}/timeline", response_model=Timeline,
            dependencies=[Depends(require_role("investigator")), audited("view_transactions", "account_id")])
def account_timeline(
    account_id: str,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    direction: Literal["CR", "DR"] | None = None,
    order: Literal["asc", "desc"] = Query("asc", description="by date and time across all rows: asc = oldest first, desc = newest first"),
) -> dict:
    s = get_store()
    s.require_account(account_id)
    tx = s.table("transactions")
    t = tx.loc[tx["account_id"] == account_id]
    if direction:
        t = t.loc[t["direction"] == direction]
    t = sort_by_date(t, order)
    rows = txn_rows(t.iloc[offset: offset + limit], s.subject_ids)
    daily = []
    tt = t.dropna(subset=["txn_ts"])
    if len(tt):
        d = tt.assign(day=tt["txn_ts"].dt.normalize()).pivot_table(index="day", columns="direction", values="amount", aggfunc=["sum", "count"], fill_value=0)
        for day, row in d.iterrows():
            daily.append({
                "date": day.date().isoformat(),
                "cr_amount": float(row.get(("sum", "CR"), 0)), "dr_amount": float(row.get(("sum", "DR"), 0)),
                "n_txns": int(row.get(("count", "CR"), 0) + row.get(("count", "DR"), 0)),
            })
    weeks = []
    ws = s.optional_table("window_scores")
    if ws is not None and len(ws):
        for w in ws.loc[ws["account_id"] == account_id].sort_values("week_start").itertuples(index=False):
            weeks.append({"week_start": pd.Timestamp(w.week_start).date().isoformat(), "anomaly_score": round(float(w.anomaly_score), 3),
                          "is_flagged": bool(w.is_flagged), "role": getattr(w, "role", None)})
    return {"account_id": account_id, "total": int(len(t)), "offset": offset, "limit": limit,
            "time_reliable": bool(t["time_reliable"].any()) if len(t) else False, "transactions": rows, "daily": daily,
            "weeks": weeks}


@router.get("/{account_id}/trail", response_model=Trail)
def account_trail(
    account_id: str,
    hops: int = Query(2, ge=1, le=config.TRAIL_MAX_HOPS),
    direction: Literal["forward", "backward", "both"] = "forward",
    max_paths: int = Query(50, ge=1, le=config.TRAIL_MAX_PATHS),
) -> dict:
    """Money trail from an account (or a counterparty ref such as CP-1a2b3c4d5e)."""
    s = get_store()
    start = s.resolve_node(account_id)
    if start not in s.graph:
        return {"start": account_id, "paths": []}
    try:
        paths = money_trail(s.graph, start, hops=hops, direction=direction, max_paths=max_paths)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    subj = s.subject_ids

    def ref(n: str) -> dict:
        return {"ref": node_ref(n, n in subj), "label": node_label(n, n in subj), "is_subject": n in subj}

    out = []
    for p in paths:
        out.append({
            "direction": p["direction"],
            "hops": p["hops"],
            "total_amount": round(p["total_amount"], 2),
            "nodes": [ref(n) for n in p["nodes"]],
            "edges": [{
                "source": node_ref(e["source"], e["source"] in subj), "target": node_ref(e["target"], e["target"] in subj),
                "amount": round(e["amount"], 2), "count": e["count"],
                "first_ts": e["first_ts"].isoformat() if e["first_ts"] is not None else None,
                "last_ts": e["last_ts"].isoformat() if e["last_ts"] is not None else None,
            } for e in p["edges"]],
        })
    return {"start": account_id, "hops": hops, "direction": direction, "paths": out}


# counterparty node id prefix -> kind shown in the trail view
NODE_KINDS = {"upi": "upi", "acct": "account", "ifsc": "ifsc", "name": "name"}


# parsed "bank" text is sometimes a payee name, so only 4-letter IFSC bank codes leave the API
BANK_CODE_RE = re.compile(r"[A-Z]{4}")


def _bank_code(bank) -> str | None:
    return bank if isinstance(bank, str) and BANK_CODE_RE.fullmatch(bank) else None


def _iso(ts) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).isoformat()


@router.get("/{account_id}/trail/graph", response_model=TrailGraph)
def account_trail_graph(
    account_id: str,
    hops: int = Query(3, ge=1, le=config.TRAIL_MAX_HOPS),
    direction: Literal["forward", "backward", "both"] = "both",
    max_paths: int = Query(120, ge=1, le=config.TRAIL_MAX_PATHS),
    shared: int = Query(12, ge=0, le=50, description="max common counterparties linking to other investigated accounts"),
) -> dict:
    """The money trail as one graph for the investigation view: nodes by hop distance, transfers, and chains."""
    s = get_store()
    s.require_account(account_id)
    subj = s.subject_ids
    acc = s.table("accounts").set_index("account_id")
    time_reliable = bool(acc.at[account_id, "time_reliable"])
    if account_id not in s.graph:
        tg = {"nodes": {account_id: {"level": 0, "amount_in": 0.0, "amount_out": 0.0}}, "edges": {}, "chains": []}
    else:
        tg = trail_graph(s.graph, account_id, subj, hops=hops, direction=direction, max_paths=max_paths, shared=shared)
    scores = s.table("scores").set_index("account_id")
    roles = s.optional_table("account_roles")
    role = roles.set_index("account_id")["role"].to_dict() if roles is not None else {}
    meta = s.table("nodes").set_index("node_id")

    def r(n: str) -> str:
        return node_ref(n, n in subj)

    nodes = []
    for n, d in tg["nodes"].items():
        is_subj = n in subj
        m = meta.loc[n] if n in meta.index else None
        kind = "subject" if is_subj else NODE_KINDS.get(n.partition(":")[0], "other")
        nodes.append({
            "ref": r(n), "label": node_label(n, is_subj), "is_subject": is_subj, "is_start": n == account_id,
            "kind": kind,
            "level": d["level"], "amount_in": round(d["amount_in"], 2), "amount_out": round(d["amount_out"], 2),
            "n_subject_links": int(m["n_subject_links"]) if m is not None else 0,
            "circular": bool(d.get("circular", False)),
            "bank": _bank_code(m["counterparty_bank"]) if m is not None and not is_subj else None,
            "risk_score": round(float(scores.at[n, "risk_score"]), 1) if is_subj else None,
            "tier": str(scores.at[n, "tier"]) if is_subj else None,
            "ring_id": (None if pd.isna(scores.at[n, "ring_id"]) else str(scores.at[n, "ring_id"])) if is_subj else None,
            "role": role.get(n) if is_subj else None,
        })
    edges = [{
        "source": r(u), "target": r(v), "amount": round(e["amount"], 2), "count": int(e["count"]),
        "first_ts": _iso(e["first_ts"]), "last_ts": _iso(e["last_ts"]), "hop": e["hop"], "direction": e["direction"], "link": e["link"],
    } for (u, v), e in tg["edges"].items()]
    chains = [{
        "direction": c["direction"], "kind": c["kind"], "hops": c["hops"], "amount": round(c["amount"], 2),
        "nodes": [r(n) for n in c["nodes"]], "first_ts": _iso(c["first_ts"]), "last_ts": _iso(c["last_ts"]),
    } for c in tg["chains"]]
    tn = tg["nodes"]
    ts = [t for (u, v), e in tg["edges"].items() for t in (e["first_ts"], e["last_ts"]) if t is not None]
    summary = {
        "n_nodes": len(nodes), "n_edges": len(edges), "n_chains": len(chains),
        "n_cross_account_chains": sum(c["kind"] == "cross-account" for c in chains),
        "n_shared_counterparties": len({c["nodes"][1] for c in chains if c["kind"] == "shared"}),
        "n_intermediaries": sum(1 for n, d in tn.items() if n != account_id and d["amount_in"] > 0 and d["amount_out"] > 0),
        "n_circular": sum(1 for d in tn.values() if d.get("circular")),
        "accounts_reached": sorted((n for n in tn if n in subj and n != account_id), key=lambda x: int(x[3:]) if x[3:].isdigit() else 0),
        "amount_in": round(tn[account_id]["amount_in"], 2), "amount_out": round(tn[account_id]["amount_out"], 2),
        "first_ts": _iso(min(ts)) if ts else None, "last_ts": _iso(max(ts)) if ts else None,
        "time_reliable": time_reliable,
    }
    nodes.sort(key=lambda n: (n["level"], -max(n["amount_in"], n["amount_out"])))
    return {"start": account_id, "hops": hops, "direction": direction, "summary": summary,
            "nodes": nodes, "edges": edges, "chains": chains}
