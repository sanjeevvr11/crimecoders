"""Account-week window features for time-reliable (ICORE) accounts.

Phase 2's Isolation Forest and HDBSCAN train on these.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config
from app.features.account_features import _dwell

WINDOW_COLUMNS = [
    "account_id", "week_start", "n_txns", "n_cr", "n_dr", "cr_amount", "dr_amount",
    "pass_through_ratio", "unique_counterparties", "max_txns_per_hour", "active_hours", "night_share",
    "round_amount_share", "small_credit_share", "fast_outflow_share", "median_dwell_hours",
    "n_night", "n_round", "n_small_cr", "n_fast_credits",
]


def _fast_credit_count(g: pd.DataFrame) -> int:
    """Credits followed by a debit within FAST_OUTFLOW_HOURS (a count, so a burst
    is not diluted by the rest of a busy week)."""
    cr_ts = np.sort(g.loc[g["is_cr"], "txn_ts"].to_numpy())
    dr_ts = np.sort(g.loc[~g["is_cr"], "txn_ts"].to_numpy())
    if len(cr_ts) == 0 or len(dr_ts) == 0:
        return 0
    idx = np.searchsorted(dr_ts, cr_ts, side="left")
    ok = idx < len(dr_ts)
    gaps = (dr_ts[idx[ok]] - cr_ts[ok]) / np.timedelta64(1, "h")
    return int((gaps <= config.FAST_OUTFLOW_HOURS).sum())


def window_features(txns: pd.DataFrame) -> pd.DataFrame:
    t = txns.loc[txns["time_reliable"] & txns["txn_ts"].notna()].copy()
    if t.empty:
        return pd.DataFrame(columns=WINDOW_COLUMNS)
    t["week_start"] = t["txn_ts"].dt.to_period("W-SUN").dt.start_time
    t["hour"] = t["txn_ts"].dt.floor("h")
    t["is_cr"] = t["direction"].eq("CR")
    t["cr_amt"] = np.where(t["is_cr"], t["amount"], 0.0)
    t["dr_amt"] = np.where(~t["is_cr"], t["amount"], 0.0)
    t["small_cr"] = t["is_cr"] & (t["amount"] <= config.SMALL_CREDIT_MAX)
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
        active_hours=("hour", "nunique"),
        night_share=("night", "mean"),
        round_amount_share=("round", "mean"),
        n_small_cr=("small_cr", "sum"),
        n_night=("night", "sum"),
        n_round=("round", "sum"),
    )
    agg["n_dr"] = agg["n_txns"] - agg["n_cr"]
    agg["pass_through_ratio"] = agg["dr_amount"] / agg["cr_amount"].where(agg["cr_amount"] > 0)
    agg["small_credit_share"] = agg["n_small_cr"] / agg["n_cr"].where(agg["n_cr"] > 0)
    agg["max_txns_per_hour"] = t.groupby(keys + ["hour"]).size().groupby(level=[0, 1]).max()
    dwell = {k: _dwell(g) for k, g in t.groupby(keys)}
    agg["median_dwell_hours"] = [dwell[k][0] for k in agg.index]
    agg["fast_outflow_share"] = [dwell[k][1] for k in agg.index]
    fast = {k: _fast_credit_count(g) for k, g in t.groupby(keys)}
    agg["n_fast_credits"] = [fast[k] for k in agg.index]
    return agg.reset_index()[WINDOW_COLUMNS]
