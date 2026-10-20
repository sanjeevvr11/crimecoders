"""DuckDB access for ad-hoc analysis. The API itself serves the Parquet outputs."""
from __future__ import annotations

from pathlib import Path

import duckdb

from app import config


def connect(path: Path | None = None, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or config.DUCKDB_PATH), read_only=read_only)


def query(sql: str, path: Path | None = None):
    with connect(path) as con:
        return con.execute(sql).df()
