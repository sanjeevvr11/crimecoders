"""Retrain the Phase 2 models and run the evaluation.

Runs the full pipeline (which trains the Isolation Forest, SHAP explainer and
HDBSCAN roles and rescoring every account), then the synthetic-injection,
stability, agreement and clustering evaluation, and writes
reports/model_evaluation.md + .json.

Usage (from backend/):  python scripts/train.py [--raw-dir PATH] [--skip-eval]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config  # noqa: E402
from app.models.evaluate import run_evaluation  # noqa: E402
from app.models.report import write_report  # noqa: E402
from app.pipeline.run_pipeline import run  # noqa: E402


def main() -> None:
    warnings.filterwarnings("ignore", category=FutureWarning)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=None)
    p.add_argument("--skip-eval", action="store_true")
    args = p.parse_args()

    out = run(raw_dir=args.raw_dir, return_tables=True)
    t = out["tables"]
    print(json.dumps(out["stats"]["models"], indent=2))
    if args.skip_eval:
        return
    t0 = time.time()
    evaluation = run_evaluation(t["transactions"], t["window_features"], t["accounts"], out["trained"], t["indicator_scores"])
    card = json.loads((config.MODEL_DIR / "model_card.json").read_text())
    md, js = write_report(evaluation, t["leads"], t["reasons"], card)
    inj = evaluation["injection"]
    print(f"evaluation {time.time() - t0:.1f}s -> {md}")
    print(f"synthetic injection: ROC-AUC {inj['roc_auc']['mean']:.3f}, PR-AUC {inj['pr_auc']['mean']:.3f}, "
          f"recall@threshold {inj['recall_at_threshold']['mean']:.3f}, FPR {inj['false_positive_rate']['mean']:.3f}")


if __name__ == "__main__":
    main()
