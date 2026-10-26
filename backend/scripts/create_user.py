"""Create a Trace360 user, or the three demo users.

Usage (from backend/):
  python scripts/create_user.py --username priya --role investigator        # asks for the password
  python scripts/create_user.py --demo                                       # admin, investigator, viewer

--demo makes one user per role with the fixed demo passwords listed in the
README (or resets them to those if the users already exist), so anyone running
the app locally can sign in. Change them in the Users tab before deploying.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth.store import ROLES, AuthError, AuthStore  # noqa: E402

# public demo passwords (also in the README): for local use only, change them before deploying
DEMO = (("admin", "admin", "Demo Admin", "Trace360-Admin"),
        ("investigator", "investigator", "Demo Investigator", "Trace360-Investigator"),
        ("viewer", "viewer", "Demo Viewer", "Trace360-Viewer"))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--username")
    p.add_argument("--role", choices=ROLES)
    p.add_argument("--name", help="display name")
    p.add_argument("--demo", action="store_true", help="create the three demo users")
    args = p.parse_args()
    store = AuthStore()
    if args.demo:
        existing = {u["username"].lower(): u for u in store.users()}
        lines = []
        for username, role, name, password in DEMO:
            if username in existing:  # same user name: put back the demo role and password, and allow sign-in
                store.update_user(existing[username]["id"], role=role, active=True, password=password)
                store.log("user_update", username="setup script", target=username, detail="reset to demo password")
            else:
                store.create_user(username, password, role, name)
                store.log("user_create", username="setup script", target=username, detail=f"role {role}")
            lines.append(f"{username:<13} {role:<13} {password}")
        print("user          role          password\n" + "\n".join(lines) + "\n\nDemo passwords are public (README): change them before deploying.")
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
