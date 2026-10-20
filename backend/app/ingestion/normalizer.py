"""Value-level normalisation helpers used by the adapters."""
from __future__ import annotations

import numpy as np
import pandas as pd

ICORE_TS_FORMAT = "%d%b%Y:%H:%M:%S"  # 17DEC2020:09:48:07


def to_amount(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.replace(",", "", regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce").fillna(0.0).abs()


def parse_icore_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("string").str.strip().str.upper(), format=ICORE_TS_FORMAT, errors="coerce")


def raw_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()


def split_debit_credit(debit: pd.Series, credit: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Two amount columns -> (direction, amount). Credit wins when both are set."""
    dr = to_amount(debit)
    cr = to_amount(credit)
    direction = pd.Series(np.where(cr > 0, "CR", np.where(dr > 0, "DR", pd.NA)), index=debit.index, dtype="string")
    amount = pd.Series(np.where(cr > 0, cr, dr), index=debit.index, dtype="float64")
    return direction, amount


def direction_from_flag(flag: pd.Series) -> pd.Series:
    f = flag.astype("string").str.strip().str.upper().str[:1]
    return f.map({"C": "CR", "D": "DR"}).astype("string")


def is_blank_row(df: pd.DataFrame) -> pd.Series:
    return df.astype("string").apply(lambda c: c.str.strip().fillna("")).eq("").all(axis=1)
