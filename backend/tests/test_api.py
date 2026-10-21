import re

import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.deps import Store, set_store
from app.main import app
from app.masking import mask, mask_text
from app.pipeline.run_pipeline import run


@pytest.fixture
def client(pipeline_dirs, monkeypatch):
    for attr, key in (("RAW_DIR", "raw_dir"), ("PROCESSED_DIR", "processed_dir"), ("DUCKDB_PATH", "db_path"), ("SYNTHETIC_DIR", "synthetic_dir")):
        monkeypatch.setattr(config, attr, pipeline_dirs[key])
    monkeypatch.setattr(config, "N_SYNTHETIC_COMPLAINTS", 12)
    monkeypatch.setattr(config, "MODEL_DIR", pipeline_dirs["model_dir"])
    run(**pipeline_dirs)
    set_store(Store(pipeline_dirs["processed_dir"]))
    yield TestClient(app)
    set_store(None)


def test_masking():
    assert mask("1111222233") == "******2233"
    assert mask("Test Holder A") == "*********er A"
    assert mask(None) is None
    assert mask_text("PAN ABCDE1234F") == "PAN ******234F"
    assert mask_text("UPI/testpayer01/530000000004/UPI") == "UPI/*******er01/********0004/UPI"
    assert mask_text("O/W RTN:37:FUNDS INSUFFICIENT") == "O/W RTN:37:FUNDS INSUFFICIENT"


def test_stats(client):
    s = client.get("/api/stats").json()
    assert s["n_accounts"] == 6 and s["n_rings"] == 1
    assert s["rows_per_layout"]["icore_short"] == 7


def test_leads_and_alerts(client):
    leads = client.get("/api/leads").json()
    assert len(leads) == 6 and leads[0]["rank"] == 1
    assert leads == sorted(leads, key=lambda r: -r["risk_score"])
    assert client.get("/api/leads?tier=HIGH").status_code == 200
    alerts = client.get("/api/alerts").json()
    assert all(a["risk_score"] >= config.ALERT_THRESHOLD for a in alerts)


def test_account_detail_is_masked(client):
    r = client.get("/api/accounts/SOA2")
    d = r.json()
    assert d["holder_name"] == "*********er A" and d["account_number"] == "******2233"
    assert "1111222233" not in r.text and "Test Holder A" not in r.text
    assert 0 <= d["score"]["risk_score"] <= 100 and len(d["reasons"]) <= 5
    assert client.get("/api/accounts/SOA999").status_code == 404
    assert len(client.get("/api/accounts").json()) == 6


def test_sheet_names_are_masked(client):
    # ICORE sheet names embed a 12-digit number (fixture: ICORE_STMT_000000000001)
    detail = client.get("/api/accounts/SOA7").json()
    assert detail["source_sheet"] == "ICORE_STMT_********0001"
    listing = client.get("/api/accounts").text
    assert "000000000001" not in listing and "000000000002" not in listing


def test_timeline(client):
    t = client.get("/api/accounts/SOA7/timeline?limit=3").json()
    assert t["total"] == 7 and len(t["transactions"]) == 3 and t["time_reliable"]
    assert t["daily"] and t["transactions"][0]["txn_ts"].startswith("2020-12-17")
    assert all(x["direction"] == "DR" for x in client.get("/api/accounts/SOA2/timeline?direction=DR").json()["transactions"])
    r = client.get("/api/accounts/SOA2/timeline?direction=CR")
    assert "ramesh.kuma" not in r.text and "*******kuma" in r.text  # VPAs masked


def test_trail(client):
    t = client.get("/api/accounts/SOA7/trail?hops=2&direction=backward").json()
    assert t["paths"] and all(p["nodes"][0]["ref"] == "SOA7" for p in t["paths"])
    labels = [n["label"] for p in t["paths"] for n in p["nodes"]]
    assert not any(re.search(r"\d{6,}", lab) for lab in labels)
    ref = next(n["ref"] for p in t["paths"] for n in p["nodes"] if not n["is_subject"])
    fwd = client.get(f"/api/accounts/{ref}/trail?hops=1").json()
    assert {p["nodes"][-1]["ref"] for p in fwd["paths"]} >= {"SOA7"}
    assert client.get("/api/accounts/SOA7/trail?direction=sideways").status_code == 422


def test_rings(client):
    rings = client.get("/api/graph/rings").json()
    assert rings[0]["subject_accounts"] == ["SOA2", "SOA7"]
    r = client.get("/api/graph/rings/R1").json()
    ids = {n["data"]["id"] for n in r["elements"]["nodes"]}
    assert {"SOA2", "SOA7"} <= ids and all(i in ids for e in r["elements"]["edges"] for i in (e["data"]["source"], e["data"]["target"]))
    assert client.get("/api/graph/rings/R9").status_code == 404


def test_complaints(client):
    cs = client.get("/api/complaints").json()
    assert len(cs) == 12 and all(c["synthetic"] for c in cs)
    m = client.get(f"/api/complaints/{cs[0]['complaint_id']}/matches").json()
    assert m["complaint"]["complaint_id"] == cs[0]["complaint_id"]
    assert client.get("/api/complaints/CMP-9999/matches").status_code == 404


def test_report_pdf(client):
    r = client.get("/api/reports/account/SOA7.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_pipeline_run_endpoint(client):
    r = client.post("/api/pipeline/run")
    assert r.status_code == 200 and r.json()["stats"]["n_accounts"] == 6
    assert client.get("/api/stats").json()["n_transactions"] > 0


def test_ml_fields(client):
    d = client.get("/api/accounts/SOA7").json()
    assert {"anomaly_score", "flagged_weeks", "role", "shap_reasons"} <= set(d)
    assert d["anomaly_score"] is not None and isinstance(d["shap_reasons"], list)
    no_time = client.get("/api/accounts/SOA2").json()
    assert no_time["anomaly_score"] is None and no_time["flagged_weeks"] is None  # not imputed as 0
    lead = client.get("/api/leads").json()[0]
    assert {"risk_score_phase1", "anomaly_uplift", "role"} <= set(lead)


def test_models_summary(client):
    r = client.get("/api/models/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["model_card"]["labels_available"] is False
    assert "isolation_forest" in body["model_card"]["models"]


def test_cors(client):
    r = client.options("/api/stats", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
