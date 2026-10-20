import pandas as pd
import pytest

from app.graph.builder import build_edges, build_graph, node_table
from app.graph.centrality import centrality, network_scores
from app.graph.communities import core_graph, detect_rings, ring_cytoscape
from app.graph.money_trail import money_trail
from app.ingestion.loader import load_all


@pytest.fixture
def graph_parts(raw_dir):
    txns, accounts = load_all(raw_dir)
    edges = build_edges(txns, accounts)
    nodes = node_table(edges, accounts, txns)
    g = build_graph(edges, nodes)
    return txns, accounts, edges, nodes, g


def test_edge_directions(graph_parts):
    _, _, edges, _, g = graph_parts
    # CR: counterparty -> account ; DR: account -> counterparty
    assert g.has_edge("upi:ramesh.kuma", "SOA2") and g.has_edge("upi:ramesh.kuma", "SOA7")
    assert g.has_edge("SOA7", "ifsc:TEST0000002:mule next")
    e = g["upi:ramesh.kuma"]["SOA7"]
    assert e["count"] == 1 and e["first_ts"] == pd.Timestamp("2020-12-17 09:00:00")


def test_subject_account_alias():
    txns = pd.DataFrame({
        "account_id": ["SOA2"], "direction": ["DR"], "amount": [10.0], "txn_ts": [pd.NaT],
        "counterparty_key": ["acct:999988887777"], "counterparty_type": ["account"], "counterparty_bank": [None],
    })
    accounts = pd.DataFrame({"account_id": ["SOA2", "SOA7"], "account_number": ["1111222233", "999988887777"]})
    edges = build_edges(txns, accounts)
    assert edges[["src", "dst"]].values.tolist() == [["SOA2", "SOA7"]]


def test_rings_and_scores(graph_parts):
    _, accounts, edges, nodes, g = graph_parts
    core = core_graph(g, nodes)
    assert set(core.nodes) >= {"SOA2", "SOA7", "upi:ramesh.kuma", "upi:9876543210"}
    members, rings = detect_rings(core, set(accounts["account_id"]))
    assert len(rings) == 1 and rings.iloc[0]["subject_accounts"] == ["SOA2", "SOA7"]
    cent = centrality(g, core)
    net = network_scores(accounts, nodes, edges, cent, members, rings).set_index("account_id")
    assert net.loc["SOA2", "shared_counterparties"] == 3
    assert net.loc["SOA2", "ring_id"] == "R1"
    assert net.loc["SOA2", "network_score"] > net.loc["SOA14", "network_score"]
    assert net.loc["SOA14", "sub_pagerank"] == 0  # isolated
    cy = ring_cytoscape(core, members, "R1")
    assert len(cy["nodes"]) == 5 and all({"source", "target", "amount"} <= set(e["data"]) for e in cy["edges"])


def test_rings_are_deterministic(graph_parts):
    _, accounts, _, nodes, g = graph_parts
    runs = [detect_rings(core_graph(g, nodes), set(accounts["account_id"]))[1]["subject_accounts"].tolist() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_money_trail_cross_account(graph_parts):
    g = graph_parts[4]
    back = money_trail(g, "SOA2", hops=2, direction="backward")
    # payers have no recorded inflow, so the backward trail stops at them
    assert back and all(p["hops"] == 1 and p["nodes"][1].startswith(("upi:", "ifsc:")) for p in back)
    fwd = money_trail(g, "upi:ramesh.kuma", hops=2, direction="forward")
    assert {p["nodes"][-1] for p in fwd} >= {"SOA2", "SOA7"}
    two_hop = [p for p in fwd if p["hops"] == 2]
    assert two_hop and two_hop[0]["nodes"][1] == "SOA7"  # SOA2 has no outflow to these nodes
    with pytest.raises(KeyError):
        money_trail(g, "nope")


def test_money_trail_respects_time():
    import networkx as nx
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=100.0, count=1, first_ts=pd.Timestamp("2021-01-02"), last_ts=pd.Timestamp("2021-01-02"))
    g.add_edge("B", "C", amount=90.0, count=1, first_ts=pd.Timestamp("2021-01-01"), last_ts=pd.Timestamp("2021-01-01"))  # before
    g.add_edge("B", "D", amount=80.0, count=1, first_ts=pd.Timestamp("2021-01-03"), last_ts=pd.Timestamp("2021-01-03"))
    ends = {p["nodes"][-1] for p in money_trail(g, "A", hops=2)}
    assert ends == {"B", "D"}
    assert {p["nodes"][-1] for p in money_trail(g, "D", hops=2, direction="backward")} == {"B", "A"}


def test_money_trail_prefers_nodes_it_can_continue_through():
    import networkx as nx
    g = nx.DiGraph()
    g.add_edge("A", "X", amount=500.0, count=1)  # X also receives from B but sends nothing on
    g.add_edge("B", "X", amount=500.0, count=1)
    g.add_edge("A", "Y", amount=10.0, count=1)
    g.add_edge("Y", "C", amount=10.0, count=1)
    paths = money_trail(g, "A", hops=2, branching=1)
    assert [p["nodes"] for p in paths] == [["A", "Y"], ["A", "Y", "C"]]
