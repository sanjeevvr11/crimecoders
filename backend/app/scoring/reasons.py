"""Top-N human-readable reasons per account, ranked by score contribution."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app import config
from app.scoring.risk_score import base_weights

ROLE_REASON_POINTS = 2.0  # roles describe behaviour; they add context, not score


@dataclass
class MLContext:
    anomaly: pd.DataFrame  # account_id, anomaly_score, flagged_weeks, n_weeks
    window_scores: pd.DataFrame  # account_id, week_start, anomaly_score, is_flagged, ...
    shap_reasons: pd.DataFrame  # account_id, week_start, rank, feature, contribution, reason
    roles: pd.DataFrame  # account_id, role, role_source, role_share
    uplift: dict | None = None  # account_id -> anomaly uplift in score points


def network_reasons(net_row: pd.Series, part_weight: float) -> list[tuple[float, str, str]]:
    """(contribution, source, text) for the network side."""
    w = config.NETWORK_WEIGHTS
    scale = part_weight / sum(w.values())
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


def anomaly_reasons(account_id: str, ml: MLContext) -> list[tuple[float, str, str]]:
    """One reason for the account's most anomalous flagged week, combining its
    top SHAP features; worth the account's anomaly uplift."""
    a = ml.anomaly.loc[ml.anomaly["account_id"] == account_id]
    if a.empty or pd.isna(a.iloc[0]["anomaly_score"]):
        return []
    ws = ml.window_scores.loc[(ml.window_scores["account_id"] == account_id) & ml.window_scores["is_flagged"]]
    if ws.empty:
        return []
    top = ws.loc[ws["anomaly_score"].idxmax()]
    sr = ml.shap_reasons.loc[(ml.shap_reasons["account_id"] == account_id) & (ml.shap_reasons["week_start"] == top["week_start"])]
    if sr.empty:
        return []
    week = pd.Timestamp(top["week_start"]).date()
    pct = max(1, round(100 * (1 - top["anomaly_pct"])))
    flagged = int(a.iloc[0]["flagged_weeks"])
    why = "; ".join(sr.sort_values("rank")["reason"])
    text = f"Week of {week} is in the top {pct}% most unusual weeks ({flagged} flagged week(s)): {why}"
    return [((ml.uplift or {}).get(account_id, 0.0) / 100.0, "anomaly", text)]


def role_reason(account_id: str, ml: MLContext) -> list[tuple[float, str, str]]:
    r = ml.roles.loc[ml.roles["account_id"] == account_id]
    if r.empty or r.iloc[0]["role"] not in ("collector", "distributor", "layering"):
        return []
    row = r.iloc[0]
    share = f" ({row['role_share']:.0%} of its weeks)" if pd.notna(row.get("role_share")) else ""
    return [(ROLE_REASON_POINTS / 100, "role", f"Behaviour matches the '{row['role']}' role{share} (HDBSCAN)")]


def top_reasons(account_id: str, indicators: pd.DataFrame, network: pd.DataFrame, ml: MLContext | None = None,
                n: int | None = None) -> list[dict]:
    n = n or config.TOP_REASONS
    w = base_weights()
    ind = indicators.loc[(indicators["account_id"] == account_id) & indicators["reason"].notna()]
    total_w = indicators.loc[indicators["account_id"] == account_id, "weight"].sum() or 1.0
    cands = [(w["indicator"] * r.weight * r.subscore / total_w, "indicator", r.reason) for r in ind.itertuples(index=False)]
    net = network.loc[network["account_id"] == account_id]
    if len(net):
        cands += network_reasons(net.iloc[0], w["network"])
    cands.sort(key=lambda x: -x[0])
    # model evidence gets a reserved slot each, so it is never crowded out by rules
    reserved = (anomaly_reasons(account_id, ml) + role_reason(account_id, ml)) if ml is not None else []
    chosen = cands[: max(0, n - len(reserved))] + reserved
    chosen.sort(key=lambda x: -x[0])
    return [{"source": s, "text": t, "contribution": round(100 * c, 1)} for c, s, t in chosen[:n]]


def reasons_table(accounts: pd.DataFrame, indicators: pd.DataFrame, network: pd.DataFrame,
                  ml: MLContext | None = None) -> pd.DataFrame:
    rows = []
    for aid in accounts["account_id"]:
        for rank, r in enumerate(top_reasons(aid, indicators, network, ml), start=1):
            rows.append({"account_id": aid, "rank": rank, **r})
    return pd.DataFrame(rows, columns=["account_id", "rank", "source", "text", "contribution"])
