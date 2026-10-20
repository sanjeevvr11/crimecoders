"""End-to-end Phase 1 pipeline: ingest -> features -> graph -> complaints -> scores.

Run from backend/:  python -m app.pipeline.run_pipeline
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import pandas as pd

from app import config
from app.complaints.generator import generate_complaints
from app.complaints.matcher import evaluate, match_complaints
from app.features.account_features import account_features
from app.features.indicators import indicator_scores, indicator_table
from app.features.window_features import window_features
from app.graph.builder import build_edges, build_graph, node_table
from app.graph.centrality import centrality, network_scores
from app.graph.communities import core_graph, detect_rings
from app.ingestion.loader import load_all, write_outputs
from app.scoring.alerts import alerts as make_alerts
from app.scoring.alerts import lead_list
from app.scoring.reasons import reasons_table
from app.scoring.risk_score import risk_scores

log = logging.getLogger("trace360.pipeline")


def run(raw_dir: Path | None = None, processed_dir: Path | None = None, db_path: Path | None = None,
        synthetic_dir: Path | None = None) -> dict:
    processed_dir = processed_dir or config.PROCESSED_DIR
    synthetic_dir = synthetic_dir or config.SYNTHETIC_DIR
    t0 = time.time()
    timings: dict[str, float] = {}

    def lap(name: str) -> None:
        timings[name] = round(time.time() - t0 - sum(timings.values()), 2)
        log.info("%-12s %.2fs", name, timings[name])

    txns, accounts = load_all(raw_dir)
    lap("ingest")

    feats = account_features(txns)
    windows = window_features(txns)
    ind = indicator_table(feats)
    ind_scores = indicator_scores(ind)
    lap("features")

    edges = build_edges(txns, accounts)
    nodes = node_table(edges, accounts, txns)
    g = build_graph(edges, nodes)
    core = core_graph(g, nodes)
    members, rings = detect_rings(core, set(accounts["account_id"]))
    cent = centrality(g, core)
    nodes = nodes.merge(cent, on="node_id", how="left").merge(members, on="node_id", how="left")
    net = network_scores(accounts, nodes, edges, cent, members, rings)
    lap("graph")

    complaints = generate_complaints(txns)
    ring_of_account = net.dropna(subset=["ring_id"]).set_index("account_id")["ring_id"].to_dict()
    ring_of_node = members.dropna(subset=["ring_id"]).set_index("node_id")["ring_id"].to_dict()
    matches = match_complaints(complaints, txns, ring_of_account, ring_of_node)
    match_eval = evaluate(complaints, matches)
    synthetic_dir.mkdir(parents=True, exist_ok=True)
    complaints.to_csv(synthetic_dir / "complaints.csv", index=False)
    lap("complaints")

    scores = risk_scores(accounts, ind_scores, net)
    reasons = reasons_table(accounts, ind, net)
    leads = lead_list(scores, reasons, accounts)
    alert_df = make_alerts(leads)
    lap("scoring")

    real = txns["raw_narration"].notna() & ~txns["raw_narration"].str.match(r"^TXN-[A-Z0-9]{10}$", na=False)
    stats = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "n_transactions": int(len(txns)),
        "n_accounts": int(len(accounts)),
        "rows_per_layout": accounts.groupby("layout")["n_rows"].sum().astype(int).to_dict(),
        "time_reliable_rows": int(txns["time_reliable"].sum()),
        "narrations_with_text": int(real.sum()),
        "pct_narrations_parsed": round(100 * float((txns["channel"] != "UNKNOWN").mean()), 2),
        "pct_text_narrations_parsed": round(100 * float((txns.loc[real, "channel"] != "UNKNOWN").mean()), 2) if real.any() else 0.0,
        "pct_with_counterparty": round(100 * float(txns["counterparty_key"].notna().mean()), 2),
        "channel_mix": txns["channel"].value_counts().astype(int).to_dict(),
        "n_counterparties": int((~nodes["is_subject"]).sum()),
        "n_shared_counterparties": int(((~nodes["is_subject"]) & (nodes["n_subject_links"] >= 2)).sum()),
        "n_edges": int(len(edges)),
        "n_rings": int(len(rings)),
        "n_alerts": int(len(alert_df)),
        "alert_threshold": config.ALERT_THRESHOLD,
        "complaints": match_eval,
        "timings_s": timings,
    }

    tables = {
        "transactions": txns,
        "accounts": accounts,
        "account_features": feats,
        "window_features": windows,
        "indicators": ind,
        "indicator_scores": ind_scores,
        "edges": edges,
        "nodes": nodes,
        "rings": rings,
        "network_scores": net,
        "complaints": complaints,
        "complaint_matches": matches,
        "scores": scores,
        "reasons": reasons,
        "leads": leads,
        "alerts": alert_df,
    }
    write_outputs(tables, processed_dir, db_path)
    (processed_dir / "stats.json").write_text(json.dumps(stats, indent=2, default=str))
    lap("write")
    stats["timings_s"] = timings
    (processed_dir / "stats.json").write_text(json.dumps(stats, indent=2, default=str))
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    p = argparse.ArgumentParser(description="Run the Trace360 Phase 1 pipeline")
    p.add_argument("--raw-dir", type=Path, default=None)
    args = p.parse_args()
    stats = run(raw_dir=args.raw_dir)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
