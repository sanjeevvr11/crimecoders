"""The committed API contract (docs/openapi.json) must match the live app."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from export_openapi import OUT, render  # noqa: E402


def test_openapi_contract_is_current():
    assert OUT.exists(), "docs/openapi.json missing: run python scripts/export_openapi.py"
    assert OUT.read_text() == render(), "API changed: run python scripts/export_openapi.py, then npm run gen:api in frontend/"


def test_every_json_route_has_a_response_model():
    import json

    spec = json.loads(OUT.read_text())
    untyped = []
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            content = op["responses"]["200"].get("content", {})
            if "application/json" in content and content["application/json"].get("schema") in ({}, None):
                untyped.append(f"{method.upper()} {path}")
    assert not untyped, f"routes without a response model: {untyped}"
