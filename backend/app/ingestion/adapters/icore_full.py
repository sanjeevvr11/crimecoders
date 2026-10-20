"""Layout D: ICORE full statements (adds Init_SOL, Cust_ID, Tran_Type, ...)."""
from __future__ import annotations

import pandas as pd

from app.ingestion.adapters.base import find_column
from app.ingestion.adapters.icore_short import IcoreShortAdapter


class IcoreFullAdapter(IcoreShortAdapter):
    name = "icore_full"

    @classmethod
    def matches(cls, df: pd.DataFrame) -> bool:
        return all(find_column(df, c) is not None for c in ("Init_SOL", "Ac_No", "Dr_Amt", "Cr_Amt", "pstd_dt"))
