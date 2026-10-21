from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app import config
from app.api.deps import get_store, records
from app.api.txns import sort_by_date, txn_rows
from app.graph.money_trail import money_trail
from app.masking import mask, mask_digits, node_label, node_ref
from app.models.summary import account_ml_summary
from app.schemas.api import AccountDetail, AccountListItem, Timeline, Trail
from app.scoring.reasons import top_reasons

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


@router.get("/{account_id}", response_model=AccountDetail)
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


@router.get("/{account_id}/timeline", response_model=Timeline)
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
