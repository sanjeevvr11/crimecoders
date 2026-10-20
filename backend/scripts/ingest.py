"""Ingest data/raw statements into data/processed/transactions.parquet + DuckDB.

Usage (from backend/):  python scripts/ingest.py [--raw-dir PATH]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.ingestion.loader import load_all, write_outputs  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=config.RAW_DIR)
    args = p.parse_args()
    txns, accounts = load_all(args.raw_dir)
    write_outputs({"transactions": txns, "accounts": accounts})
    print(f"{len(txns):,} transactions from {len(accounts)} accounts -> {config.PROCESSED_DIR} and {config.DUCKDB_PATH}")


if __name__ == "__main__":
    main()
