"""Train all Phase 2 models, save artefacts and the model card."""
from __future__ import annotations

import json
import platform
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap
import sklearn

from app import config
from app.models.anomaly import account_anomaly, fit_anomaly_model, score_windows
from app.models.explain import explain_windows
from app.models.features import MODEL_FEATURES, account_baselines, model_matrix
from app.models.roles import account_roles, window_roles


def train_models(windows: pd.DataFrame, features: pd.DataFrame, accounts: pd.DataFrame,
                 model_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    model_dir = model_dir or config.MODEL_DIR
    model_dir.mkdir(parents=True, exist_ok=True)

    if len(windows) == 0:
        empty_acc = accounts[["account_id"]].assign(anomaly_score=np.nan, flagged_weeks=pd.NA, n_weeks=pd.NA)
        roles, _, _ = account_roles(features, pd.DataFrame(columns=["account_id", "cluster", "role"]))
        return {"window_scores": pd.DataFrame(), "shap_reasons": pd.DataFrame(), "window_roles": pd.DataFrame(),
                "role_profiles": pd.DataFrame(), "anomaly": empty_acc, "roles": roles}

    baselines = account_baselines(windows)
    model = fit_anomaly_model(model_matrix(windows, baselines))
    model.baselines = baselines
    wscores = score_windows(model, windows)
    shap_reasons = explain_windows(model, windows, wscores)
    acc_anom = account_anomaly(wscores, accounts)
    wroles, profiles, _ = window_roles(windows)
    roles, _, acc_labels = account_roles(features, wroles)
    window_out = wscores.merge(wroles, on=["account_id", "week_start"], how="left")

    joblib.dump({"scaler": model.scaler, "forest": model.forest, "train_scores": model.train_scores,
                 "threshold": model.threshold, "features": MODEL_FEATURES,
                 "baselines": baselines}, model_dir / "anomaly_model.joblib", compress=3)
    card = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "phase": 2,
        "labels_available": False,
        "versions": {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                     "shap": shap.__version__, "numpy": np.__version__, "pandas": pd.__version__},
        "training_data": {"windows": int(len(windows)), "accounts": int(windows["account_id"].nunique()),
                          "weeks_from": str(windows["week_start"].min().date()), "weeks_to": str(windows["week_start"].max().date())},
        "models": {
            "isolation_forest": {
                "use": "flag unusual account-weeks", "features": MODEL_FEATURES, "scaler": "RobustScaler",
                "n_estimators": config.IFOREST_TREES, "contamination": config.IFOREST_CONTAMINATION,
                "random_state": config.MODEL_SEED, "threshold_raw": model.threshold,
                "flagged_windows": int(wscores["is_flagged"].sum()),
                "account_score": f"mean of top-{config.ACCOUNT_TOP_WINDOWS} window percentile scores",
            },
            "shap_tree_explainer": {"use": "top reasons per flagged week", "top_features": config.SHAP_TOP_FEATURES},
            "hdbscan_window_roles": {
                "use": "behaviour roles per week", "selection": config.HDBSCAN_SELECTION,
                "min_cluster_size": config.HDBSCAN_WINDOW_MIN_CLUSTER, "min_samples": config.HDBSCAN_WINDOW_MIN_SAMPLES,
                "min_week_txns": config.ROLE_MIN_WEEK_TXNS, "clusters": profiles.to_dict(orient="records"),
            },
            "hdbscan_account_roles": {
                "use": "roles for accounts without reliable timestamps", "selection": "eom",
                "min_cluster_size": config.HDBSCAN_ACCOUNT_MIN_CLUSTER, "n_clusters": int(acc_labels.max() + 1) if len(acc_labels) else 0,
            },
        },
        "score_weights": config.SCORE_WEIGHTS,
    }
    (model_dir / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
    return {"window_scores": window_out, "shap_reasons": shap_reasons, "window_roles": wroles,
            "role_profiles": profiles, "anomaly": acc_anom, "roles": roles}
