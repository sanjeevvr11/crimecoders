from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from app import config
from app.api.deps import get_store, records
from app.graph.money_trail import money_trail
from app.masking import mask, mask_text, node_label, node_ref
from app.scoring.reasons import top_reasons

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _cp(key: object, subjects: set[str]) -> dict | None:
    if not isinstance(key, str):
        return None
    is_subj = key in subjects
    return {"ref": node_ref(key, is_subj), "label": node_label(key, is_subj)}


@router.get("")
def list_accounts() -> list[dict]:
    s = get_store()
    acc = s.table("accounts").merge(s.table("scores")[["account_id", "risk_score", "tier", "rank"]], on="account_id", how="left")
    acc["holder_name"] = acc["holder_name"].map(mask)
    acc["account_number"] = acc["account_number"].map(mask)
    return records(acc.sort_values("rank"))


@router.get("/{account_id}")
def account_detail(account_id: str) -> dict:
    s = get_store()
    s.require_account(account_id)
    acc = s.table("accounts").set_index("account_id").loc[account_id]
    feats = s.table("account_features").set_index("account_id").loc[[account_id]]
    score = s.table("scores").set_index("account_id").loc[[account_id]]
    net = s.table("network_scores").set_index("account_id").loc[[account_id]]
    ind = s.table("indicators")
    matches = s.table("complaint_matches")
    return {
        "account_id": account_id,
        "holder_name": mask(acc["holder_name"]),
        "account_number": mask(acc["account_number"]),
        "source_file": acc["source_file"],
        "source_sheet": acc["source_sheet"],
        "layout": acc["layout"],
        "time_reliable": bool(acc["time_reliable"]),
        "n_rows": int(acc["n_rows"]),
        "score": records(score.reset_index())[0],
        "reasons": top_reasons(account_id, ind, s.table("network_scores")),
        "indicators": records(ind.loc[ind["account_id"] == account_id].drop(columns="account_id")),
        "features": records(feats.reset_index())[0],
        "network": records(net.reset_index())[0],
        "complaint_matches": int((matches["account_id"] == account_id).sum()),
    }


@router.get("/{account_id}/timeline")
def account_timeline(
    account_id: str,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    direction: Literal["CR", "DR"] | None = None,
) -> dict:
    s = get_store()
    s.require_account(account_id)
    tx = s.table("transactions")
    t = tx.loc[tx["account_id"] == account_id]
    if direction:
        t = t.loc[t["direction"] == direction]
    t = t.sort_values(["txn_ts", "row_idx"], na_position="last")
    page = t.iloc[offset: offset + limit]
    rows = []
    for r in page.itertuples(index=False):
        rows.append({
            "txn_uid": r.txn_uid,
            "txn_ts": None if pd.isna(r.txn_ts) else pd.Timestamp(r.txn_ts).isoformat(),
            "direction": r.direction,
            "amount": float(r.amount),
            "channel": r.channel,
            "counterparty": _cp(r.counterparty_key, s.subject_ids),
            "counterparty_type": r.counterparty_type,
            "narration": mask_text(r.raw_narration),
            "raw_date": None if pd.isna(r.raw_date) else str(r.raw_date),
        })
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
    return {"account_id": account_id, "total": int(len(t)), "offset": offset, "limit": limit,
            "time_reliable": bool(t["time_reliable"].any()) if len(t) else False, "transactions": rows, "daily": daily}


@router.get("/{account_id}/trail")
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
