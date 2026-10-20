from fastapi import APIRouter, HTTPException

from app.api.deps import get_store, records
from app.masking import mask, node_label, node_ref

router = APIRouter(prefix="/api/complaints", tags=["complaints"])

PUBLIC_COLUMNS = ["complaint_id", "date", "victim", "reported_upi_or_account", "reported_type", "amount", "channel", "synthetic"]


@router.get("")
def list_complaints() -> list[dict]:
    s = get_store()
    c = s.table("complaints")[PUBLIC_COLUMNS].copy()
    c["reported_upi_or_account"] = c["reported_upi_or_account"].map(mask)
    m = s.table("complaint_matches")
    best = m.drop_duplicates("complaint_id").set_index("complaint_id")
    c["n_matches"] = c["complaint_id"].map(m.groupby("complaint_id").size()).fillna(0).astype(int)
    c["best_confidence"] = c["complaint_id"].map(best["confidence"])
    c["best_account_id"] = c["complaint_id"].map(best["account_id"])
    return records(c)


@router.get("/{complaint_id}/matches")
def complaint_matches(complaint_id: str) -> dict:
    s = get_store()
    c = s.table("complaints")
    row = c.loc[c["complaint_id"] == complaint_id, PUBLIC_COLUMNS]
    if row.empty:
        raise HTTPException(404, f"unknown complaint '{complaint_id}'")
    complaint = records(row)[0]
    complaint["reported_upi_or_account"] = mask(complaint["reported_upi_or_account"])
    m = s.table("complaint_matches")
    m = m.loc[m["complaint_id"] == complaint_id].copy()
    m["counterparty"] = [{"ref": node_ref(k, False), "label": node_label(k, False)} for k in m["counterparty_key"]]
    return {"complaint": complaint, "matches": records(m.drop(columns=["counterparty_key"]))}
