from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_store, records
from app.api.txns import sort_by_date, txn_rows
from app.graph.communities import ring_cytoscape
from app.masking import node_label, node_ref
from app.schemas.api import NetworkOverview, NodeConnections, Ring, RingDetail
from app.auth.deps import audited, require_role

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _rings() -> list[dict]:
    rings = get_store().table("rings").copy()
    rings["subject_accounts"] = rings["subject_accounts"].map(list)
    return records(rings)


def _elements(nodes_in: set[str] | None = None, ring_id: str | None = None) -> dict:
    s = get_store()
    subj = s.subject_ids
    members = s.table("nodes")[["node_id", "community", "ring_id"]]
    elements = ring_cytoscape(
        s.core, members, ring_id, nodes_in=nodes_in, graph=s.graph,
        label_fn=lambda n: node_label(n, n in subj),
        id_fn=lambda n: node_ref(n, n in subj),
    )
    ring_of = members.dropna(subset=["ring_id"]).set_index("node_id")["ring_id"].to_dict()
    for el in elements["nodes"]:
        el["data"]["is_subject"] = el["data"]["id"] in subj
        el["data"]["ring_id"] = ring_of.get(el["data"]["id"]) if el["data"]["is_subject"] else None
    return elements


@router.get("/rings", response_model=list[Ring])
def list_rings() -> list[dict]:
    return _rings()


@router.get("/overview", response_model=NetworkOverview)
def network_overview() -> dict:
    """Every investigated account (in a ring or not) and every counterparty shared by 2+ of them."""
    s = get_store()
    elements = _elements(nodes_in=set(s.core.nodes))
    linked = {e["data"][k] for e in elements["edges"] for k in ("source", "target")}
    return {"rings": _rings(), "elements": elements, "n_accounts": len(s.subject_ids),
            "n_unlinked_accounts": len(s.subject_ids - linked)}


@router.get("/rings/{ring_id}", response_model=RingDetail)
def ring_detail(ring_id: str) -> dict:
    rings = [r for r in _rings() if r["ring_id"] == ring_id]
    if not rings:
        raise HTTPException(404, f"unknown ring '{ring_id}'")
    return {"ring": rings[0], "elements": _elements(ring_id=ring_id)}


@router.get("/nodes/{ref}/transactions", response_model=NodeConnections,
            dependencies=[Depends(require_role("investigator")), audited("view_connections", "ref")])
def node_transactions(
    ref: str,
    account: str | None = Query(None, description="only transactions of this investigated account (a clicked link)"),
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    order: Literal["asc", "desc"] = "asc",
) -> dict:
    """Transactions behind a node of the network graph.

    Counterparty (CP-xxxxxxxxxx): every transaction any investigated account made with it.
    Account (SOA7): its transactions with counterparties it shares with other investigated accounts.
    """
    s = get_store()
    node = s.resolve_node(ref)
    subj = s.subject_ids
    if account is not None:
        s.require_account(account)
    tx = s.table("transactions")
    ring_of = s.table("nodes").dropna(subset=["ring_id"]).set_index("node_id")["ring_id"].to_dict()
    core = s.core
    is_subject = node in subj
    if is_subject:
        shared = {n for n in core.neighbors(node) if n not in subj} if node in core else set()
        t = tx.loc[(tx["account_id"] == node) & tx["counterparty_key"].isin(shared)]
        if account is not None:
            shared = {n for n in shared if core.has_edge(n, account)}
            t = t.loc[t["counterparty_key"].isin(shared)]
        others: dict[str, int] = {}
        for n in shared:
            for a in core.neighbors(n):
                if a in subj and a != node:
                    others[a] = others.get(a, 0) + 1
        accounts = []
        for a, k in sorted(others.items(), key=lambda kv: -kv[1]):
            if account is not None and a != account:
                continue
            ta = t.loc[t["counterparty_key"].isin({n for n in shared if core.has_edge(n, a)})]
            accounts.append(_account_row(a, ring_of.get(a), ta, k))
    else:
        t = tx.loc[tx["counterparty_key"] == node]
        if account is not None:
            t = t.loc[t["account_id"] == account]
        accounts = [_account_row(a, ring_of.get(a), g, 1) for a, g in t.groupby("account_id", sort=True)]
        accounts.sort(key=lambda r: -r["n_txns"])
    t = sort_by_date(t, order)
    return {
        "node": {"ref": node_ref(node, is_subject), "label": node_label(node, is_subject)},
        "is_subject": is_subject,
        "ring_id": ring_of.get(node) if is_subject else None,
        "account": account,
        "accounts": accounts,
        "total": int(len(t)), "offset": offset, "limit": limit,
        "transactions": txn_rows(t.iloc[offset: offset + limit], subj, with_account=True),
    }


def _account_row(account_id: str, ring_id: str | None, t, n_shared: int) -> dict:
    return {
        "account_id": account_id, "ring_id": ring_id, "n_txns": int(len(t)),
        "cr_amount": float(t.loc[t["direction"] == "CR", "amount"].sum()),
        "dr_amount": float(t.loc[t["direction"] == "DR", "amount"].sum()),
        "n_shared_counterparties": int(n_shared),
    }
