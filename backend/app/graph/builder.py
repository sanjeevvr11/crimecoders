"""Directed money-flow graph: subject accounts <-> counterparties.

CR rows become counterparty -> account edges, DR rows account -> counterparty.
Counterparty keys of the form acct:<number> that equal a subject account's
(constant) account number are folded into that subject node. Per-row account
numbers in anonymised files are never used for linking.
"""
from __future__ import annotations

import networkx as nx
import pandas as pd

EDGE_COLUMNS = ["src", "dst", "amount", "count", "first_ts", "last_ts", "account_id", "direction"]


def resolve_counterparties(txns: pd.DataFrame, accounts: pd.DataFrame) -> pd.Series:
    alias = {
        f"acct:{num}": aid
        for aid, num in accounts[["account_id", "account_number"]].dropna().itertuples(index=False)
    }
    return txns["counterparty_key"].map(lambda k: alias.get(k, k) if isinstance(k, str) else k)


def build_edges(txns: pd.DataFrame, accounts: pd.DataFrame) -> pd.DataFrame:
    t = txns.loc[txns["counterparty_key"].notna(), ["account_id", "direction", "amount", "txn_ts"]].copy()
    t["cp"] = resolve_counterparties(txns.loc[t.index], accounts)
    t = t.loc[t["cp"] != t["account_id"]]
    is_cr = t["direction"] == "CR"
    t["src"] = t["cp"].where(is_cr, t["account_id"])
    t["dst"] = t["account_id"].where(is_cr, t["cp"])
    edges = (
        t.groupby(["src", "dst", "account_id", "direction"], as_index=False)
        .agg(amount=("amount", "sum"), count=("amount", "size"), first_ts=("txn_ts", "min"), last_ts=("txn_ts", "max"))
    )
    return edges[EDGE_COLUMNS]


def node_table(edges: pd.DataFrame, accounts: pd.DataFrame, txns: pd.DataFrame) -> pd.DataFrame:
    subjects = set(accounts["account_id"])
    cp_meta = (
        txns.dropna(subset=["counterparty_key"])
        .groupby("counterparty_key")
        .agg(counterparty_type=("counterparty_type", "first"), counterparty_bank=("counterparty_bank", "first"))
    )
    ids = pd.unique(pd.concat([edges["src"], edges["dst"], accounts["account_id"]], ignore_index=True))
    nodes = pd.DataFrame({"node_id": ids})
    nodes["is_subject"] = nodes["node_id"].isin(subjects)
    nodes = nodes.merge(cp_meta, how="left", left_on="node_id", right_index=True)
    nodes.loc[nodes["is_subject"], "counterparty_type"] = "subject"
    linked = pd.concat([edges[["src", "account_id"]].rename(columns={"src": "node_id"}),
                        edges[["dst", "account_id"]].rename(columns={"dst": "node_id"})])
    n_subj = linked.groupby("node_id")["account_id"].nunique().rename("n_subject_links")
    nodes = nodes.merge(n_subj, how="left", left_on="node_id", right_index=True)
    nodes["n_subject_links"] = nodes["n_subject_links"].fillna(0).astype(int)
    return nodes


def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame | None = None) -> nx.DiGraph:
    g = nx.DiGraph()
    if nodes is not None:
        for row in nodes.itertuples(index=False):
            g.add_node(row.node_id, is_subject=bool(row.is_subject), type=row.counterparty_type)
    # several (account, direction) groups can share one src->dst pair: merge them
    agg = edges.groupby(["src", "dst"], as_index=False).agg(
        amount=("amount", "sum"), count=("count", "sum"), first_ts=("first_ts", "min"), last_ts=("last_ts", "max")
    )
    for r in agg.itertuples(index=False):
        g.add_edge(
            r.src, r.dst, amount=float(r.amount), count=int(r.count),
            first_ts=None if pd.isna(r.first_ts) else pd.Timestamp(r.first_ts),
            last_ts=None if pd.isna(r.last_ts) else pd.Timestamp(r.last_ts),
        )
    return g
