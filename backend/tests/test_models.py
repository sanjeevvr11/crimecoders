"""Phase 2 models on small generated data (no real statements)."""
import json

import numpy as np
import pandas as pd
import pytest

from app import config
from app.features.account_features import account_features
from app.features.window_features import window_features
from app.models.anomaly import account_anomaly, fit_anomaly_model, score_windows
from app.models.evaluate import PATTERNS, clustering_quality, inject_pattern, injection_test, run_evaluation, stability
from app.models.explain import REASONS, explain_windows
from app.models.features import BASELINE_FEATURES, LEVEL_FEATURES, MODEL_FEATURES, account_baselines, model_matrix
from app.models.report import write_report
from app.models.roles import account_roles, name_role, window_roles
from app.models.trainer import train_models

BURST = ("ACC0", pd.Timestamp("2021-03-01"))  # (account, week) with a planted mule burst


def _normal_week(rng, account, week, n):
    rows = []
    for _ in range(n):
        t = week + pd.Timedelta(days=int(rng.integers(0, 6)), hours=float(rng.uniform(9, 18)))
        a = float(np.round(rng.lognormal(8, 0.6), 2))
        rows.append((account, t, "CR", a))
        rows.append((account, t + pd.Timedelta(hours=float(rng.uniform(6, 40))), "DR", round(a * rng.uniform(0.3, 0.9), 2)))
    return rows


@pytest.fixture(scope="module")
def txns():
    rng = np.random.default_rng(3)
    rows = []
    weeks = pd.date_range("2021-01-04", periods=12, freq="W-MON")
    for a in range(6):
        for w in weeks:
            rows += _normal_week(rng, f"ACC{a}", w, int(rng.integers(8, 15)))
    # burst: 40 quick night-time round-amount pass-throughs in one week of ACC0
    t0 = BURST[1] + pd.Timedelta(days=2, hours=1)
    for i in range(40):
        t = t0 + pd.Timedelta(minutes=5 * i)
        rows += [("ACC0", t, "CR", 50000.0), ("ACC0", t + pd.Timedelta(minutes=3), "DR", 50000.0)]
    df = pd.DataFrame(rows, columns=["account_id", "txn_ts", "direction", "amount"])
    df["channel"] = "UPI"
    df["counterparty_key"] = None
    df["time_reliable"] = True
    # an account without reliable timestamps
    extra = pd.DataFrame({"account_id": ["NOTIME"] * 4, "txn_ts": pd.NaT, "direction": ["CR", "DR", "CR", "DR"],
                          "amount": [100.0, 90.0, 200.0, 180.0], "channel": "UNKNOWN", "counterparty_key": None, "time_reliable": False})
    return pd.concat([df, extra], ignore_index=True)


@pytest.fixture(scope="module")
def windows(txns):
    return window_features(txns)


@pytest.fixture(scope="module")
def accounts(txns):
    return pd.DataFrame({"account_id": sorted(txns["account_id"].unique())})


def test_window_features_and_matrix(windows):
    assert len(windows) >= 6 * 12 and "NOTIME" not in set(windows["account_id"])  # debits can spill into the next week
    burst = windows.set_index(["account_id", "week_start"]).loc[BURST]
    assert burst["n_fast_credits"] >= 40 and burst["n_night"] >= 80 and burst["round_amount_share"] > 0.5
    X = model_matrix(windows)
    assert list(X.columns) == LEVEL_FEATURES + BASELINE_FEATURES
    assert not X.isna().any().any()
    # the median week of an account sits on its own baseline
    assert X["dev_log_n_txns"].abs().min() == 0


def test_baseline_account_column_uses_source_baseline(windows):
    base = account_baselines(windows)
    copy = windows.loc[windows["account_id"] == "ACC1"].head(1).assign(account_id="INJ0", baseline_account="ACC1")
    orig = windows.loc[windows["account_id"] == "ACC1"].head(1)
    a, b = model_matrix(copy, base), model_matrix(orig, base)
    assert np.allclose(a[BASELINE_FEATURES].to_numpy(), b[BASELINE_FEATURES].to_numpy())


def test_isolation_forest_flags_the_burst(windows, accounts):
    model = fit_anomaly_model(model_matrix(windows))
    ws = score_windows(model, windows)
    assert ws["anomaly_score"].between(0, 1).all()
    top = ws.sort_values("anomaly_raw", ascending=False).iloc[0]
    assert (top["account_id"], top["week_start"]) == BURST and top["is_flagged"]
    assert ws["is_flagged"].mean() == pytest.approx(config.IFOREST_CONTAMINATION, abs=0.03)
    acc = account_anomaly(ws, accounts).set_index("account_id")
    assert pd.isna(acc.loc["NOTIME", "anomaly_score"])  # no timestamps -> None, not 0
    assert acc.loc["ACC0", "anomaly_score"] == acc["anomaly_score"].max()
    assert acc.loc["ACC0", "flagged_weeks"] >= 1


