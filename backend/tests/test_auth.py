"""Sign-in, roles, admin-only unmasking and the audit log (TRACE360_AUTH=on)."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api.deps import Store, set_store
from app.api.routes import auth as auth_routes
from app.auth.passwords import hash_password, verify_password
from app.auth.store import AuthError, AuthStore, set_auth_store
from app.main import app
from app.pipeline.run_pipeline import run

PW = "correct-horse-9"


@pytest.fixture
def users(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", True)
    store = AuthStore(tmp_path / "auth.sqlite3")
    for name, role in (("ada", "admin"), ("ian", "investigator"), ("val", "viewer")):
        store.create_user(name, PW, role)
    set_auth_store(store)
    auth_routes._failures.clear()
    yield store
    set_auth_store(None)


@pytest.fixture
def api(pipeline_dirs, monkeypatch, users):
    for attr, key in (("RAW_DIR", "raw_dir"), ("PROCESSED_DIR", "processed_dir"), ("DUCKDB_PATH", "db_path"), ("SYNTHETIC_DIR", "synthetic_dir")):
        monkeypatch.setattr(config, attr, pipeline_dirs[key])
    monkeypatch.setattr(config, "N_SYNTHETIC_COMPLAINTS", 12)
    monkeypatch.setattr(config, "MODEL_DIR", pipeline_dirs["model_dir"])
    run(**pipeline_dirs)
    set_store(Store(pipeline_dirs["processed_dir"]))
    yield
    set_store(None)


def signed_in(username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": PW})
    assert r.status_code == 200, r.text
    return c


def test_password_hashing():
    h = hash_password("s3cret-pass")
    assert h.startswith("scrypt$") and "s3cret-pass" not in h
    assert verify_password("s3cret-pass", h) and not verify_password("wrong-pass", h)
    assert hash_password("s3cret-pass") != h  # salted


def test_everything_needs_sign_in(api):
    c = TestClient(app)
    for path in ("/api/stats", "/api/leads", "/api/conclusion", "/api/accounts/SOA2", "/api/graph/rings", "/api/data", "/api/admin/users"):
        assert c.get(path).status_code == 401, path
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    summary = c.get("/api/public/summary")  # the landing page: counts only, no sign-in
    assert summary.status_code == 200 and summary.json()["ready"] and summary.json()["n_transactions"] > 0
    assert set(summary.json()) == {"ready", "n_statements", "n_transactions", "n_counterparties", "n_leads"}


def test_login_sets_an_httponly_cookie_and_logout_ends_it(users):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "ian", "password": PW})
    cookie = r.headers["set-cookie"]
    assert config.SESSION_COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    me = c.get("/api/auth/me").json()
    assert me["user"]["username"] == "ian" and me["user"]["role"] == "investigator" and me["unmasked"] is False
    assert c.post("/api/auth/logout").json() == {"status": "signed out"}
    assert c.get("/api/auth/me").status_code == 401


def test_wrong_password_and_rate_limit(users):
    c = TestClient(app)
    for _ in range(config.LOGIN_MAX_FAILURES):
        assert c.post("/api/auth/login", json={"username": "val", "password": "nope-nope"}).status_code == 401
    assert c.post("/api/auth/login", json={"username": "val", "password": PW}).status_code == 429
    assert c.post("/api/auth/login", json={"username": "nobody", "password": PW}).status_code == 401


def test_roles(api):
    viewer, inv, admin = signed_in("val"), signed_in("ian"), signed_in("ada")
    assert viewer.get("/api/leads").status_code == 200
    assert viewer.get("/api/accounts/SOA2").status_code == 200
    # transactions, connections and PDFs need investigator
    assert viewer.get("/api/accounts/SOA2/timeline").status_code == 403
    assert viewer.get("/api/reports/account/SOA2.pdf").status_code == 403
    assert inv.get("/api/accounts/SOA2/timeline").status_code == 200
    # Ingestion, re-running the analysis and users are admin only
    for c in (viewer, inv):
        assert c.get("/api/data").status_code == 403
        assert c.post("/api/pipeline/run").status_code == 403
        assert c.get("/api/admin/users").status_code == 403
    assert admin.get("/api/data").status_code == 200
    assert admin.get("/api/admin/users").status_code == 200


def test_only_admins_see_identifiers_in_full(api):
    inv, admin = signed_in("ian"), signed_in("ada")
    masked = inv.get("/api/accounts/SOA2")
    assert masked.json()["holder_name"] == "*********er A" and "Test Holder A" not in masked.text
    full = admin.get("/api/accounts/SOA2").json()
    assert full["holder_name"] == "Test Holder A" and full["account_number"] == "1111222233"
    assert admin.get("/api/auth/me").json()["unmasked"] is True
    # the cached conclusion must not leak the admin's unmasked copy to others
    admin.get("/api/conclusion")
    assert "Test Holder" not in inv.get("/api/conclusion").text
    # and the masked copy is not served back to the admin either
    inv_labels = inv.get("/api/graph/overview").text
    assert "ramesh.kuma" not in inv_labels and "ramesh.kuma" in admin.get("/api/graph/overview").text


def test_audit_log(api, users):
    inv, admin = signed_in("ian"), signed_in("ada")
    inv.get("/api/accounts/SOA7")
    admin.get("/api/accounts/SOA2")
    TestClient(app).post("/api/auth/login", json={"username": "ian", "password": "bad-password"})
    page = admin.get("/api/admin/audit").json()
    rows = [(e["username"], e["action"], e["target"], e["unmasked"]) for e in page["items"]]
    assert ("ian", "view_account", "SOA7", False) in rows
    assert ("ada", "view_account", "SOA2", True) in rows
    assert any(a == "login_failed" for _, a, _, _ in rows)
    assert page["total"] >= 5
    assert admin.get("/api/admin/audit", params={"username": "ian", "action": "view_account"}).json()["total"] == 1


def test_user_management(users):
    admin = signed_in("ada")
    r = admin.post("/api/admin/users", json={"username": "newbie", "password": "longenough1", "role": "viewer", "display_name": "New B"})
    assert r.status_code == 200 and r.json()["role"] == "viewer" and "password" not in r.text
    uid = r.json()["id"]
    assert admin.post("/api/admin/users", json={"username": "newbie", "password": "longenough1", "role": "viewer"}).status_code == 400
    assert admin.post("/api/admin/users", json={"username": "short", "password": "short", "role": "viewer"}).status_code == 400
    # promote, then deactivate: the user is signed out and cannot sign in
    newbie = TestClient(app)
    assert newbie.post("/api/auth/login", json={"username": "newbie", "password": "longenough1"}).status_code == 200
    assert admin.patch(f"/api/admin/users/{uid}", json={"role": "investigator"}).json()["role"] == "investigator"
    assert newbie.get("/api/auth/me").status_code == 401  # role change ends sessions
    assert admin.patch(f"/api/admin/users/{uid}", json={"active": False}).json()["active"] is False
    assert TestClient(app).post("/api/auth/login", json={"username": "newbie", "password": "longenough1"}).status_code == 401
    # password reset
    admin.patch(f"/api/admin/users/{uid}", json={"active": True, "password": "brand-new-pass"})
    assert TestClient(app).post("/api/auth/login", json={"username": "newbie", "password": "brand-new-pass"}).status_code == 200
    assert admin.patch("/api/admin/users/999", json={"role": "viewer"}).status_code == 404


def test_last_admin_cannot_be_removed(tmp_path):
    store = AuthStore(tmp_path / "a.sqlite3")
    a = store.create_user("boss", PW, "admin")
    with pytest.raises(AuthError):
        store.update_user(a["id"], role="viewer")
    with pytest.raises(AuthError):
        store.update_user(a["id"], active=False)
    store.create_user("boss2", PW, "admin")
    assert store.update_user(a["id"], role="viewer")["role"] == "viewer"


def test_sign_in_off_keeps_the_old_behaviour(api, monkeypatch):
    monkeypatch.setattr(config, "AUTH_ENABLED", False)
    c = TestClient(app)
    assert c.get("/api/data").status_code == 200
    assert c.get("/api/accounts/SOA2").json()["holder_name"] == "*********er A"
    assert c.get("/api/auth/me").json()["auth_enabled"] is False
