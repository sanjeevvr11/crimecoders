"""Threshold risk scores into alerts and a ranked lead list."""
from __future__ import annotations

import pandas as pd

from app import config


def lead_list(scores: pd.DataFrame, reasons: pd.DataFrame, accounts: pd.DataFrame,
              anomaly: pd.DataFrame | None = None, roles: pd.DataFrame | None = None) -> pd.DataFrame:
    top = reasons.loc[reasons["rank"] == 1].set_index("account_id")["text"]
    leads = scores.merge(accounts[["account_id", "layout", "time_reliable", "n_rows"]], on="account_id", how="left")
    if anomaly is not None:
        leads = leads.merge(anomaly[["account_id", "flagged_weeks"]], on="account_id", how="left")
    if roles is not None:
        leads = leads.merge(roles[["account_id", "role"]], on="account_id", how="left")
    leads["top_reason"] = leads["account_id"].map(top)
    leads["is_alert"] = leads["risk_score"] >= config.ALERT_THRESHOLD
    return leads.sort_values(["risk_score", "account_id"], ascending=[False, True]).reset_index(drop=True)


def alerts(leads: pd.DataFrame, threshold: float | None = None) -> pd.DataFrame:
    threshold = config.ALERT_THRESHOLD if threshold is None else threshold
    out = leads.loc[leads["risk_score"] >= threshold].copy()
    out.insert(0, "alert_id", [f"ALR-{i + 1:03d}" for i in range(len(out))])
    return out.reset_index(drop=True)
