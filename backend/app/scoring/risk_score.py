"""Combine rule indicators, network and anomaly into a 0-100 risk score.

base  = 100 * (w_ind * indicator + w_net * network) / (w_ind + w_net)
risk  = base + ANOMALY_UPLIFT * anomaly * (100 - base)

The anomaly score only adds evidence (see config.ANOMALY_UPLIFT for why). It is
missing for accounts without reliable timestamps (SOA1-6); they keep their base
score, so missing is never treated as 0 risk or as a penalty. The Phase 1
rules-only score is kept alongside for comparison.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app import config


def base_weights() -> dict[str, float]:
    w = config.SCORE_WEIGHTS
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


def risk_scores(accounts: pd.DataFrame, indicator: pd.DataFrame, network: pd.DataFrame,
                anomaly: pd.DataFrame | None = None) -> pd.DataFrame:
    df = accounts[["account_id"]].merge(indicator[["account_id", "indicator_score"]], on="account_id", how="left")
    df = df.merge(network[["account_id", "network_score", "ring_id"]], on="account_id", how="left")
    if anomaly is not None and "anomaly_score" in anomaly:
        df = df.merge(anomaly[["account_id", "anomaly_score"]], on="account_id", how="left")
    else:
        df["anomaly_score"] = np.nan
    df[["indicator_score", "network_score"]] = df[["indicator_score", "network_score"]].fillna(0.0)

    w = base_weights()
    base = 100.0 * (w["indicator"] * df["indicator_score"] + w["network"] * df["network_score"])
    uplift = config.ANOMALY_UPLIFT * df["anomaly_score"].fillna(0.0) * (100.0 - base)
    df["base_score"] = base.round(1)
    df["anomaly_uplift"] = uplift.round(1)
    df["risk_score"] = (base + uplift).clip(0, 100).round(1)
    df["score_parts"] = np.where(df["anomaly_score"].notna(), "indicator,network,anomaly", "indicator,network")
    p1 = config.PHASE1_SCORE_WEIGHTS
    df["risk_score_phase1"] = (100.0 * (p1["indicator"] * df["indicator_score"] + p1["network"] * df["network_score"])
                               / sum(p1.values())).round(1)
    df["tier"] = df["risk_score"].map(tier_for)
    df["rank"] = df["risk_score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank").reset_index(drop=True)


def tier_for(score: float) -> str:
    for cutoff, name in config.TIERS:
        if score >= cutoff:
            return name
    return config.TIERS[-1][1]
