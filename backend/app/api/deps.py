"""Shared state for the API: processed tables loaded once, graph built lazily."""
from __future__ import annotations

import json
import threading
from functools import cached_property
from pathlib import Path

import networkx as nx
import pandas as pd
from fastapi import HTTPException

from app import config
from app.graph.builder import build_graph
from app.graph.communities import core_graph
from app.masking import node_ref

TABLES = [
    "transactions", "accounts", "account_features", "indicators", "edges", "nodes", "rings",
    "network_scores", "complaints", "complaint_matches", "scores", "reasons", "leads", "alerts",
]


class Store:
    def __init__(self, processed_dir: Path | None = None):
        self.processed_dir = processed_dir or config.PROCESSED_DIR
        self._tables: dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return (self.processed_dir / "stats.json").exists()

    def table(self, name: str) -> pd.DataFrame:
        if name not in self._tables:
            path = self.processed_dir / f"{name}.parquet"
            if not path.exists():
                raise HTTPException(503, f"pipeline output '{name}' missing; POST /api/pipeline/run first")
            self._tables[name] = pd.read_parquet(path)
        return self._tables[name]

    def stats(self) -> dict:
        if not self.ready:
            raise HTTPException(503, "pipeline has not been run; POST /api/pipeline/run first")
        return json.loads((self.processed_dir / "stats.json").read_text())

    @cached_property
    def graph(self) -> nx.DiGraph:
        return build_graph(self.table("edges"), self.table("nodes"))

    @cached_property
    def core(self) -> nx.Graph:
        return core_graph(self.graph, self.table("nodes"))

    @cached_property
    def subject_ids(self) -> set[str]:
        return set(self.table("accounts")["account_id"])

    @cached_property
    def ref_to_node(self) -> dict[str, str]:
        nodes = self.table("nodes")
        return {node_ref(n, s): n for n, s in zip(nodes["node_id"], nodes["is_subject"])}

    def resolve_node(self, ref: str) -> str:
        if ref in self.subject_ids:
            return ref
        node = self.ref_to_node.get(ref)
        if node is None:
            raise HTTPException(404, f"unknown account or node '{ref}'")
        return node

    def require_account(self, account_id: str) -> None:
        if account_id not in self.subject_ids:
            raise HTTPException(404, f"unknown account '{account_id}'")

    def reload(self) -> None:
        with self._lock:
            self._tables.clear()
            for attr in ("graph", "core", "subject_ids", "ref_to_node"):
                self.__dict__.pop(attr, None)


_store: Store | None = None
pipeline_lock = threading.Lock()


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def set_store(store: Store) -> None:
    """Used by tests to point the API at a temporary data directory."""
    global _store
    _store = store


def records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records (NaN -> None, timestamps -> ISO)."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S").where(out[c].notna(), None)
    out = out.astype(object).where(out.notna(), None)
    return out.to_dict(orient="records")
