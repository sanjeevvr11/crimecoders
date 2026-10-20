"""Combine indicator, network and (Phase 2) anomaly scores into a 0-100 risk score."""
from __future__ import annotations

import pandas as pd

from app import config


def risk_scores(accounts: pd.DataFrame, indicator: pd.DataFrame, network: pd.DataFrame,
                anomaly: pd.DataFrame | None = None) -> pd.DataFrame:
    df = accounts[["account_id"]].merge(indicator[["account_id", "indicator_score"]], on="account_id", how="left")
    df = df.merge(network[["account_id", "network_score", "ring_id"]], on="account_id", how="left")
    if anomaly is not None and "anomaly_score" in anomaly:
        df = df.merge(anomaly[["account_id", "anomaly_score"]], on="account_id", how="left")
    else:
        df["anomaly_score"] = 0.0  # slot reserved for Phase 2 (weight 0)
    df[["indicator_score", "network_score", "anomaly_score"]] = df[["indicator_score", "network_score", "anomaly_score"]].fillna(0.0)

    w = config.SCORE_WEIGHTS
    total_w = sum(w.values()) or 1.0
    df["risk_score"] = 100.0 * (
        w["indicator"] * df["indicator_score"] + w["network"] * df["network_score"] + w["anomaly"] * df["anomaly_score"]
    ) / total_w
    df["risk_score"] = df["risk_score"].clip(0, 100).round(1)
    df["tier"] = df["risk_score"].map(tier_for)
    df["rank"] = df["risk_score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank").reset_index(drop=True)


def tier_for(score: float) -> str:
    for cutoff, name in config.TIERS:
        if score >= cutoff:
            return name
    return config.TIERS[-1][1]
