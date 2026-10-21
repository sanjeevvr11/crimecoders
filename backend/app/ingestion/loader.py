"""Load every N_SOA.xls(x) statement into the canonical transactions table."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import duckdb
import pandas as pd

from app import config
from app.ingestion.adapters.base import SourceContext
from app.ingestion.layout_detector import detect_layout
from app.ingestion.schema import ACCOUNT_COLUMNS, validate

log = logging.getLogger(__name__)


def discover_files(raw_dir: Path) -> list[tuple[int, Path]]:
    pattern = re.compile(config.RAW_FILE_PATTERN, re.IGNORECASE)
    found = []
    for path in raw_dir.iterdir():
        if path.name.startswith("~$"):  # Excel lock files
            continue
        m = pattern.match(path.name)
        if m:
            found.append((int(m.group(1)), path))
    return sorted(found)


def load_file(file_no: int, path: Path) -> tuple[list[pd.DataFrame], list[dict]]:
    txns, accounts = [], []
    xl = pd.ExcelFile(path)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, dtype=str)
        df.columns = [str(c).strip() for c in df.columns]
        if df.empty:
            continue
        adapter = detect_layout(df)()
        res = adapter.to_canonical(df, SourceContext(file_no, path.name, sheet))
        txns.append(res.transactions)
        accounts.append(res.account)
        log.info("%s [%s] -> %s, %d rows", path.name, sheet, adapter.name, len(res.transactions))
    return txns, accounts


def load_all(raw_dir: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_dir = raw_dir or config.RAW_DIR
    files = discover_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"no N_SOA.xls/.xlsx statements found in {raw_dir}")
    all_txns, all_accounts = [], []
    for file_no, path in files:
        t, a = load_file(file_no, path)
        all_txns += t
        all_accounts += a
    txns = pd.concat(all_txns, ignore_index=True)
    validate(txns)
    accounts = pd.DataFrame(all_accounts, columns=ACCOUNT_COLUMNS)
    if accounts["account_id"].duplicated().any():
        # multiple sheets in one file share the account id; merge them
        accounts = accounts.groupby("account_id", as_index=False).agg(
            {**{c: "first" for c in ACCOUNT_COLUMNS if c not in ("account_id", "n_rows")}, "n_rows": "sum"}
        )[ACCOUNT_COLUMNS]
    return txns, accounts


def write_outputs(tables: dict[str, pd.DataFrame], processed_dir: Path | None = None, db_path: Path | None = None) -> None:
    processed_dir = processed_dir or config.PROCESSED_DIR
    db_path = db_path or config.DUCKDB_PATH
    processed_dir.mkdir(parents=True, exist_ok=True)
    tables = {k: v for k, v in tables.items() if len(v.columns)}  # nothing to store for column-less frames
    for name, df in tables.items():
        df.to_parquet(processed_dir / f"{name}.parquet", index=False)
    con = duckdb.connect(str(db_path))
    try:
        for name, df in tables.items():
            con.register("__df", df)
            con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM __df')
            con.unregister("__df")
    finally:
        con.close()
