"""The Data screen API: upload, check, add / replace, remove, restore, background analysis."""
import io
import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.deps import Store, pipeline_lock, set_store
from app.main import app
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


def _xlsx(df: pd.DataFrame, sheet: str = "Sheet1") -> bytes:
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name=sheet, index=False)
    return buf.getvalue()


def _upload(client, name: str, data: bytes) -> dict:
    r = client.post("/api/data/staged", params={"filename": name}, content=data)
    assert r.status_code == 200
    return r.json()


def _wait(client) -> dict:
    for _ in range(600):
        job = client.get("/api/data/job").json()
        if job["state"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("analysis did not finish")


def _new_icore(icore_short_df, holder: str) -> pd.DataFrame:
    df = icore_short_df.copy()
    df["AC_Name"] = holder
    df["Cr_Amt"] = df["Cr_Amt"].map(lambda v: str(int(v) + 7) if v != "0" else v)
    return df


def test_dataset_state(client):
    d = client.get("/api/data").json()
    assert len(d["files"]) == 6 and all(f["analysed"] for f in d["files"])
    assert d["staged"] == [] and d["archives"] == [] and d["needs_rerun"] is False
    assert d["job"]["state"] in ("idle", "done") and d["job"]["steps"][0] == "ingest"
    f7 = next(f for f in d["files"] if f["name"] == "7_SOA.xlsx")
    assert f7["accounts"] == ["SOA7"] and f7["layouts"] == ["icore_short"] and f7["time_reliable"] is True


def test_upload_rejects_what_cannot_be_analysed(client, raw_dir):
    assert "unsupported file type" in _upload(client, "notes.txt", b"hello")["error"]
    bad = _upload(client, "other.csv", b"a,b\n1,2\n")
    assert bad["ok"] is False and "sheet 'other' does not match any supported statement layout" in bad["error"]
    dup = _upload(client, "copy.xlsx", (raw_dir / "7_SOA.xlsx").read_bytes())
    assert dup["ok"] is False and "already in the dataset as 7_SOA.xlsx" in dup["error"]
    assert client.get("/api/data").json()["staged"] == []


def test_add_remove_replace_restore(client, icore_short_df, debit_credit_df):
    up = _upload(client, "new statement 123456789012.xlsx", _xlsx(_new_icore(icore_short_df, "New Holder"), "ICORE_STMT_123456789012"))
    assert up["ok"] and up["sheets"][0]["layout"] == "icore_short" and up["sheets"][0]["time_reliable"]
    assert "123456789012" not in up["original_name"] and "123456789012" not in up["sheets"][0]["sheet"]  # masked
    assert up["sheets"][0]["first_date"] == "2020-12-17"
    csv = debit_credit_df.assign(Customer_Name="Csv Holder").to_csv(index=False).encode()
    up2 = _upload(client, "statement.csv", csv)
    assert up2["ok"] and up2["sheets"][0]["layout"] == "debit_credit" and up2["sheets"][0]["first_date"] is None
    assert _upload(client, "again.csv", csv)["error"] == "this file is already in the upload list"
    assert len(client.get("/api/data").json()["staged"]) == 2

    # add: uploads get the next unused numbers (14 is the highest in the fixture data)
    d = client.post("/api/data/run", json={"mode": "add"}).json()
    assert d["job"]["state"] == "running" and d["job"]["mode"] == "add"
    job = _wait(client)
    assert job["state"] == "done", job["error"]
    assert job["steps_done"] == len(job["steps"]) and job["n_accounts"] == 8
    d = client.get("/api/data").json()
    names = {f["name"] for f in d["files"]}
    assert {"15_SOA.xlsx", "16_SOA.csv"} <= names and not d["needs_rerun"] and d["staged"] == []
    assert next(f for f in d["files"] if f["name"] == "15_SOA.xlsx")["accounts"] == ["SOA15"]
    assert client.get("/api/stats").json()["n_accounts"] == 8

    # remove: the file is archived, not deleted
    client.delete("/api/data/files/16_SOA.csv")
    assert _wait(client)["state"] == "done"
    d = client.get("/api/data").json()
    assert len(d["files"]) == 7 and d["archives"][0]["reason"] == "removed"
    assert client.delete("/api/data/files/99_SOA.xlsx").status_code == 400

    # replace: uploads become the whole dataset; the 7 current files are archived
    _upload(client, "a.xlsx", _xlsx(_new_icore(icore_short_df, "Holder Two")))
    _upload(client, "b.xlsx", _xlsx(_new_icore(icore_short_df, "Holder Three")))
    client.post("/api/data/run", json={"mode": "replace"})
    job = _wait(client)
    assert job["state"] == "done", job["error"]
    d = client.get("/api/data").json()
    assert [f["name"] for f in d["files"]] == ["17_SOA.xlsx", "18_SOA.xlsx"]
    replaced = next(a for a in d["archives"] if a["reason"] == "replaced")
    assert replaced["n_files"] == 7

    # restore: the replaced set comes back, the current one is archived in turn
    client.post(f"/api/data/archives/{replaced['name']}/restore")
    assert _wait(client)["state"] == "done"
    d = client.get("/api/data").json()
    assert len(d["files"]) == 7 and "15_SOA.xlsx" in {f["name"] for f in d["files"]}
    assert any(a["n_files"] == 2 for a in d["archives"])
    assert client.get("/api/stats").json()["n_accounts"] == 7


def test_replace_needs_uploads_and_busy_is_409(client):
    assert client.post("/api/data/run", json={"mode": "replace"}).status_code == 400
    assert client.post("/api/data/run", json={"mode": "other"}).status_code == 422
    assert client.post("/api/data/archives/../restore").status_code in (400, 404)
    pipeline_lock.acquire()
    try:
        assert client.post("/api/data/staged", params={"filename": "x.csv"}, content=b"a").status_code == 409
        assert client.post("/api/data/run", json={"mode": "add"}).status_code == 409
    finally:
        pipeline_lock.release()
