"""Canonical transaction schema shared by every adapter."""
from __future__ import annotations

import pandas as pd

TRANSACTION_COLUMNS: dict[str, str] = {
    "txn_uid": "string",
    "account_id": "string",
    "source_file": "string",
    "source_sheet": "string",
    "row_idx": "int64",
    "txn_ts": "datetime64[ns]",
    "time_reliable": "bool",
    "direction": "string",  # CR / DR
    "amount": "float64",
    "channel": "string",
    "counterparty_key": "string",
    "counterparty_type": "string",  # upi / account / ifsc / name / none
    "counterparty_bank": "string",
    "raw_narration": "string",
    "raw_date": "string",
}

ACCOUNT_COLUMNS = [
    "account_id",
    "source_file",
    "source_sheet",
    "layout",
    "holder_name",
    "account_number",  # only when constant within the statement, else null
    "time_reliable",
    "n_rows",
]

CHANNELS = ("UPI", "IMPS", "NEFT", "RTGS", "ATM", "CASH", "CLG", "CHQ", "ACH", "CHARGES", "OTHER", "UNKNOWN")


def conform(df: pd.DataFrame) -> pd.DataFrame:
    """Return `df` with exactly the canonical columns, in order, with canonical dtypes."""
    out = pd.DataFrame(index=df.index)
    for col, dtype in TRANSACTION_COLUMNS.items():
        series = df[col] if col in df else pd.Series(pd.NA, index=df.index)
        if dtype.startswith("datetime"):
            series = pd.to_datetime(series, errors="coerce")
        elif dtype == "bool":
            series = series.fillna(False).astype(bool)
        else:
            series = series.astype(dtype)
        out[col] = series
    return out.reset_index(drop=True)


def validate(df: pd.DataFrame) -> None:
    missing = set(TRANSACTION_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing canonical columns: {sorted(missing)}")
    bad_dir = ~df["direction"].isin(["CR", "DR"])
    if bad_dir.any():
        raise ValueError(f"{int(bad_dir.sum())} rows with invalid direction")
    if (df["amount"] < 0).any():
        raise ValueError("negative amounts after normalisation")
    if df["txn_uid"].duplicated().any():
        raise ValueError("duplicate txn_uid")
