"""Create a Trace360 user, or the three demo users.

Usage (from backend/):
  python scripts/create_user.py --username priya --role investigator        # asks for the password
  python scripts/create_user.py --demo                                       # admin, investigator, viewer

--demo makes one user per role with random passwords, prints them once and
saves them to data/demo_users.txt (git-ignored). Passwords never go in the repo.
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.auth.store import ROLES, AuthError, AuthStore  # noqa: E402

DEMO = (("admin", "admin", "Demo Admin"), ("investigator", "investigator", "Demo Investigator"), ("viewer", "viewer", "Demo Viewer"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--username")
    p.add_argument("--role", choices=ROLES)
    p.add_argument("--name", help="display name")
    p.add_argument("--demo", action="store_true", help="create the three demo users")
    args = p.parse_args()
    store = AuthStore()
    if args.demo:
        lines = []
        for username, role, name in DEMO:
            password = secrets.token_urlsafe(9)
            try:
                store.create_user(username, password, role, name)
            except AuthError as e:
                print(f"skipped {username}: {e}")
                continue
            store.log("user_create", username="setup script", target=username, detail=f"role {role}")
            lines.append(f"{username:<13} {role:<13} {password}")
        if lines:
            out = config.DATA_DIR / "demo_users.txt"
            with out.open("a") as f:
                f.write("\n".join(lines) + "\n")
            print("user          role          password\n" + "\n".join(lines) + f"\n\nSaved to {out} (not committed).")
        return
    if not (args.username and args.role):
        p.error("give --username and --role, or --demo")
    password = getpass.getpass("Password (8+ characters): ")
    if password != getpass.getpass("Again: "):
        sys.exit("passwords differ")
    try:
        store.create_user(args.username, password, args.role, args.name)
    except AuthError as e:
        sys.exit(str(e))
    store.log("user_create", username="setup script", target=args.username, detail=f"role {args.role}")
    print(f"created {args.username} ({args.role}) in {store.path}")


if __name__ == "__main__":
    main()
