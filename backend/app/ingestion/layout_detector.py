"""Pick the adapter for a sheet from its headers and content."""
from __future__ import annotations

import pandas as pd

from app.ingestion.adapters.base import BaseAdapter
from app.ingestion.adapters.crn_statement import CrnStatementAdapter
from app.ingestion.adapters.debit_credit import DebitCreditAdapter
from app.ingestion.adapters.icore_full import IcoreFullAdapter
from app.ingestion.adapters.icore_short import IcoreShortAdapter
from app.ingestion.adapters.misc import CustomerLedgerAdapter, WideExtractAdapter

# order matters: more specific layouts first
ADAPTERS: list[type[BaseAdapter]] = [
    IcoreFullAdapter,
    IcoreShortAdapter,
    DebitCreditAdapter,
    WideExtractAdapter,
    CustomerLedgerAdapter,
    CrnStatementAdapter,
]


class UnknownLayoutError(ValueError):
    pass


def detect_layout(df: pd.DataFrame) -> type[BaseAdapter]:
    for adapter in ADAPTERS:
        if adapter.matches(df):
            return adapter
    raise UnknownLayoutError(f"no adapter matches columns {list(df.columns)}")
