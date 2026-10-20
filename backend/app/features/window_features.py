"""Account-week window features for time-reliable (ICORE) accounts.

These are not scored in Phase 1; Phase 2's anomaly model trains on them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config

WINDOW_COLUMNS = [
    "account_id", "week_start", "n_txns", "n_cr", "n_dr", "cr_amount", "dr_amount",
    "pass_through_ratio", "unique_counterparties", "max_txns_per_hour", "night_share", "round_amount_share",
]


def window_features(txns: pd.DataFrame) -> pd.DataFrame:
    t = txns.loc[txns["time_reliable"] & txns["txn_ts"].notna()].copy()
    if t.empty:
        return pd.DataFrame(columns=WINDOW_COLUMNS)
    t["week_start"] = t["txn_ts"].dt.to_period("W-SUN").dt.start_time
    t["hour"] = t["txn_ts"].dt.floor("h")
    t["is_cr"] = t["direction"].eq("CR")
    t["cr_amt"] = np.where(t["is_cr"], t["amount"], 0.0)
    t["dr_amt"] = np.where(~t["is_cr"], t["amount"], 0.0)
    lo, hi = config.NIGHT_HOURS
    t["night"] = (t["txn_ts"].dt.hour >= lo) & (t["txn_ts"].dt.hour < hi)
    rnd = np.zeros(len(t), dtype=bool)
    for unit in config.ROUND_AMOUNT_UNITS:
        rnd |= (t["amount"].round(2) % unit == 0) & (t["amount"] > 0)
    t["round"] = rnd

    keys = ["account_id", "week_start"]
    agg = t.groupby(keys).agg(
        n_txns=("amount", "size"),
        n_cr=("is_cr", "sum"),
        cr_amount=("cr_amt", "sum"),
        dr_amount=("dr_amt", "sum"),
        unique_counterparties=("counterparty_key", "nunique"),
        night_share=("night", "mean"),
        round_amount_share=("round", "mean"),
    )
    agg["n_dr"] = agg["n_txns"] - agg["n_cr"]
    agg["pass_through_ratio"] = np.where(agg["cr_amount"] > 0, agg["dr_amount"] / agg["cr_amount"].where(agg["cr_amount"] > 0), np.nan)
    agg["max_txns_per_hour"] = t.groupby(keys + ["hour"]).size().groupby(level=[0, 1]).max()
    return agg.reset_index()[WINDOW_COLUMNS]
