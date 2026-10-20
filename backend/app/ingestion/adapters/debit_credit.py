"""Layout B: separate debit / credit columns (file 6)."""
from __future__ import annotations

import pandas as pd

from app.ingestion import normalizer
from app.ingestion.adapters.base import BaseAdapter, col_or_na, find_column


class DebitCreditAdapter(BaseAdapter):
    name = "debit_credit"
    time_reliable = False

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return all(find_column(df, c) is not None for c in ("Customer_Name", "Debit_amount", "Credit_Amount", "Narration"))

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        direction, amount = normalizer.split_debit_credit(df[find_column(df, "Debit_amount")], df[find_column(df, "Credit_Amount")])
        return pd.DataFrame(
            {
                "direction": direction,
                "amount": amount,
                "raw_narration": normalizer.raw_text(col_or_na(df, "Narration")),
                "raw_remarks": pd.NA,
                "raw_date": normalizer.raw_text(col_or_na(df, "Date_of_transaction")),
                "txn_ts": pd.NaT,
                "holder_name": col_or_na(df, "Customer_Name"),
                "account_number": col_or_na(df, "Account_Number"),
            },
            index=df.index,
        )
