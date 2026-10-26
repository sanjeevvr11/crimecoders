"""SQLite store for users, sessions and the audit log."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import config
from app.auth.passwords import hash_password, verify_password

ROLES = ("viewer", "investigator", "admin")  # each role can do everything the previous one can
MIN_PASSWORD_LEN = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    username TEXT,
    role TEXT,
    action TEXT NOT NULL,
    target TEXT,
    unmasked INTEGER NOT NULL DEFAULT 0,
    ip TEXT,
    detail TEXT
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit(ts);
"""
USER_COLS = "id, username, display_name, role, active, created_at, last_login_at"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rank(role: str) -> int:
    return ROLES.index(role)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthError(ValueError):
    """A rule was broken (bad role, short password, duplicate name, last admin)."""


class AuthStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.AUTH_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock, self._conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    # ------------------------------------------------------------ users
    def users(self) -> list[dict]:
        return [_user(u) for u in self._run(f"SELECT {USER_COLS} FROM users ORDER BY username")]

    def user(self, user_id: int) -> dict | None:
        rows = self._run(f"SELECT {USER_COLS} FROM users WHERE id = ?", (user_id,))
        return _user(rows[0]) if rows else None

    def count_users(self) -> int:
        return self._run("SELECT COUNT(*) AS n FROM users")[0]["n"]

    def create_user(self, username: str, password: str, role: str, display_name: str | None = None) -> dict:
        username = username.strip()
        if not username or len(username) > 40 or not all(ch.isalnum() or ch in "._-" for ch in username):
            raise AuthError("username must be 1-40 letters, digits, dots, dashes or underscores")
        _check_role(role)
        _check_password(password)
        try:
            self._run("INSERT INTO users (username, display_name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                      (username, (display_name or "").strip() or None, role, hash_password(password), now()))
        except sqlite3.IntegrityError:
            raise AuthError(f"username '{username}' is already taken") from None
        return next(u for u in self.users() if u["username"].lower() == username.lower())

    def update_user(self, user_id: int, *, role: str | None = None, active: bool | None = None,
                    password: str | None = None, display_name: str | None = None) -> dict:
        user = self.user(user_id)
        if user is None:
            raise KeyError(user_id)
        if role is not None:
            _check_role(role)
        losing_admin = user["role"] == "admin" and user["active"] and ((role is not None and role != "admin") or active is False)
        if losing_admin and self._active_admins() <= 1:
            raise AuthError("this is the only active admin; make another admin first")
        sets, args = [], []
        if role is not None:
            sets.append("role = ?"), args.append(role)
        if active is not None:
            sets.append("active = ?"), args.append(int(active))
        if display_name is not None:
            sets.append("display_name = ?"), args.append(display_name.strip() or None)
        if password is not None:
            _check_password(password)
            sets.append("password_hash = ?"), args.append(hash_password(password))
        if sets:
            self._run(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*args, user_id))
        if active is False or password is not None or role is not None:
            self._run("DELETE FROM sessions WHERE user_id = ?", (user_id,))  # sign them out everywhere
        return self.user(user_id)

    def _active_admins(self) -> int:
        return self._run("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND active = 1")[0]["n"]

    def check_login(self, username: str, password: str) -> dict | None:
        rows = self._run("SELECT id, password_hash, active FROM users WHERE username = ?", (username.strip(),))
        if not rows:
            verify_password(password, hash_password("timing-equaliser"))  # same work whether or not the user exists
            return None
        row = rows[0]
        if not verify_password(password, row["password_hash"]) or not row["active"]:
            return None
        self._run("UPDATE users SET last_login_at = ? WHERE id = ?", (now(), row["id"]))
        return self.user(row["id"])

    # ------------------------------------------------------------ sessions
    def new_session(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=config.SESSION_HOURS)
        self._run("DELETE FROM sessions WHERE expires_at < ?", (now(),))
        self._run("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                  (_token_hash(token), user_id, now(), expires.isoformat(timespec="seconds")))
        return token

    def session_user(self, token: str) -> dict | None:
        rows = self._run(f"SELECT {', '.join('u.' + c.strip() for c in USER_COLS.split(','))} FROM sessions s JOIN users u ON u.id = s.user_id "
                         "WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1", (_token_hash(token), now()))
        return _user(rows[0]) if rows else None

    def end_session(self, token: str) -> None:
        self._run("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))

    # ------------------------------------------------------------ audit
    def log(self, action: str, user: dict | None = None, *, target: str | None = None, unmasked: bool = False,
            ip: str | None = None, detail: str | None = None, username: str | None = None) -> None:
        self._run("INSERT INTO audit (ts, username, role, action, target, unmasked, ip, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  (now(), (user or {}).get("username") or username, (user or {}).get("role"), action, target, int(unmasked), ip, detail))

    def audit(self, limit: int = 100, offset: int = 0, username: str | None = None, action: str | None = None) -> dict:
        where, args = [], []
        if username:
            where.append("username = ? COLLATE NOCASE"), args.append(username)
        if action:
            where.append("action = ?"), args.append(action)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        total = self._run(f"SELECT COUNT(*) AS n FROM audit {clause}", tuple(args))[0]["n"]
        items = self._run(f"SELECT * FROM audit {clause} ORDER BY id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
        for i in items:
            i["unmasked"] = bool(i["unmasked"])
        return {"total": total, "items": items}


def _user(row: dict) -> dict:
    return {**row, "active": bool(row["active"])}


def _check_role(role: str) -> None:
    if role not in ROLES:
        raise AuthError(f"role must be one of {', '.join(ROLES)}")


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise AuthError(f"password must be at least {MIN_PASSWORD_LEN} characters")


_store: AuthStore | None = None


def get_auth_store() -> AuthStore:
    global _store
    if _store is None:
        _store = AuthStore()
        bootstrap_admin(_store)
    return _store


def set_auth_store(store: AuthStore | None) -> None:
    """Used by tests to point the API at a temporary user database."""
    global _store
    _store = store


def bootstrap_admin(store: AuthStore) -> None:
    """Create the first admin from TRACE360_ADMIN_USER / TRACE360_ADMIN_PASSWORD when no user exists yet."""
    if store.count_users() == 0 and config.ADMIN_USER and config.ADMIN_PASSWORD:
        store.create_user(config.ADMIN_USER, config.ADMIN_PASSWORD, "admin", "Administrator")
        store.log("user_create", username="system", target=config.ADMIN_USER, detail="first admin from environment")
