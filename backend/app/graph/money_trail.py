"""Hop-limited money trail from any node, forward or backward.

Where both edges carry timestamps, a hop is only followed if the next edge's
activity is not entirely before the previous edge started (money cannot move
on before it arrives).
"""
from __future__ import annotations

from collections import deque

import networkx as nx

from app import config


def _time_ok(prev: dict | None, nxt: dict, direction: str) -> bool:
    if prev is None:
        return True
    if direction == "forward":
        a, b = prev.get("first_ts"), nxt.get("last_ts")
        return a is None or b is None or b >= a
    a, b = prev.get("last_ts"), nxt.get("first_ts")  # backward: next edge happened earlier
    return a is None or b is None or b <= a


def money_trail(
    g: nx.DiGraph,
    start: str,
    hops: int = 2,
    direction: str = "forward",
    max_paths: int | None = None,
    branching: int = 10,
) -> list[dict]:
    """BFS from `start`. direction: forward (where money went), backward (where it
    came from) or both. Returns paths as {nodes, edges, total_amount, hops}.

    At most `branching` neighbours are expanded per node: those the trail can
    continue through first, then by amount, so multi-hop paths are not crowded
    out by a hub's many one-hop payees."""
    if start not in g:
        raise KeyError(start)
    hops = max(1, min(hops, config.TRAIL_MAX_HOPS))
    max_paths = max_paths or config.TRAIL_MAX_PATHS
    if direction == "both":
        return (money_trail(g, start, hops, "forward", max_paths, branching)
                + money_trail(g, start, hops, "backward", max_paths, branching))[:max_paths]
    if direction not in ("forward", "backward"):
        raise ValueError("direction must be forward, backward or both")

    paths: list[dict] = []
    queue: deque = deque([([start], [])])
    while queue and len(paths) < max_paths:
        nodes, edges = queue.popleft()
        here = nodes[-1]
        if direction == "forward":
            step, onward, amount = g.successors, g.out_degree, (lambda n: g[here][n]["amount"])
        else:
            step, onward, amount = g.predecessors, g.in_degree, (lambda n: g[n][here]["amount"])
        ranked = sorted(step(here), key=lambda n: (-(onward(n) > 0), -amount(n), n))[:branching]
        for nbr in ranked:
            if nbr in nodes:
                continue
            u, v = (here, nbr) if direction == "forward" else (nbr, here)
            d = g[u][v]
            if not _time_ok(edges[-1] if edges else None, d, direction):
                continue
            edge = {"source": u, "target": v, "amount": d["amount"], "count": d["count"],
                    "first_ts": d.get("first_ts"), "last_ts": d.get("last_ts")}
            new_nodes, new_edges = nodes + [nbr], edges + [edge]
            paths.append({
                "direction": direction,
                "nodes": new_nodes,
                "edges": new_edges,
                "hops": len(new_edges),
                "total_amount": min(e["amount"] for e in new_edges),  # flow bounded by weakest hop
            })
            if len(paths) >= max_paths:
                break
            if len(new_edges) < hops:
                queue.append((new_nodes, new_edges))
    return paths
