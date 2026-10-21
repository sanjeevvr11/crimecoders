"""Money trail as one merged graph, for the investigation view.

money_trail() returns individual paths. The investigation screen needs them
merged: every account or counterparty once, placed by hop distance from the
starting account (negative = money came from there, positive = money went
there), every transfer once, and the chains that reach another investigated
account called out, because those are the cross-account layering chains.
"""
from __future__ import annotations

import networkx as nx

from app.graph.money_trail import money_trail


def _chain_kind(nodes: list[str], subjects: set[str]) -> str:
    """'cross-account' if the path reaches another investigated account, else 'exit'."""
    return "cross-account" if any(n in subjects for n in nodes[1:]) else "exit"


def _edge(g: nx.DiGraph, u: str, v: str, hop: int, direction: str, link: str) -> dict:
    d = g[u][v]
    return {"source": u, "target": v, "amount": d["amount"], "count": d["count"],
            "first_ts": d.get("first_ts"), "last_ts": d.get("last_ts"), "hop": hop, "direction": direction, "link": link}


def _add_shared_links(g, start, subjects, nodes, edges, chains, limit) -> None:
    """Counterparties one hop from `start` that also pay or are paid by other investigated accounts."""
    cands = []
    for cp in g.predecessors(start):  # paid into start
        others = [s for s in g.successors(cp) if s in subjects and s != start]
        if others:
            cands.append((g[cp][start]["amount"], cp, "backward", others))
    for cp in g.successors(start):  # was paid by start
        others = [s for s in g.predecessors(cp) if s in subjects and s != start]
        if others:
            cands.append((g[start][cp]["amount"], cp, "forward", others))
    for amount, cp, d, others in sorted(cands, key=lambda c: (-c[0], c[1]))[:limit]:
        sign = 1 if d == "forward" else -1
        if cp not in nodes or abs(nodes[cp]["level"]) > 1:
            nodes[cp] = {"level": sign, "amount_in": 0.0, "amount_out": 0.0}
        first = (start, cp) if d == "forward" else (cp, start)
        edges.setdefault(first, _edge(g, *first, hop=1, direction=d, link="trail"))
        for other in others:
            nodes.setdefault(other, {"level": 0, "amount_in": 0.0, "amount_out": 0.0})
            pair = (other, cp) if d == "forward" else (cp, other)
            edges.setdefault(pair, _edge(g, *pair, hop=1, direction=d, link="shared"))
            e1, e2 = edges[first], edges[pair]
            ts = [t for t in (e1["first_ts"], e1["last_ts"], e2["first_ts"], e2["last_ts"]) if t is not None]
            chains.append({
                "direction": d, "kind": "shared", "hops": 2, "amount": min(e1["amount"], e2["amount"]),
                "nodes": [start, cp, other], "first_ts": min(ts, default=None), "last_ts": max(ts, default=None),
            })


def trail_graph(
    g: nx.DiGraph,
    start: str,
    subjects: set[str],
    hops: int = 3,
    direction: str = "both",
    max_paths: int = 120,
    shared: int = 12,
) -> dict:
    """Merge forward and/or backward trail paths from `start` into nodes, edges and chains.

    nodes: {node_id: {level, amount_in, amount_out, circular}}, level = signed hop
    distance; circular = reached both forward and backward (money goes round).
    edges: {(u, v): {amount, count, first_ts, last_ts, hop, direction, link}}.
    chains: the paths, longest and largest first, with kind cross-account / shared / exit.

    `shared` adds up to that many direct counterparties of `start` that also
    deal with other investigated accounts (the same payer funding several mule
    accounts, or the same payee draining them). Those accounts sit at level 0
    beside `start`, linked with link='shared'.
    """
    dirs = ["backward", "forward"] if direction == "both" else [direction]
    nodes: dict[str, dict] = {start: {"level": 0, "amount_in": 0.0, "amount_out": 0.0}}
    edges: dict[tuple[str, str], dict] = {}
    chains: list[dict] = []
    seen: dict[str, set[str]] = {"forward": set(), "backward": set()}
    per_dir = max(1, max_paths // len(dirs))
    for d in dirs:
        sign = 1 if d == "forward" else -1
        for p in money_trail(g, start, hops=hops, direction=d, max_paths=per_dir):
            seen[d].update(p["nodes"][1:])
            for i, n in enumerate(p["nodes"][1:], start=1):
                cur = nodes.get(n)
                if cur is None or abs(cur["level"]) > i:
                    nodes[n] = {"level": sign * i, "amount_in": 0.0, "amount_out": 0.0}
            for i, e in enumerate(p["edges"], start=1):
                key = (e["source"], e["target"])
                if key not in edges or edges[key]["hop"] > i:
                    edges[key] = {**e, "hop": i, "direction": d, "link": "trail"}
            chains.append({
                "direction": d,
                "nodes": p["nodes"],
                "hops": p["hops"],
                "amount": p["total_amount"],
                "kind": _chain_kind(p["nodes"], subjects),
                "first_ts": min((e["first_ts"] for e in p["edges"] if e["first_ts"] is not None), default=None),
                "last_ts": max((e["last_ts"] for e in p["edges"] if e["last_ts"] is not None), default=None),
            })
    if shared:
        _add_shared_links(g, start, subjects, nodes, edges, chains, shared)
    circular = seen["forward"] & seen["backward"]
    for n, d in nodes.items():
        d["circular"] = n in circular
    for (u, v), e in edges.items():
        nodes[u]["amount_out"] += e["amount"]
        nodes[v]["amount_in"] += e["amount"]
    # a path that is a prefix of a longer one adds nothing to the chain list
    keep = []
    seqs = {tuple(c["nodes"]) for c in chains}
    for c in chains:
        t = tuple(c["nodes"])
        if any(len(o) > len(t) and o[: len(t)] == t for o in seqs):
            continue
        keep.append(c)
    order = {"cross-account": 0, "shared": 1, "exit": 2}
    keep.sort(key=lambda c: (order[c["kind"]], -c["hops"], -c["amount"]))
    return {"nodes": nodes, "edges": edges, "chains": keep}
