"""Write reports/model_evaluation.md and .json from an evaluation run."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app import config

MODELS_TABLE = [
    ("Isolation Forest (scikit-learn)",
     "Scores every account-week against all other weeks and against the account's own usual week; the most unusual 5% are flagged. "
     "Account anomaly = mean of its top-3 calibrated week scores, used as an uplift on the risk score.",
     "Unsupervised (no labels exist), fast, robust to irrelevant features, needs no distribution assumptions.",
     "Finds *unusual*, not *criminal*: a steady mule is not unusual for itself, and naturally extreme weeks also get flagged. "
     "Needs reliable timestamps, so SOA1-6 get no score."),
    ("SHAP TreeExplainer",
     "Explains each flagged week: which features pushed it towards 'anomalous', turned into plain-English reasons.",
     "Exact, fast attributions for tree models; makes the forest auditable by an investigator.",
     "Explains the model, not the truth; attributions on correlated features can be split between them."),
    ("HDBSCAN (scikit-learn), week level",
     "Groups active weeks (>= 10 txns) with similar behaviour and names each group by its typical pattern: "
     "collector, distributor, layering or normal-looking; outliers stay 'unclassified'. An account's role is its dominant group.",
     "Finds the number of groups itself, handles uneven density and leaves outliers unassigned instead of forcing them.",
     "Role names come from simple thresholds on cluster medians; with this data ~half the weeks are noise and separation is weak (see DBCV)."),
    ("HDBSCAN, account level",
     "Roles for the six statements without reliable timestamps, from non-temporal features (credit share, volume, round amounts, ratios).",
     "Same reasons as above; works with 25 accounts.",
     "Only 25 points and no timing, so it can only say collector/distributor/normal, never layering."),
]


def _ms(d: dict) -> str:
    return f"{d['mean']:.3f} ± {d['std']:.3f}"


def _table(rows: list[list], header: list[str]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def top10_table(leads: pd.DataFrame, reasons: pd.DataFrame) -> list[dict]:
    rows = []
    for r in leads.head(10).itertuples(index=False):
        rs = reasons.loc[reasons["account_id"] == r.account_id].sort_values("rank")["text"].head(3).tolist()
        rows.append({
            "rank": int(r.rank), "account_id": r.account_id, "phase1_score": float(r.risk_score_phase1),
            "phase2_score": float(r.risk_score), "anomaly_uplift": float(r.anomaly_uplift),
            "flagged_weeks": None if pd.isna(r.flagged_weeks) else int(r.flagged_weeks),
            "role": r.role, "ring_id": r.ring_id if isinstance(r.ring_id, str) else None, "top_reasons": rs,
        })
    return rows


def write_report(evaluation: dict, leads: pd.DataFrame, reasons: pd.DataFrame, model_card: dict,
                 reports_dir: Path | None = None) -> tuple[Path, Path]:
    reports_dir = reports_dir or config.REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)
    top10 = top10_table(leads, reasons)
    payload = {**evaluation, "top10": top10, "model_card": model_card}
    json_path = reports_dir / "model_evaluation.json"
    json_path.write_text(json.dumps(payload, indent=2, default=str))

    inj = evaluation["injection"]
    st = evaluation["stability"]
    cl = evaluation["clustering"]
    ag = evaluation["agreement_with_rules"]
    md = [
        "# Trace360 model evaluation (Phase 2)",
        "",
        f"Generated {model_card.get('generated_at', '')}. Seeds {st['seeds']}, contamination {evaluation['contamination']}.",
        "",
        "> **There are no fraud labels in this dataset, so real-world accuracy cannot be measured.** "
        "The numbers below are (a) detection of *synthetic* mule patterns injected into real weeks, "
        "(b) stability and (c) agreement checks. Read them as evidence that the models behave sensibly, not as accuracy.",
        "",
        "## Models used and use case",
        "",
        _table([list(r) for r in MODELS_TABLE], ["Model", "What it does in Trace360", "Why this model", "Limitations"]),
        "",
        "## a) Synthetic injection test (closest substitute for accuracy)",
        "",
        f"For each seed the windows are split {int((1 - config.EVAL_TEST_SHARE) * 100)}/{int(config.EVAL_TEST_SHARE * 100)}; "
        "the forest trains on the training weeks only. Copies of normal-looking test weeks get one injected mule pattern "
        f"(~{int(config.EVAL_INJECT_SHARE * 100)}% of the test set) and are scored with the untouched test weeks. "
        "Untouched weeks that happen to be genuinely unusual count as false positives, so precision is a lower bound.",
        "",
        _table([
            ["ROC-AUC (injected vs clean, 0.5 = chance)", _ms(inj["roc_auc"])],
            ["PR-AUC (baseline = share injected ≈ 0.10)", _ms(inj["pr_auc"])],
            ["Precision@K (K = number injected)", _ms(inj["precision_at_k"])],
            [f"Recall at the {evaluation['contamination']:.0%} flag threshold", _ms(inj["recall_at_threshold"])],
            ["Precision at the threshold", _ms(inj["precision_at_threshold"])],
            ["False-positive rate on clean test weeks", _ms(inj["false_positive_rate"])],
        ], ["Metric (synthetic injection)", "Mean ± std over 5 seeds"]),
        "",
        "Recall by injected pattern (at the threshold):",
        "",
        _table([[p, _ms(v)] for p, v in inj["recall_by_pattern"].items()], ["Pattern", "Recall"]),
        "",
        "Contamination trade-off:",
        "",
        _table([[c, _ms(v["recall_at_threshold"]), _ms(v["precision_at_threshold"]), _ms(v["false_positive_rate"])]
                for c, v in evaluation["contamination_sweep"].items()], ["Contamination", "Recall", "Precision", "FPR"]),
        "",
        "## b) Stability",
        "",
        _table([
            ["Jaccard overlap of flagged weeks across seeds", _ms(st["flagged_jaccard_across_seeds"])],
            ["Spearman of account anomaly ranking across seeds", _ms(st["account_rank_spearman_across_seeds"])],
            [f"Time split: Spearman of later-week scores, model fit on weeks ≤ {st['time_split']['cutoff_week']} vs full model",
             st["time_split"]["window_score_spearman_vs_full_model"]],
            ["Time split: Jaccard of flagged later weeks", st["time_split"]["flagged_jaccard_vs_full_model"]],
            ["Time split: share of later weeks flagged by the early model", st["time_split"]["flagged_share_early_model"]],
            ["Per-account split (first 70% of each account's weeks → last 30%): Spearman vs full model",
             st["per_account_time_split"]["window_score_spearman_vs_full_model"]],
            ["Per-account split: Jaccard of flagged later weeks", st["per_account_time_split"]["flagged_jaccard_vs_full_model"]],
            ["Per-account split: share of later weeks flagged", st["per_account_time_split"]["flagged_share_early_model"]],
        ], ["Check", "Value"]),
        "",
        "Across seeds the model is very stable. Across time it is not: a model fit on earlier weeks flags far more than 5% "
        "of later weeks, i.e. behaviour drifts and the model must be retrained when new statements arrive (training takes "
        "under a second). The global split also scores accounts whose history starts after the cutoff; the per-account "
        "split removes that effect.",
        "",
        "## c) Agreement with the rule indicators",
        "",
        f"Spearman between account anomaly score and rule-indicator score over {ag['accounts']} time-reliable accounts: "
        f"**{ag['spearman']}** (p = {ag.get('p_value')}). The anomaly model measures change against each account's own "
        "history while the rules measure absolute mule traits, so low agreement is expected and is reported, not tuned away.",
        "",
        "## d) HDBSCAN roles",
        "",
        f"{cl['active_weeks']} active weeks clustered ({cl['sparse_weeks']} weeks with < {config.ROLE_MIN_WEEK_TXNS} transactions labelled 'sparse').",
        "",
        _table([[q["selection"], q["clusters"], q["noise_share"], q["silhouette_non_noise"], q["dbcv"]]
                for q in (cl["chosen"], cl["alternative_eom"])], ["Selection", "Clusters", "Noise share", "Silhouette (non-noise)", "DBCV"]),
        "",
        f"Chosen: '{cl['chosen']['selection']}'. 'eom' scores better on DBCV but finds only two coarse groups, which cannot "
        "separate roles; 'leaf' finds interpretable groups at the cost of more noise and weaker separation.",
        "",
        _table([[p["cluster"], p["size"], p["n_accounts"], p["role"], f"{p['cr_count_share']:.2f}", f"{p['pass_through']:.2f}",
                 f"{p['fast_outflow_share']:.2f}", f"{p['median_dwell_hours']:.1f}", f"{p['n_txns']:.0f}"] for p in cl["profiles"]],
               ["Cluster", "Weeks", "Accounts", "Role", "Credit share", "Pass-through", "Fast outflow", "Dwell h", "Txns/week"]),
        "",
        "Role per account:",
        "",
        _table([[r["account_id"], r["role"], r["role_source"], "" if pd.isna(r.get("role_share")) else f"{r['role_share']:.0%}"]
                for r in cl["account_roles"]], ["Account", "Role", "Source", "Share of weeks"]),
        "",
        "## e) Top 10 accounts: Phase 1 vs Phase 2",
        "",
        _table([[r["rank"], r["account_id"], r["phase1_score"], r["phase2_score"], f"+{r['anomaly_uplift']}",
                 "n/a" if r["flagged_weeks"] is None else r["flagged_weeks"], r["role"], r["ring_id"] or "",
                 "<br>".join(r["top_reasons"])] for r in top10],
               ["#", "Account", "Phase 1", "Phase 2", "Uplift", "Flagged weeks", "Role", "Ring", "Top reasons"]),
        "",
    ]
    md_path = reports_dir / "model_evaluation.md"
    md_path.write_text("\n".join(md))
    return md_path, json_path
