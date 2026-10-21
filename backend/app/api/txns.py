"""Transaction rows as the API returns them: date sort and masked serialisation."""
from __future__ import annotations

import pandas as pd

from app.masking import mask_text, node_label, node_ref


def sort_time(t: pd.DataFrame) -> pd.Series:
    """txn_ts (ICORE pstd_dt) where reliable, else the raw date. Raw dates are shuffled in SOA1-6,
    so that order is by date only, not the real order of events."""
    raw = t["raw_date"].astype("string")
    parsed = pd.to_datetime(raw, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    parsed = parsed.fillna(pd.to_datetime(raw, format="%d-%m-%Y", errors="coerce"))
    return t["txn_ts"].fillna(parsed)


def sort_by_date(t: pd.DataFrame, order: str = "asc") -> pd.DataFrame:
    """Every row sorted by date and time (ties keep statement order); undated rows last."""
    return t.assign(_sort_ts=sort_time(t)).sort_values(["_sort_ts", "account_id", "row_idx"], ascending=order == "asc", na_position="last")


def counterparty(key: object, subjects: set[str]) -> dict | None:
    if not isinstance(key, str):
        return None
    is_subj = key in subjects
    return {"ref": node_ref(key, is_subj), "label": node_label(key, is_subj)}


def txn_rows(page: pd.DataFrame, subjects: set[str], with_account: bool = False) -> list[dict]:
    rows = []
    for r in page.itertuples(index=False):
        row = {
            "txn_uid": r.txn_uid,
            "txn_ts": None if pd.isna(r.txn_ts) else pd.Timestamp(r.txn_ts).isoformat(),
            "direction": r.direction,
            "amount": float(r.amount),
            "channel": r.channel,
            "counterparty": counterparty(r.counterparty_key, subjects),
            "counterparty_type": r.counterparty_type,
            "narration": mask_text(r.raw_narration),
            "raw_date": None if pd.isna(r.raw_date) else str(r.raw_date),
        }
        if with_account:
            row["account_id"] = r.account_id
        rows.append(row)
    return rows
