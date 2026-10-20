"""Match complaints to counterparties, transactions, accounts and rings.

Identifier similarity uses RapidFuzz (ratio + partial ratio), then each
candidate is checked against that counterparty's transactions for an amount
within tolerance and, where timestamps exist, a date within the window.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from app import config
from app.ingestion.narration_parser import normalise_vpa

MATCH_COLUMNS = [
    "complaint_id", "counterparty_key", "id_score", "txn_uid", "account_id", "amount_match", "time_match",
    "confidence", "ring_id",
]


def normalise_reported(value: str, kind: str) -> str | None:
    if kind == "account":
        digits = re.sub(r"\D", "", str(value))
        return digits or None
    return normalise_vpa(str(value))


def _candidates(query: str, choices: list[str]) -> dict[str, float]:
    found: dict[str, float] = {}
    for key, score, _ in process.extract(query, choices, scorer=fuzz.ratio, limit=5, score_cutoff=config.MATCH_ID_CUTOFF):
        found[key] = max(found.get(key, 0.0), score)
    if len(query) >= 6:
        # truncated reports: the query is a prefix/substring of the real id
        for key, score, _ in process.extract(query, choices, scorer=fuzz.partial_ratio, limit=5, score_cutoff=95):
            if len(key) >= 6 and min(len(key), len(query)) / max(len(key), len(query)) >= 0.7:
                found[key] = max(found.get(key, 0.0), score * 0.95)
    return found


def match_complaints(complaints: pd.DataFrame, txns: pd.DataFrame, ring_of_account: dict | None = None,
                     ring_of_node: dict | None = None) -> pd.DataFrame:
    ring_of_account = ring_of_account or {}
    ring_of_node = ring_of_node or {}
    known = txns.loc[txns["counterparty_type"].isin(["upi", "account"])]
    by_key = {k: g for k, g in known.groupby("counterparty_key")}
    choices = {
        kind: sorted({k.split(":", 1)[1] for k in by_key if k.startswith(prefix)})
        for kind, prefix in (("upi", "upi:"), ("account", "acct:"))
    }
    prefix = {"upi": "upi:", "account": "acct:"}
    window = pd.Timedelta(days=config.MATCH_TIME_WINDOW_DAYS)

    rows = []
    for c in complaints.itertuples(index=False):
        q = normalise_reported(c.reported_upi_or_account, c.reported_type)
        if not q:
            continue
        for ident, id_score in _candidates(q, choices[c.reported_type]).items():
            key = prefix[c.reported_type] + ident
            g = by_key[key]
            amt_ok = (g["amount"] - c.amount).abs() <= config.MATCH_AMOUNT_TOLERANCE * c.amount
            has_ts = g["txn_ts"].notna()
            time_ok = has_ts & ((g["txn_ts"] - pd.Timestamp(c.date)).abs() <= window + pd.Timedelta(days=1))
            # best supporting transaction for this candidate
            rank = amt_ok.astype(int) * 2 + time_ok.astype(int)
            best = g.loc[rank.idxmax()]
            a = float(amt_ok.loc[best.name])
            t = float(time_ok.loc[best.name]) if has_ts.loc[best.name] else np.nan
            parts = [(0.6, id_score / 100.0), (0.3, a)] + ([] if np.isnan(t) else [(0.1, t)])
            conf = sum(w * s for w, s in parts) / sum(w for w, _ in parts)
            if conf < config.MATCH_MIN_CONFIDENCE:
                continue
            rows.append({
                "complaint_id": c.complaint_id,
                "counterparty_key": key,
                "id_score": round(float(id_score), 1),
                "txn_uid": best["txn_uid"] if a else None,
                "account_id": best["account_id"],
                "amount_match": bool(a),
                "time_match": None if np.isnan(t) else bool(t),
                "confidence": round(float(conf), 3),
                "ring_id": ring_of_node.get(key) or ring_of_account.get(best["account_id"]),
            })
    out = pd.DataFrame(rows, columns=MATCH_COLUMNS)
    return out.sort_values(["complaint_id", "confidence"], ascending=[True, False]).reset_index(drop=True)


def evaluate(complaints: pd.DataFrame, matches: pd.DataFrame) -> dict:
    """Synthetic ground truth lets us report matcher precision/recall."""
    top = matches.drop_duplicates("complaint_id")
    merged = complaints.merge(top, on="complaint_id", how="left")
    real = merged.loc[~merged["is_decoy"]]
    decoy = merged.loc[merged["is_decoy"]]
    hit = real["counterparty_key"] == real["seed_counterparty_key"]
    return {
        "complaints": int(len(complaints)),
        "matched": int(top["complaint_id"].nunique()),
        "recall_top1": round(float(hit.mean()), 3) if len(real) else None,
        "decoys_matched": int(decoy["counterparty_key"].notna().sum()),
        "decoys": int(len(decoy)),
    }