def test_shap_reasons(windows):
    model = fit_anomaly_model(model_matrix(windows))
    ws = score_windows(model, windows)
    ex = explain_windows(model, windows, ws)
    assert set(MODEL_FEATURES) <= set(REASONS)
    burst = ex.loc[(ex["account_id"] == BURST[0]) & (ex["week_start"] == BURST[1])]
    assert 1 <= len(burst) <= config.SHAP_TOP_FEATURES and (burst["contribution"] > 0).all()
    assert burst["reason"].str.len().gt(10).all()
    assert ex.groupby(["account_id", "week_start"]).size().max() <= config.SHAP_TOP_FEATURES


@pytest.mark.parametrize("args,expected", [
    ((0.9, 0.0, 0.0, 50.0), "collector"),
    ((0.1, 0.3, 0.0, 50.0), "distributor"),
    ((0.5, 1.0, 0.7, 1.0), "layering"),
    ((0.5, 1.0, 0.1, 30.0), "normal-looking"),
    ((0.9, 1.0, 0.1, 2.0), "layering"),  # passes straight through: layering wins over collector
])
def test_name_role(args, expected):
    assert name_role(*args) == expected


def test_roles(windows, txns):
    wr, prof, _ = window_roles(windows)
    assert len(wr) == len(windows) and set(wr["role"]) <= {"collector", "distributor", "layering", "normal-looking", "unclassified", "sparse"}
    feats = account_features(txns)
    roles, _, _ = account_roles(feats, wr)
    assert set(roles["account_id"]) == set(feats["account_id"])
    assert roles.set_index("account_id").loc["NOTIME", "role_source"] == "account clusters"


def test_sparse_weeks_are_not_clustered():
    w = pd.DataFrame({"account_id": ["A"], "week_start": [pd.Timestamp("2021-01-04")], "n_txns": [1], "n_cr": [1], "n_dr": [0],
                      "cr_amount": [10.0], "dr_amount": [0.0], "pass_through_ratio": [0.0], "unique_counterparties": [0],
                      "max_txns_per_hour": [1], "active_hours": [1], "night_share": [0.0], "round_amount_share": [0.0],
                      "small_credit_share": [1.0], "fast_outflow_share": [np.nan], "median_dwell_hours": [np.nan],
                      "n_night": [0], "n_round": [0], "n_small_cr": [1], "n_fast_credits": [0]})
    wr, prof, _ = window_roles(w)
    assert wr["role"].tolist() == ["sparse"] and prof.empty


@pytest.mark.parametrize("pattern", PATTERNS)
def test_inject_pattern_stays_in_week(pattern):
    week = pd.Timestamp("2021-03-01")
    t = inject_pattern(pattern, week, 10000.0, np.random.default_rng(0), "x")
    assert len(t) >= 8 and set(t["direction"]) == {"CR", "DR"}
    assert (t["txn_ts"] >= week).all() and (t["txn_ts"] < week + pd.Timedelta(days=7)).all()


def test_injection_and_stability(windows, txns, accounts):
    r = injection_test(windows, txns, seed=0)
    assert r["n_injected"] >= len(PATTERNS)
    for k in ("roc_auc", "pr_auc", "precision_at_k", "recall_at_threshold", "false_positive_rate"):
        assert 0.0 <= r[k] <= 1.0
    st = stability(windows, accounts, seeds=(0, 1))
    assert 0 <= st["flagged_jaccard_across_seeds"]["mean"] <= 1
    assert "per_account_time_split" in st and "time_split" in st


def test_train_evaluate_report(tmp_path, windows, txns, accounts):
    feats = account_features(txns)
    trained = train_models(windows, feats, accounts, tmp_path / "m")
    card = json.loads((tmp_path / "m" / "model_card.json").read_text())
    assert (tmp_path / "m" / "anomaly_model.joblib").exists()
    assert card["models"]["isolation_forest"]["random_state"] == config.MODEL_SEED and card["labels_available"] is False
    cq = clustering_quality(windows, trained["window_roles"], trained["role_profiles"], trained["roles"])
    assert {"chosen", "alternative_eom", "profiles", "account_roles"} <= set(cq)

    ind = pd.DataFrame({"account_id": accounts["account_id"], "indicator_score": np.linspace(0, 1, len(accounts))})
    ev = run_evaluation(txns, windows, accounts, trained, ind, seeds=(0, 1))
    assert "not real-world accuracy" in ev["note"]
    leads = pd.DataFrame({"rank": [1], "account_id": ["ACC0"], "risk_score": [80.0], "risk_score_phase1": [70.0],
                          "anomaly_uplift": [10.0], "flagged_weeks": [1], "role": ["layering"], "ring_id": [None]})
    reasons = pd.DataFrame({"account_id": ["ACC0"], "rank": [1], "text": ["x"]})
    md, js = write_report(ev, leads, reasons, card, tmp_path / "r")
    text = md.read_text()
    assert "no fraud labels" in text and "Models used and use case" in text and "Top 10" in text
    assert json.loads(js.read_text())["top10"][0]["account_id"] == "ACC0"
