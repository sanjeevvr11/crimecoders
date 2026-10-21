"""SHAP explanations for the Isolation Forest.

Use case: say *why* a week was flagged, in the same plain-English style as the
rule indicators, so an investigator can check it against the statement.

TreeExplainer explains the forest's path length (higher = more normal), so a
feature pushes a window towards "anomalous" when its SHAP value is negative.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap

from app import config
from app.models.anomaly import AnomalyModel
from app.models.features import MODEL_FEATURES, model_matrix


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _amt(x: float) -> str:
    return f"₹{x:,.0f}"


# reason wording per model feature, filled from the raw window row
REASONS = {
    "log_n_txns": lambda w: f"{int(w['n_txns']):,} transactions in the week",
    "cr_count_share": lambda w: f"{int(w['n_cr']):,} credits vs {int(w['n_dr']):,} debits in the week",
    "log_cr_amount": lambda w: f"{_amt(w['cr_amount'])} credited in the week",
    "log_dr_amount": lambda w: f"{_amt(w['dr_amount'])} debited in the week",
    "flow_imbalance": lambda w: (
        f"{_pct(min(w['pass_through_ratio'], 9.99))} of the week's credits were debited out"
        if pd.notna(w["pass_through_ratio"]) else f"{_amt(w['dr_amount'])} debited with no credits that week"
    ),
    "log_max_txns_per_hour": lambda w: f"{int(w['max_txns_per_hour']):,} transactions in a single hour",
    "log_active_hours": lambda w: f"Active in {int(w['active_hours'])} different hours of the week",
    "night_share": lambda w: f"{_pct(w['night_share'])} of the week's transactions between 00:00 and 05:00",
    "round_amount_share": lambda w: f"{_pct(w['round_amount_share'])} of the week's amounts are round (multiples of ₹500/₹1000)",
    "small_credit_share": lambda w: f"{_pct(w['small_credit_share'] or 0)} of the week's credits are small (≤ ₹{config.SMALL_CREDIT_MAX:,.0f})",
    "fast_outflow_share": lambda w: f"{_pct(w['fast_outflow_share'] or 0)} of the week's inflow left within {config.FAST_OUTFLOW_HOURS:g} hours",
    "log_n_fast_credits": lambda w: f"{int(w['n_fast_credits']):,} credits were followed by a debit within {config.FAST_OUTFLOW_HOURS:g} hours",
    "log_n_night": lambda w: f"{int(w['n_night']):,} transactions between 00:00 and 05:00",
    "log_n_round": lambda w: f"{int(w['n_round']):,} round-amount transactions (multiples of ₹500/₹1000)",
    "log_n_small_cr": lambda w: f"{int(w['n_small_cr']):,} small credits (≤ ₹{config.SMALL_CREDIT_MAX:,.0f})",
    "dev_log_n_txns": lambda w: f"{int(w['n_txns']):,} transactions, far above this account's usual week",
    "dev_log_max_txns_per_hour": lambda w: f"{int(w['max_txns_per_hour']):,} transactions in one hour, unusual for this account",
    "dev_log_n_fast_credits": lambda w: f"{int(w['n_fast_credits']):,} quick credit→debit pass-throughs, unusual for this account",
    "dev_log_n_night": lambda w: f"{int(w['n_night']):,} night-time transactions, unusual for this account",
    "dev_log_n_round": lambda w: f"{int(w['n_round']):,} round-amount transactions, unusual for this account",
    "dev_log_n_small_cr": lambda w: f"{int(w['n_small_cr']):,} small credits (≤ ₹{config.SMALL_CREDIT_MAX:,.0f}), unusual for this account",
    "dev_log_cr_amount": lambda w: f"{_amt(w['cr_amount'])} credited, unusual for this account",
    "log_median_dwell_hours": lambda w: (
        f"Median {w['median_dwell_hours']:.1f} hours from credit to next debit"
        if pd.notna(w["median_dwell_hours"]) else "No credit was followed by a debit within the week"
    ),
}


def shap_contributions(model: AnomalyModel, windows: pd.DataFrame) -> pd.DataFrame:
    """Per-window anomaly contribution of each feature (positive = more anomalous)."""
    X = model_matrix(windows, model.baselines)[MODEL_FEATURES]
    sv = shap.TreeExplainer(model.forest).shap_values(model.scaler.transform(X))
    return pd.DataFrame(-np.asarray(sv), columns=MODEL_FEATURES, index=windows.index)


def explain_windows(model: AnomalyModel, windows: pd.DataFrame, window_scores: pd.DataFrame,
                    only_flagged: bool = True, top_n: int | None = None) -> pd.DataFrame:
    """Long table: (account_id, week_start, rank, feature, contribution, reason)."""
    top_n = top_n or config.SHAP_TOP_FEATURES
    sel = window_scores["is_flagged"] if only_flagged else pd.Series(True, index=window_scores.index)
    w = windows.loc[sel.to_numpy()]
    cols = ["account_id", "week_start", "rank", "feature", "contribution", "reason"]
    if w.empty:
        return pd.DataFrame(columns=cols)
    contrib = shap_contributions(model, w)
    rows = []
    for idx, row in w.iterrows():
        c = contrib.loc[idx]
        top = c[c > 0].nlargest(top_n)
        for rank, (feat, val) in enumerate(top.items(), start=1):
            rows.append({
                "account_id": row["account_id"], "week_start": row["week_start"], "rank": rank,
                "feature": feat, "contribution": float(val), "reason": REASONS[feat](row),
            })
    return pd.DataFrame(rows, columns=cols)
