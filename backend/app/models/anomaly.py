"""Isolation Forest on account-week windows.

Use case: flag weeks whose behaviour is unlike the bulk of weeks across all
time-reliable accounts (bursts, sudden pass-through, night activity), without
needing fraud labels.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

from app import config
from app.models.features import MODEL_FEATURES, model_matrix


@dataclass
class AnomalyModel:
    scaler: RobustScaler
    forest: IsolationForest
    train_scores: np.ndarray  # raw anomaly scores of the training windows (higher = more anomalous)
    threshold: float  # raw score above which a window is flagged
    baselines: pd.DataFrame | None = None  # per-account typical week used for the dev_* features

    def raw_scores(self, X: pd.DataFrame) -> np.ndarray:
        return -self.forest.score_samples(self.scaler.transform(X[MODEL_FEATURES]))

    def to_unit(self, raw: np.ndarray) -> np.ndarray:
        """Empirical percentile of each score among training windows (0-1)."""
        ref = np.sort(self.train_scores)
        return np.searchsorted(ref, raw, side="right") / len(ref)


def fit_anomaly_model(X: pd.DataFrame, seed: int | None = None, contamination: float | None = None) -> AnomalyModel:
    seed = config.MODEL_SEED if seed is None else seed
    contamination = config.IFOREST_CONTAMINATION if contamination is None else contamination
    scaler = RobustScaler().fit(X[MODEL_FEATURES])
    forest = IsolationForest(
        n_estimators=config.IFOREST_TREES, contamination=contamination, random_state=seed, n_jobs=1,
    ).fit(scaler.transform(X[MODEL_FEATURES]))
    train = -forest.score_samples(scaler.transform(X[MODEL_FEATURES]))
    threshold = float(np.quantile(train, 1 - contamination))
    return AnomalyModel(scaler, forest, train, threshold)


def score_windows(model: AnomalyModel, windows: pd.DataFrame) -> pd.DataFrame:
    X = model_matrix(windows, model.baselines)
    raw = model.raw_scores(X)
    out = windows[["account_id", "week_start"]].copy()
    pct = model.to_unit(raw)
    floor = config.ANOMALY_FLOOR_PCT
    out["anomaly_raw"] = raw
    out["anomaly_pct"] = pct  # percentile among training weeks
    out["anomaly_score"] = np.clip((pct - floor) / (1 - floor), 0, 1)
    out["is_flagged"] = raw > model.threshold
    return out


def account_anomaly(window_scores: pd.DataFrame, accounts: pd.DataFrame, top_k: int | None = None) -> pd.DataFrame:
    """Per account: mean of its top-k window scores and number of flagged weeks.
    Accounts without windows (no reliable timestamps) get None, not 0."""
    top_k = top_k or config.ACCOUNT_TOP_WINDOWS
    g = window_scores.groupby("account_id")
    agg = pd.DataFrame({
        "anomaly_score": g["anomaly_score"].apply(lambda s: float(s.nlargest(top_k).mean())),
        "flagged_weeks": g["is_flagged"].sum().astype(int),
        "n_weeks": g.size().astype(int),
    })
    out = accounts[["account_id"]].merge(agg, left_on="account_id", right_index=True, how="left")
    out["flagged_weeks"] = out["flagged_weeks"].astype("Int64")
    out["n_weeks"] = out["n_weeks"].astype("Int64")
    return out
