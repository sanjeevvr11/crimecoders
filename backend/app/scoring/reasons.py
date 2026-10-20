"""Top-N human-readable reasons per account, ranked by score contribution."""
from __future__ import annotations

import pandas as pd

from app import config


def network_reasons(net_row: pd.Series) -> list[tuple[float, str, str]]:
    """(contribution, source, text) for the network side."""
    w = config.NETWORK_WEIGHTS
    scale = config.SCORE_WEIGHTS["network"] / sum(w.values())
    out = []
    if net_row.get("shared_counterparties", 0) > 0:
        out.append((scale * w["shared_counterparties"] * net_row["sub_shared"], "network",
                    f"Shares {int(net_row['shared_counterparties'])} counterparties with other investigated accounts"))
    if net_row.get("direct_subject_links", 0) > 0:
        out.append((scale * w["shared_counterparties"] * net_row["sub_shared"], "network",
                    f"Transacts directly with {int(net_row['direct_subject_links'])} other investigated account(s)"))
    if isinstance(net_row.get("ring_id"), str):
        out.append((scale * w["ring_membership"] * net_row["sub_ring"], "network",
                    f"Member of ring {net_row['ring_id']} with {int(net_row['ring_subjects'])} investigated accounts"))
    if net_row.get("sub_betweenness", 0) >= 0.5:
        out.append((scale * w["betweenness"] * net_row["sub_betweenness"], "network",
                    "Acts as a bridge between other accounts in the network (high betweenness)"))
    if net_row.get("sub_pagerank", 0) >= 0.7:
        out.append((scale * w["pagerank"] * net_row["sub_pagerank"], "network",
                    "Central destination of money flow in the network (high PageRank)"))
    return out


def top_reasons(account_id: str, indicators: pd.DataFrame, network: pd.DataFrame, n: int | None = None) -> list[dict]:
    n = n or config.TOP_REASONS
    ind = indicators.loc[(indicators["account_id"] == account_id) & indicators["reason"].notna()]
    total_w = indicators.loc[indicators["account_id"] == account_id, "weight"].sum() or 1.0
    scale = config.SCORE_WEIGHTS["indicator"]
    cands = [(scale * r.weight * r.subscore / total_w, "indicator", r.reason) for r in ind.itertuples(index=False)]
    net = network.loc[network["account_id"] == account_id]
    if len(net):
        cands += network_reasons(net.iloc[0])
    cands.sort(key=lambda x: -x[0])
    return [{"source": s, "text": t, "contribution": round(100 * c, 1)} for c, s, t in cands[:n]]


def reasons_table(accounts: pd.DataFrame, indicators: pd.DataFrame, network: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for aid in accounts["account_id"]:
        for rank, r in enumerate(top_reasons(aid, indicators, network), start=1):
            rows.append({"account_id": aid, "rank": rank, **r})
    return pd.DataFrame(rows, columns=["account_id", "rank", "source", "text", "contribution"])
