"""Write the API contract to docs/openapi.json.

The frontend's TypeScript types are generated from this file
(`npm run gen:api` in frontend/). Re-run this after changing any route or
response model; tests/test_openapi.py fails while the file is stale.

Usage (from backend/):  python scripts/export_openapi.py [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check", action="store_true", help="exit 1 if docs/openapi.json is out of date")
    args = p.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"{OUT} is out of date: run python scripts/export_openapi.py")
            sys.exit(1)
        print(f"{OUT} is up to date")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT} ({len(app.openapi()['paths'])} paths)")


if __name__ == "__main__":
    main()
