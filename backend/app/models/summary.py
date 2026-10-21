"""Per-account Phase 2 summary shared by the API and the evidence report."""
from __future__ import annotations

import pandas as pd


def account_ml_summary(s, account_id: str) -> dict:
    """Phase 2 fields: anomaly score, flagged weeks, role and SHAP reasons."""
    anom, roles = s.optional_table("account_anomaly"), s.optional_table("account_roles")
    out = {"anomaly_score": None, "flagged_weeks": None, "role": None, "role_source": None, "shap_reasons": []}
    if anom is not None:
        a = anom.loc[anom["account_id"] == account_id]
        if len(a) and pd.notna(a.iloc[0]["anomaly_score"]):
            out["anomaly_score"] = round(float(a.iloc[0]["anomaly_score"]), 3)
            out["flagged_weeks"] = int(a.iloc[0]["flagged_weeks"])
    if roles is not None:
        r = roles.loc[roles["account_id"] == account_id]
        if len(r):
            out["role"], out["role_source"] = r.iloc[0]["role"], r.iloc[0]["role_source"]
    ws, sr = s.optional_table("window_scores"), s.optional_table("shap_reasons")
    if ws is not None and sr is not None:
        flagged = ws.loc[(ws["account_id"] == account_id) & ws["is_flagged"]].sort_values("anomaly_score", ascending=False)
        for w in flagged.itertuples(index=False):
            rs = sr.loc[(sr["account_id"] == account_id) & (sr["week_start"] == w.week_start)].sort_values("rank")
            out["shap_reasons"].append({
                "week_start": pd.Timestamp(w.week_start).date().isoformat(),
                "anomaly_score": round(float(w.anomaly_score), 3),
                "percentile": round(float(w.anomaly_pct), 4),
                "role": getattr(w, "role", None),
                "reasons": [{"feature": x.feature, "contribution": round(float(x.contribution), 4), "text": x.reason}
                            for x in rs.itertuples(index=False)],
            })
    return out
