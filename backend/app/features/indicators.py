"""Turn raw features into 0-1 rule sub-scores with plain-English reasons."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app import config


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


REASON_TEMPLATES = {
    "pass_through_ratio": lambda f: f"{_pct(min(f['pass_through_ratio'], 9.99))} of credited value was debited out again (pass-through)",
    "fan_in": lambda f: f"Received money from {int(f['fan_in'])} distinct counterparties",
    "fan_out": lambda f: f"Sent money to {int(f['fan_out'])} distinct counterparties",
    "small_in_large_out": lambda f: (
        f"Typical debit (₹{f['median_dr_amount']:,.0f}) is {f['small_in_large_out']:.1f}x the typical credit (₹{f['median_cr_amount']:,.0f})"
    ),
    "round_amount_share": lambda f: f"{_pct(f['round_amount_share'])} of transactions are round amounts (multiples of ₹500/₹1000)",
    "upi_share": lambda f: f"{_pct(f['upi_share'])} of transactions are UPI",
    "fast_outflow_share": lambda f: f"{_pct(f['fast_outflow_share'])} of inflow left within {config.FAST_OUTFLOW_HOURS:g} hours",
    "median_dwell_hours": lambda f: f"Median time from credit to next debit is {f['median_dwell_hours']:.1f} hours",
    "burst_hours": lambda f: f"{int(f['burst_hours'])} hours with more than {config.BURST_TXNS_PER_HOUR} transactions (bursts)",
    "night_share": lambda f: f"{_pct(f['night_share'])} of transactions happen between 00:00 and 05:00",
    "txns_per_active_day": lambda f: f"{f['txns_per_active_day']:.1f} transactions per active day over {int(f['active_days'])} days",
}


def ramp(value: float, lo: float, hi: float) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return np.nan
    if lo == hi:
        return float(value >= hi)
    s = (value - lo) / (hi - lo)
    return float(min(1.0, max(0.0, s)))


def indicator_table(features: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per (account, indicator) with value, sub-score, weight, reason."""
    rows = []
    for _, f in features.iterrows():
        for name, spec in config.INDICATORS.items():
            value = f.get(name, np.nan)
            sub = ramp(value, spec["lo"], spec["hi"])
            if isinstance(sub, float) and math.isnan(sub):
                continue  # indicator not applicable (e.g. no timestamps)
            reason = REASON_TEMPLATES[name](f) if sub >= config.REASON_MIN_SUBSCORE else None
            rows.append({
                "account_id": f["account_id"],
                "indicator": name,
                "value": float(value),
                "subscore": sub,
                "weight": float(spec["weight"]),
                "reason": reason,
            })
    return pd.DataFrame(rows, columns=["account_id", "indicator", "value", "subscore", "weight", "reason"])


def indicator_scores(ind: pd.DataFrame) -> pd.DataFrame:
    """Weighted mean of available sub-scores per account (0-1)."""
    if ind.empty:
        return pd.DataFrame(columns=["account_id", "indicator_score", "n_indicators"])
    w = ind.assign(ws=ind["subscore"] * ind["weight"])
    g = w.groupby("account_id").agg(ws=("ws", "sum"), w=("weight", "sum"), n_indicators=("indicator", "size"))
    g["indicator_score"] = g["ws"] / g["w"]
    return g.reset_index()[["account_id", "indicator_score", "n_indicators"]]
