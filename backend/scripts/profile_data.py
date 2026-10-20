"""Profile the canonical transactions: rows, accounts, dates, parse rate, channels.

Usage (from backend/):  python scripts/profile_data.py
Reads data/processed/transactions.parquet if present, else ingests data/raw.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.ingestion.loader import load_all  # noqa: E402

TOKEN = r"^TXN-[A-Z0-9]{10}$"


def profile(txns: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (src, sheet), g in txns.groupby(["source_file", "source_sheet"], sort=False):
        text = g["raw_narration"].notna() & ~g["raw_narration"].str.match(TOKEN, na=False)
        raw_dates = pd.to_datetime(g["raw_date"], errors="coerce", dayfirst=True, format="mixed")
        rows.append({
            "file": src,
            "sheet": sheet,
            "account_id": g["account_id"].iloc[0],
            "rows": len(g),
            "accounts": g["account_id"].nunique(),
            "time_reliable": bool(g["time_reliable"].any()),
            "ts_valid_%": round(100 * g["txn_ts"].notna().mean(), 1),
            "raw_date_parseable_%": round(100 * raw_dates.notna().mean(), 1),
            "text_narr_%": round(100 * text.mean(), 1),
            "parsed_%": round(100 * (g["channel"] != "UNKNOWN").mean(), 1),
            "counterparty_%": round(100 * g["counterparty_key"].notna().mean(), 1),
            "cr_%": round(100 * (g["direction"] == "CR").mean(), 1),
        })
    out = pd.DataFrame(rows)
    out["_n"] = out["file"].str.extract(r"^(\d+)").astype(int)
    return out.sort_values("_n").drop(columns="_n")


def main() -> None:
    path = config.PROCESSED_DIR / "transactions.parquet"
    txns = pd.read_parquet(path) if path.exists() else load_all()[0]
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(profile(txns).to_string(index=False))
    print(f"\nTotal: {len(txns):,} rows, {txns['account_id'].nunique()} accounts")
    text = ~txns["raw_narration"].str.match(TOKEN, na=False)
    print(f"Narrations with real text: {text.sum():,}; of those parsed: {100 * (txns.loc[text, 'channel'] != 'UNKNOWN').mean():.2f}%")
    print("\nChannel mix:")
    print(txns["channel"].value_counts().to_string())
    print("\nChannel mix by account (text narrations only):")
    print(pd.crosstab(txns.loc[text, "account_id"], txns.loc[text, "channel"]).to_string())


if __name__ == "__main__":
    main()
