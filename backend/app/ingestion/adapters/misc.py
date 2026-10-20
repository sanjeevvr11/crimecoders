"""Layout E: one-off formats (file 1 customer ledger, file 3 26-column extract)."""
from __future__ import annotations

import pandas as pd

from app.ingestion import normalizer
from app.ingestion.adapters.base import BaseAdapter, col_or_na, find_column


class CustomerLedgerAdapter(BaseAdapter):
    """File 1: CUSTOMER ID, CUSTOMER NAME, ACCOUNT NO, TRANSACTION DATE, NARRATION, DEBIT/CREDIT AMOUNT."""

    name = "misc_ledger"
    time_reliable = False

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return all(find_column(df, c) is not None for c in ("CUSTOMER NAME", "NARRATION", "DEBIT AMOUNT", "CREDIT AMOUNT"))

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        direction, amount = normalizer.split_debit_credit(df[find_column(df, "DEBIT AMOUNT")], df[find_column(df, "CREDIT AMOUNT")])
        return pd.DataFrame(
            {
                "direction": direction,
                "amount": amount,
                "raw_narration": normalizer.raw_text(col_or_na(df, "NARRATION")),
                "raw_remarks": pd.NA,
                "raw_date": normalizer.raw_text(col_or_na(df, "TRANSACTION DATE")),
                "txn_ts": pd.NaT,
                "holder_name": col_or_na(df, "CUSTOMER NAME"),
                "account_number": col_or_na(df, "ACCOUNT NO"),
            },
            index=df.index,
        )


class WideExtractAdapter(BaseAdapter):
    """File 3: 26 columns with 'Dr Cr' + AMOUNT. PAN DETAILS is deliberately dropped."""

    name = "misc_wide"
    time_reliable = False

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return all(find_column(df, c) is not None for c in ("Dr Cr", "AMOUNT", "TXN PARTICULARS"))

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "direction": normalizer.direction_from_flag(df[find_column(df, "Dr Cr")]),
                "amount": normalizer.to_amount(df[find_column(df, "AMOUNT")]),
                "raw_narration": normalizer.raw_text(col_or_na(df, "TXN PARTICULARS")),
                "raw_remarks": pd.NA,
                "raw_date": normalizer.raw_text(col_or_na(df, "TXN DATE")),
                "txn_ts": pd.NaT,
                "holder_name": col_or_na(df, "Account Name"),
                "account_number": col_or_na(df, "Account No"),
            },
            index=df.index,
        )
