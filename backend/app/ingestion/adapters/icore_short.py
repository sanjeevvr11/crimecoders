"""Layout C: ICORE short statements. pstd_dt is the (sorted) event timestamp."""
from __future__ import annotations

import pandas as pd

from app.ingestion import normalizer
from app.ingestion.adapters.base import BaseAdapter, col_or_na, find_column


class IcoreShortAdapter(BaseAdapter):
    name = "icore_short"
    time_reliable = True

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return (
            all(find_column(df, c) is not None for c in ("Ac_No", "Dr_Amt", "Cr_Amt", "pstd_dt"))
            and find_column(df, "Init_SOL") is None
        )

    def extract(self, df: pd.DataFrame) -> pd.DataFrame:
        direction, amount = normalizer.split_debit_credit(df[find_column(df, "Dr_Amt")], df[find_column(df, "Cr_Amt")])
        return pd.DataFrame(
            {
                "direction": direction,
                "amount": amount,
                "raw_narration": normalizer.raw_text(col_or_na(df, "Narration")),
                "raw_remarks": normalizer.raw_text(col_or_na(df, "Rmks")),
                # Tran_Date is scrambled (sometimes an Excel serial): raw only
                "raw_date": normalizer.raw_text(col_or_na(df, "Tran_Date")),
                "txn_ts": normalizer.parse_icore_ts(df[find_column(df, "pstd_dt")]),
                "holder_name": col_or_na(df, "AC_Name"),
                "account_number": col_or_na(df, "Ac_No"),
            },
            index=df.index,
        )
