import pandas as pd
import pytest

from app import config
from app.complaints.generator import _corrupt, generate_complaints
from app.complaints.matcher import evaluate, match_complaints
from app.scoring.alerts import alerts, lead_list
from app.scoring.risk_score import risk_scores, tier_for


@pytest.fixture
def txns():
    return pd.DataFrame({
        "txn_uid": [f"SOA9-{i:06d}" for i in range(6)],
        "account_id": ["SOA9"] * 6,
        "direction": ["CR"] * 6,
        "amount": [1000.0, 2500.0, 777.0, 12000.0, 300.0, 50.0],
        "txn_ts": pd.to_datetime(["2021-01-01 10:00"] * 6),
        "channel": ["UPI"] * 5 + ["IMPS"],
        "counterparty_key": ["upi:ramesh.kuma", "upi:9876543210", "upi:priya.sharm", "upi:testpayer03", "upi:zzqqxx", "acct:123456789012"],
        "counterparty_type": ["upi"] * 5 + ["account"],
    })


def test_generator_labels(txns):
    c = generate_complaints(txns, n=20, seed=1)
    assert len(c) == 20 and c["synthetic"].all()
    assert c["complaint_id"].is_unique
    # only 6 seedable transactions: the rest are decoys
    assert (~c["is_decoy"]).sum() == 6 and c["is_decoy"].sum() == 14
    assert c.loc[~c["is_decoy"], "seed_txn_uid"].notna().all()


def test_corrupt_changes_little():
    import numpy as np
    rng = np.random.default_rng(0)
    for _ in range(50):
        out = _corrupt("ramesh.kumar", rng)
        assert abs(len(out) - len("ramesh.kumar")) <= 2


def test_matcher_handles_typos_and_amounts(txns):
    complaints = pd.DataFrame([
        {"complaint_id": "C1", "date": pd.Timestamp("2021-01-01"), "reported_upi_or_account": "ramesh.kuma@okaxis",
         "reported_type": "upi", "amount": 1010.0, "channel": "UPI"},  # +1%
        {"complaint_id": "C2", "date": pd.Timestamp("2021-01-02"), "reported_upi_or_account": "9876543201",
         "reported_type": "upi", "amount": 2500.0, "channel": "UPI"},  # swapped digits
        {"complaint_id": "C3", "date": pd.Timestamp("2021-01-01"), "reported_upi_or_account": "bcdfghjk42@ybl",
         "reported_type": "upi", "amount": 5000.0, "channel": "UPI"},  # decoy
        {"complaint_id": "C4", "date": pd.Timestamp("2021-01-01"), "reported_upi_or_account": "12345678901",
         "reported_type": "account", "amount": 50.0, "channel": "IMPS"},  # truncated account
    ])
    m = match_complaints(complaints, txns, {"SOA9": "R1"})
    best = m.drop_duplicates("complaint_id").set_index("complaint_id")
    assert best.loc["C1", "counterparty_key"] == "upi:ramesh.kuma" and best.loc["C1", "amount_match"]
    assert best.loc["C2", "counterparty_key"] == "upi:9876543210"
    assert best.loc["C4", "counterparty_key"] == "acct:123456789012"
    assert "C3" not in best.index
    assert best.loc["C1", "ring_id"] == "R1" and best.loc["C1", "time_match"]
    complaints["is_decoy"] = [False, False, True, False]
    complaints["seed_counterparty_key"] = ["upi:ramesh.kuma", "upi:9876543210", None, "acct:123456789012"]
    ev = evaluate(complaints, m)
    assert ev["recall_top1"] == 1.0 and ev["decoys_matched"] == 0


def test_risk_score_and_alerts():
    accounts = pd.DataFrame({"account_id": ["A", "B", "C"], "layout": "x", "time_reliable": True, "n_rows": 1})
    ind = pd.DataFrame({"account_id": ["A", "B", "C"], "indicator_score": [1.0, 0.5, 0.0]})
    net = pd.DataFrame({"account_id": ["A", "B", "C"], "network_score": [1.0, 0.5, 0.0], "ring_id": ["R1", None, None]})
    s = risk_scores(accounts, ind, net)
    assert s.set_index("account_id")["risk_score"].to_dict() == {"A": 100.0, "B": 50.0, "C": 0.0}
    assert s["anomaly_score"].isna().all() and s["anomaly_uplift"].eq(0).all()
    reasons = pd.DataFrame({"account_id": ["A"], "rank": [1], "source": ["indicator"], "text": ["x"], "contribution": [1.0]})
    leads = lead_list(s, reasons, accounts)
    assert leads["account_id"].tolist() == ["A", "B", "C"]
    a = alerts(leads, threshold=50)
    assert a["account_id"].tolist() == ["A", "B"] and a["alert_id"].tolist() == ["ALR-001", "ALR-002"]
    assert tier_for(75) == "HIGH" and tier_for(55) == "MEDIUM" and tier_for(10) == "LOW"


def test_anomaly_is_an_uplift_and_missing_is_not_a_penalty():
    accounts = pd.DataFrame({"account_id": ["A", "B", "C"]})
    ind = pd.DataFrame({"account_id": ["A", "B", "C"], "indicator_score": [0.5, 0.5, 0.5]})
    net = pd.DataFrame({"account_id": ["A", "B", "C"], "network_score": [0.5, 0.5, 0.5], "ring_id": [None] * 3})
    anom = pd.DataFrame({"account_id": ["A", "B", "C"], "anomaly_score": [1.0, 0.0, None]})
    s = risk_scores(accounts, ind, net, anom).set_index("account_id")
    # base 50; A gets the full uplift on the remaining headroom, B (steady) and C (no timestamps) keep the base
    assert s.loc["A", "risk_score"] == pytest.approx(50 + config.ANOMALY_UPLIFT * 50)
    assert s.loc["B", "risk_score"] == 50.0 and s.loc["C", "risk_score"] == 50.0
    assert s.loc["C", "score_parts"] == "indicator,network"
    assert (s["risk_score_phase1"] == 50.0).all()
