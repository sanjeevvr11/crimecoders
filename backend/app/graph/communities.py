"""Ring detection with Louvain on the shared-counterparty core.

Counterparties linked to a single subject account cannot change which ring
that account belongs to, so Louvain runs on the core: subject accounts plus
counterparties touching two or more subjects.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from app import config


def core_graph(g: nx.DiGraph, nodes: pd.DataFrame) -> nx.Graph:
    keep = set(nodes.loc[nodes["is_subject"] | (nodes["n_subject_links"] >= 2), "node_id"])
    core = nx.Graph()
    # sorted: set order varies with hash randomisation and Louvain depends on node order
    core.add_nodes_from(sorted(n for n in keep if n in g))
    for u, v, d in g.edges(data=True):
        if u in keep and v in keep:
            w = float(np.log1p(d["count"]))
            if core.has_edge(u, v):
                core[u][v]["weight"] += w
                core[u][v]["amount"] += d["amount"]
            else:
                core.add_edge(u, v, weight=w, amount=d["amount"])
    return core


def detect_rings(core: nx.Graph, subjects: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (membership: node_id -> community/ring, rings summary)."""
    if core.number_of_edges() == 0:
        comms = [{n} for n in core.nodes]
    else:
        comms = nx.community.louvain_communities(core, weight="weight", resolution=config.LOUVAIN_RESOLUTION, seed=config.GRAPH_SEED)
    comms = sorted(comms, key=lambda c: (-len(c & subjects), -len(c), sorted(c)[0]))
    member_rows, ring_rows = [], []
    ring_no = 0
    for i, comm in enumerate(comms):
        subj = sorted(comm & subjects)
        ring_id = None
        if len(subj) >= config.RING_MIN_SUBJECTS:
            ring_no += 1
            ring_id = f"R{ring_no}"
            sub = core.subgraph(comm)
            ring_rows.append({
                "ring_id": ring_id,
                "subject_accounts": subj,
                "n_subjects": len(subj),
                "n_shared_counterparties": len(comm) - len(subj),
                "n_nodes": len(comm),
                "n_edges": sub.number_of_edges(),
                "total_amount": float(sum(d["amount"] for _, _, d in sub.edges(data=True))),
            })
        for n in comm:
            member_rows.append({"node_id": n, "community": i, "ring_id": ring_id})
    members = pd.DataFrame(member_rows, columns=["node_id", "community", "ring_id"])
    rings = pd.DataFrame(ring_rows, columns=["ring_id", "subject_accounts", "n_subjects", "n_shared_counterparties", "n_nodes", "n_edges", "total_amount"])
    return members, rings


def ring_cytoscape(core: nx.Graph, members: pd.DataFrame, ring_id: str | None, label_fn=lambda n: n, id_fn=lambda n: n,
                   nodes_in: set[str] | None = None, graph: nx.DiGraph | None = None) -> dict:
    """Cytoscape.js elements for one ring, or for `nodes_in` when given. `label_fn`/`id_fn` let the API
    mask ids. With the directed `graph`, edges also carry their transaction count."""
    if nodes_in is None:
        nodes_in = set(members.loc[members["ring_id"] == ring_id, "node_id"])
    sub = core.subgraph(nodes_in)
    elements = {"nodes": [], "edges": []}
    for n, d in sub.nodes(data=True):
        elements["nodes"].append({"data": {"id": id_fn(n), "label": label_fn(n), "is_subject": not n.count(":"), "degree": sub.degree(n)}})
    for u, v, d in sub.edges(data=True):
        data = {"id": f"{id_fn(u)}__{id_fn(v)}", "source": id_fn(u), "target": id_fn(v), "amount": round(d["amount"], 2)}
        if graph is not None:
            data["count"] = sum(graph[a][b]["count"] for a, b in ((u, v), (v, u)) if graph.has_edge(a, b))
        elements["edges"].append({"data": data})
    return elements
