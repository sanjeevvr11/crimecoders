import math

import numpy as np
import pandas as pd
import pytest

from app.features.account_features import account_features
from app.features.indicators import indicator_scores, indicator_table, ramp
from app.features.window_features import window_features


def _tx(rows, reliable=True, account="SOA7"):
    df = pd.DataFrame(rows, columns=["txn_ts", "direction", "amount", "channel", "counterparty_key"])
    df["txn_ts"] = pd.to_datetime(df["txn_ts"])
    df["account_id"] = account
    df["time_reliable"] = reliable
    return df


@pytest.fixture
def mule_tx():
    return _tx([
        ("2021-01-01 10:00", "CR", 1000.0, "UPI", "upi:a"),
        ("2021-01-01 10:30", "DR", 950.0, "IMPS", "ifsc:X"),
        ("2021-01-01 12:00", "CR", 2000.0, "UPI", "upi:b"),
        ("2021-01-01 20:00", "DR", 1990.0, "IMPS", "ifsc:X"),
        ("2021-01-02 02:00", "CR", 500.0, "UPI", "upi:c"),
    ])


def test_account_features(mule_tx):
    f = account_features(mule_tx).iloc[0]
    assert f["pass_through_ratio"] == pytest.approx(2940 / 3500)
    assert f["fan_in"] == 3 and f["fan_out"] == 1
    assert f["round_amount_share"] == pytest.approx(3 / 5)
    assert f["upi_share"] == pytest.approx(3 / 5)
    # dwell: 0.5h, 8h, none -> median of [0.5, 8]
    assert f["median_dwell_hours"] == pytest.approx(4.25)
    # fast (<=2h) inflow: 1000 of 3500
    assert f["fast_outflow_share"] == pytest.approx(1000 / 3500)
    assert f["night_share"] == pytest.approx(1 / 5)
    assert f["active_days"] == 2


def test_no_time_features_when_unreliable(mule_tx):
    f = account_features(mule_tx.assign(time_reliable=False, txn_ts=pd.NaT)).iloc[0]
    assert math.isnan(f["median_dwell_hours"]) and math.isnan(f["night_share"])


def test_opaque_narrations_make_fan_in_unknown():
    tx = _tx([("2021-01-01", "CR", 10.0, "UNKNOWN", None), ("2021-01-01", "DR", 10.0, "UNKNOWN", None)])
    f = account_features(tx).iloc[0]
    assert math.isnan(f["fan_in"]) and math.isnan(f["upi_share"])


def test_window_features(mule_tx):
    w = window_features(mule_tx)
    assert w["n_txns"].sum() == 5
    assert {"pass_through_ratio", "max_txns_per_hour", "unique_counterparties"} <= set(w.columns)
    assert window_features(mule_tx.assign(time_reliable=False)).empty


def test_ramp():
    assert ramp(0.5, 0, 1) == 0.5
    assert ramp(5, 0, 1) == 1.0
    assert ramp(72, 72, 2) == 0.0 and ramp(2, 72, 2) == 1.0  # inverted
    assert np.isnan(ramp(np.nan, 0, 1))


def test_indicators_and_reasons(mule_tx):
    feats = account_features(mule_tx)
    ind = indicator_table(feats)
    assert ind["subscore"].between(0, 1).all()
    assert "median_dwell_hours" in set(ind["indicator"])
    reasons = ind["reason"].dropna().tolist()
    assert any("debited out again" in r for r in reasons)
    s = indicator_scores(ind).iloc[0]
    assert 0 <= s["indicator_score"] <= 1
