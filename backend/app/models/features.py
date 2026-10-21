"""Model matrix built from account-week window features.

Raw window features are heavy-tailed (one week has 20k transactions), so
counts and amounts are log-scaled and ratios clipped before robust scaling.

Two kinds of feature are used:
* level features describe the week itself (HDBSCAN roles use these) (volume, mix, timing, round amounts);
  pattern counts (fast credit->debit pairs, night, round, small credits) are
  counts rather than shares so a burst is not diluted by a busy week;
* self-baseline features compare the week with the same account's typical week
  (robust z-score against that account's median/IQR), because accounts differ
  by orders of magnitude and a mule burst is a change *for that account*.

Distinct counterparties are deliberately left out: only the accounts with real
narrations (7, 8, 9) have counterparties at all, so the feature would separate
accounts by data availability rather than behaviour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_FEATURES = [
    "log_n_txns",
    "cr_count_share",
    "log_cr_amount",
    "log_dr_amount",
    "flow_imbalance",
    "log_max_txns_per_hour",
    "log_active_hours",
    "night_share",
    "round_amount_share",
    "small_credit_share",
    "fast_outflow_share",
    "log_median_dwell_hours",
    "log_n_fast_credits",
    "log_n_night",
    "log_n_round",
    "log_n_small_cr",
]
# compared with the account's own typical week
BASELINE_SOURCES = [
    "log_n_txns", "log_max_txns_per_hour", "log_n_fast_credits", "log_n_night", "log_n_round", "log_cr_amount", "log_n_small_cr",
]
BASELINE_FEATURES = [f"dev_{c}" for c in BASELINE_SOURCES]
RATIO_FEATURES = ["fast_outflow_share", "night_share", "round_amount_share", "small_credit_share", "log_median_dwell_hours"]
# Isolation Forest input. Chosen on the synthetic-injection test (see
# reports/model_evaluation.md): with all 23 features the forest spent its splits on
# raw size, so naturally huge weeks drowned out mule bursts (ROC-AUC 0.73 vs 0.78).
MODEL_FEATURES = BASELINE_FEATURES + RATIO_FEATURES

WEEK_HOURS = 168.0
MIN_IQR = 0.5  # floor for the baseline spread (log units) so sparse accounts don't explode


def level_matrix(windows: pd.DataFrame) -> pd.DataFrame:
    w = windows
    n = w["n_txns"].clip(lower=1)
    m = pd.DataFrame(index=w.index)
    m["log_n_txns"] = np.log1p(w["n_txns"])
    m["cr_count_share"] = w["n_cr"] / n
    m["log_cr_amount"] = np.log1p(w["cr_amount"])
    m["log_dr_amount"] = np.log1p(w["dr_amount"])
    # log(debits) - log(credits): 0 means everything credited went out again
    m["flow_imbalance"] = (np.log1p(w["dr_amount"]) - np.log1p(w["cr_amount"])).clip(-5, 5)
    m["log_max_txns_per_hour"] = np.log1p(w["max_txns_per_hour"])
    m["log_active_hours"] = np.log1p(w["active_hours"])
    m["night_share"] = w["night_share"]
    m["round_amount_share"] = w["round_amount_share"]
    m["small_credit_share"] = w["small_credit_share"].fillna(0.0)
    m["fast_outflow_share"] = w["fast_outflow_share"].fillna(0.0)
    # no credit->debit pair inside the week counts as a full week of dwell
    m["log_median_dwell_hours"] = np.log1p(w["median_dwell_hours"].fillna(WEEK_HOURS).clip(upper=WEEK_HOURS))
    m["log_n_fast_credits"] = np.log1p(w["n_fast_credits"])
    m["log_n_night"] = np.log1p(w["n_night"])
    m["log_n_round"] = np.log1p(w["n_round"])
    m["log_n_small_cr"] = np.log1p(w["n_small_cr"])
    return m[LEVEL_FEATURES].astype(float)


def account_baselines(windows: pd.DataFrame) -> pd.DataFrame:
    """Per-account median and IQR of the baseline source features."""
    lv = level_matrix(windows)[BASELINE_SOURCES].assign(account_id=windows["account_id"].to_numpy())
    g = lv.groupby("account_id")
    med = g.median()
    iqr = (g.quantile(0.75) - g.quantile(0.25)).clip(lower=MIN_IQR)
    return pd.concat({"median": med, "iqr": iqr}, axis=1)


def model_matrix(windows: pd.DataFrame, baselines: pd.DataFrame | None = None) -> pd.DataFrame:
    """Full model matrix. `baselines` defaults to baselines computed from
    `windows` itself; a `baseline_account` column (used by the injection test)
    makes a copied week use its source account's baseline."""
    lv = level_matrix(windows)
    baselines = account_baselines(windows) if baselines is None else baselines
    key = windows["baseline_account"] if "baseline_account" in windows else windows["account_id"]
    med = baselines["median"].reindex(key.to_numpy())
    iqr = baselines["iqr"].reindex(key.to_numpy())
    for src in BASELINE_SOURCES:
        dev = (lv[src].to_numpy() - med[src].to_numpy()) / iqr[src].to_numpy()
        lv[f"dev_{src}"] = np.nan_to_num(dev, nan=0.0)
    return lv[LEVEL_FEATURES + BASELINE_FEATURES]
