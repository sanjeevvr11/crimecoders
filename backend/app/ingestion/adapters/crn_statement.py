"""Layout A: CRN account statements (files 2, 4, 5).

Several headers are randomised person names, so the CRN and D/C columns are
found by position and content rather than by header.
"""
from __future__ import annotations

import pandas as pd

from app.ingestion import normalizer
from app.ingestion.adapters.base import BaseAdapter, col_or_na, find_column


def find_direction_column(df: pd.DataFrame) -> str | None:
    best = None
    for c in df.columns:
        vals = df[c].dropna().astype(str).str.strip().str.upper()
        if len(vals) == 0:
            continue
        share = vals.isin(["C", "D", "CR", "DR"]).mean()
        if share > 0.95 and (best is None or share > best[1]):
            best = (c, share)
    return best[0] if best else None


class CrnStatementAdapter(BaseAdapter):
    name = "crn_statement"
    time_reliable = False  # all date columns are shuffled

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return (
            find_column(df, "TXN PARTICULARS") is not None
            and find_column(df, "AMOUNT") is not None
            and find_column(df, "Dr Cr") is None
            and find_direction_column(df) is not None
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        dir_col = find_direction_column(df)
        cols = list(df.columns)
        amount_col = find_column(df, "AMOUNT") or cols[cols.index(dir_col) + 1]
        return pd.DataFrame(
            {
                "direction": normalizer.direction_from_flag(df[dir_col]),
                "amount": normalizer.to_amount(df[amount_col]),
                "raw_narration": normalizer.raw_text(col_or_na(df, "TXN PARTICULARS")),
                "raw_remarks": normalizer.raw_text(col_or_na(df, "TXN REMARKS")),
                "raw_date": normalizer.raw_text(col_or_na(df, "TXN DATE")),
                "txn_ts": pd.NaT,
                "holder_name": col_or_na(df, "Account Name"),
                "account_number": col_or_na(df, "Account No"),
            },
            index=df.index,
        )
