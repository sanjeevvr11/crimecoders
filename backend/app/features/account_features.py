"""Per-account behavioural features (rule inputs, no ML).

Balances are randomised in the source data, so nothing here uses them.
Time features are only computed for accounts whose timestamps are reliable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config

CHANNEL_GROUPS = {
    "upi": ["UPI"],
    "imps": ["IMPS"],
    "neft_rtgs": ["NEFT", "RTGS"],
    "cash_atm": ["ATM", "CASH"],
    "cheque": ["CLG", "CHQ"],
    "unknown": ["UNKNOWN"],
}

MIN_NARRATION_COVERAGE = 0.2

TIME_FEATURES = ["median_dwell_hours", "fast_outflow_share", "burst_hours", "night_share", "active_days", "txns_per_active_day"]


def _round_share(amount: pd.Series) -> float:
    if len(amount) == 0:
        return np.nan
    a = amount.round(2)
    is_round = np.zeros(len(a), dtype=bool)
    for unit in config.ROUND_AMOUNT_UNITS:
        is_round |= (a % unit == 0) & (a > 0)
    return float(is_round.mean())


def _dwell(g: pd.DataFrame) -> tuple[float, float]:
    """Median hours from each credit to the next debit, and the share of credit
    value followed by a debit within FAST_OUTFLOW_HOURS."""
    g = g.dropna(subset=["txn_ts"])
    cr = g.loc[g["direction"] == "CR"]
    dr_ts = np.sort(g.loc[g["direction"] == "DR", "txn_ts"].to_numpy())
    if len(cr) == 0 or len(dr_ts) == 0:
        return np.nan, np.nan
    cr_ts = cr["txn_ts"].to_numpy()
    idx = np.searchsorted(dr_ts, cr_ts, side="left")
    has_next = idx < len(dr_ts)
    if not has_next.any():
        return np.nan, 0.0
    gaps_h = (dr_ts[idx[has_next]] - cr_ts[has_next]) / np.timedelta64(1, "h")
    amounts = cr["amount"].to_numpy()
    fast = np.zeros(len(cr), dtype=bool)
    fast[has_next] = gaps_h <= config.FAST_OUTFLOW_HOURS
    total = amounts.sum()
    return float(np.median(gaps_h)), float(amounts[fast].sum() / total) if total > 0 else np.nan


def _time_features(g: pd.DataFrame) -> dict:
    ts = g["txn_ts"].dropna()
    if ts.empty:
        return {k: np.nan for k in TIME_FEATURES}
    median_dwell, fast_share = _dwell(g)
    per_hour = ts.dt.floor("h").value_counts()
    lo, hi = config.NIGHT_HOURS
    active_days = int(ts.dt.normalize().nunique())
    return {
        "median_dwell_hours": median_dwell,
        "fast_outflow_share": fast_share,
        "burst_hours": int((per_hour > config.BURST_TXNS_PER_HOUR).sum()),
        "night_share": float(((ts.dt.hour >= lo) & (ts.dt.hour < hi)).mean()),
        "active_days": active_days,
        "txns_per_active_day": float(len(ts) / active_days) if active_days else np.nan,
    }


def account_features(txns: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for account_id, g in txns.groupby("account_id", sort=True):
        cr = g.loc[g["direction"] == "CR"]
        dr = g.loc[g["direction"] == "DR"]
        total_cr, total_dr = float(cr["amount"].sum()), float(dr["amount"].sum())
        med_cr = float(cr["amount"].median()) if len(cr) else np.nan
        med_dr = float(dr["amount"].median()) if len(dr) else np.nan
        time_reliable = bool(g["time_reliable"].any())
        row = {
            "account_id": account_id,
            "time_reliable": time_reliable,
            "n_txns": int(len(g)),
            "n_cr": int(len(cr)),
            "n_dr": int(len(dr)),
            "total_cr": total_cr,
            "total_dr": total_dr,
            "pass_through_ratio": total_dr / total_cr if total_cr > 0 else np.nan,
            "fan_in": int(cr["counterparty_key"].dropna().nunique()),
            "fan_out": int(dr["counterparty_key"].dropna().nunique()),
            "median_cr_amount": med_cr,
            "median_dr_amount": med_dr,
            "small_credit_share": float((cr["amount"] <= config.SMALL_CREDIT_MAX).mean()) if len(cr) else np.nan,
            "large_debit_share": float((dr["amount"] >= config.LARGE_DEBIT_MIN).mean()) if len(dr) else np.nan,
            # many small credits feeding fewer large debits
            "small_in_large_out": (med_dr / med_cr) if med_cr and med_cr > 0 and not np.isnan(med_dr) else np.nan,
            "round_amount_share": _round_share(g["amount"]),
            "narration_coverage": float((g["channel"] != "UNKNOWN").mean()),
        }
        for name, chans in CHANNEL_GROUPS.items():
            row[f"{name}_share"] = float(g["channel"].isin(chans).mean())
        if row["narration_coverage"] < MIN_NARRATION_COVERAGE:
            # narrations are opaque tokens: counterparties and channels are unknown, not zero
            for k in ["fan_in", "fan_out", *[f"{n}_share" for n in CHANNEL_GROUPS if n != "unknown"]]:
                row[k] = np.nan
        if time_reliable:
            row.update(_time_features(g))
        else:
            row.update({k: np.nan for k in TIME_FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)
