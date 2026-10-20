"""Centrality measures and the per-account network score."""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from app import config


def centrality(g: nx.DiGraph, core: nx.Graph) -> pd.DataFrame:
    """PageRank on the full flow graph (amount-weighted) and weighted betweenness
    on the shared-counterparty core (exact; the core is small)."""
    pr = nx.pagerank(g, weight="amount") if g.number_of_edges() else {n: 0.0 for n in g}
    # betweenness treats weight as distance: strong ties should be short
    for _, _, d in core.edges(data=True):
        d["distance"] = 1.0 / (1.0 + d["weight"])
    bc = nx.betweenness_centrality(core, weight="distance", normalized=True) if core.number_of_edges() else {}
    df = pd.DataFrame({"node_id": list(g.nodes)})
    df["pagerank"] = df["node_id"].map(pr).fillna(0.0)
    df["betweenness"] = df["node_id"].map(bc).fillna(0.0)
    return df


def _rank_pct(s: pd.Series) -> pd.Series:
    if len(s) <= 1 or s.max() == s.min():
        return pd.Series(0.0, index=s.index)
    return s.rank(pct=True, method="average")


def network_scores(accounts: pd.DataFrame, nodes: pd.DataFrame, edges: pd.DataFrame, cent: pd.DataFrame, members: pd.DataFrame, rings: pd.DataFrame) -> pd.DataFrame:
    subj = accounts[["account_id"]].copy()
    shared = nodes.loc[~nodes["is_subject"] & (nodes["n_subject_links"] >= 2), "node_id"]
    links = edges.loc[edges["src"].isin(shared) | edges["dst"].isin(shared)]
    links = pd.concat([
        links.loc[links["src"].isin(shared), ["account_id", "src"]].rename(columns={"src": "cp"}),
        links.loc[links["dst"].isin(shared), ["account_id", "dst"]].rename(columns={"dst": "cp"}),
    ])
    n_shared = links.groupby("account_id")["cp"].nunique()
    # direct subject <-> subject links count too
    direct = edges.loc[edges["src"].isin(subj["account_id"]) & edges["dst"].isin(subj["account_id"])]
    n_direct = pd.concat([direct["src"], direct["dst"]]).value_counts()

    subj["shared_counterparties"] = subj["account_id"].map(n_shared).fillna(0).astype(int)
    subj["direct_subject_links"] = subj["account_id"].map(n_direct).fillna(0).astype(int)
    subj = subj.merge(cent, how="left", left_on="account_id", right_on="node_id").drop(columns="node_id")
    subj[["pagerank", "betweenness"]] = subj[["pagerank", "betweenness"]].fillna(0.0)
    ring_of = members.dropna(subset=["ring_id"]).set_index("node_id")["ring_id"]
    subj["ring_id"] = subj["account_id"].map(ring_of)
    ring_size = rings.set_index("ring_id")["n_subjects"] if len(rings) else pd.Series(dtype=float)
    subj["ring_subjects"] = subj["ring_id"].map(ring_size).fillna(0).astype(int)

    w = config.NETWORK_WEIGHTS
    sat = config.SHARED_CP_SATURATION
    s_shared = np.minimum(1.0, (subj["shared_counterparties"] + 5 * subj["direct_subject_links"]) / sat)
    # isolated nodes still get teleport PageRank mass; only connected accounts count
    connected = subj["account_id"].isin(pd.concat([edges["src"], edges["dst"]]).unique())
    s_pr = _rank_pct(subj["pagerank"]).where(connected, 0.0)
    s_bc = _rank_pct(subj["betweenness"]).where(subj["betweenness"] > 0, 0.0)
    s_ring = np.where(subj["ring_id"].notna(), np.minimum(1.0, subj["ring_subjects"] / 3.0), 0.0)
    subj["sub_shared"] = s_shared
    subj["sub_pagerank"] = s_pr
    subj["sub_betweenness"] = s_bc
    subj["sub_ring"] = s_ring
    subj["network_score"] = (
        w["shared_counterparties"] * s_shared + w["pagerank"] * s_pr + w["betweenness"] * s_bc + w["ring_membership"] * s_ring
    ) / sum(w.values())
    return subj
