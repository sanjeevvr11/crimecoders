"""Synthetic victim complaints, seeded from real counterparties.

The dataset has no complaint records. To demonstrate complaint-to-account
matching we generate SYNTHETIC complaints: each one picks a real transaction
with a known counterparty and reports that identifier the way a victim
might (typos, truncation, missing handle). A share are decoys that match
nothing. Every record is labelled synthetic=True.
"""
from __future__ import annotations

import string

import numpy as np
import pandas as pd

from app import config

HANDLES = ["ybl", "okaxis", "oksbi", "paytm", "ibl", "upi", "okhdfcbank"]
COMPLAINT_COLUMNS = [
    "complaint_id", "date", "victim", "reported_upi_or_account", "reported_type", "amount", "channel",
    "synthetic", "is_decoy", "seed_txn_uid", "seed_counterparty_key",
]


def _corrupt(value: str, rng: np.random.Generator) -> str:
    """Apply one victim-style error: typo, truncation, swap or none."""
    kind = rng.choice(["none", "typo", "truncate", "swap"], p=[0.3, 0.3, 0.25, 0.15])
    if len(value) < 5 or kind == "none":
        return value
    chars = list(value)
    i = int(rng.integers(1, len(chars) - 1))
    if kind == "typo":
        pool = string.digits if chars[i].isdigit() else string.ascii_lowercase
        chars[i] = rng.choice([c for c in pool if c != chars[i]])
    elif kind == "truncate":
        chars = chars[: len(chars) - int(rng.integers(1, 3))]
    elif kind == "swap" and i + 1 < len(chars):
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    return "".join(chars)


def generate_complaints(txns: pd.DataFrame, n: int | None = None, seed: int | None = None) -> pd.DataFrame:
    n = n or config.N_SYNTHETIC_COMPLAINTS
    rng = np.random.default_rng(config.COMPLAINT_SEED if seed is None else seed)
    pool = txns.loc[txns["counterparty_type"].isin(["upi", "account"])]
    n_decoy = int(round(n * config.COMPLAINT_DECOY_SHARE))
    n_real = min(n - n_decoy, len(pool))
    seeds = pool.sample(n=n_real, random_state=int(rng.integers(0, 2**31 - 1))) if n_real else pool.iloc[:0]

    rows = []
    for i, t in enumerate(seeds.itertuples(index=False)):
        kind, ident = t.counterparty_type, t.counterparty_key.split(":", 1)[1]  # key prefix is "acct:" for type "account"
        reported = _corrupt(ident, rng)
        if kind == "upi" and rng.random() < 0.6:
            reported = f"{reported}@{rng.choice(HANDLES)}"
        amount = float(t.amount) if rng.random() < 0.7 else round(float(t.amount) * float(rng.uniform(0.99, 1.01)), 2)
        if pd.notna(t.txn_ts):
            date = pd.Timestamp(t.txn_ts).normalize() + pd.Timedelta(days=int(rng.integers(0, 2)))
        else:
            date = pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng.integers(0, 730)))
        rows.append({
            "date": date, "reported_upi_or_account": reported, "reported_type": kind, "amount": amount,
            "channel": t.channel if t.channel != "UNKNOWN" else "UPI", "is_decoy": False,
            "seed_txn_uid": t.txn_uid, "seed_counterparty_key": t.counterparty_key,
        })
    for _ in range(n - len(rows)):
        if rng.random() < 0.5:
            reported, kind = "".join(rng.choice(list("bcdfghjkmnpqrstvwxz"), size=8)) + str(int(rng.integers(10, 99))) + "@ybl", "upi"
        else:
            reported, kind = "".join(rng.choice(list(string.digits), size=12)), "account"
        rows.append({
            "date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=int(rng.integers(0, 730))),
            "reported_upi_or_account": reported, "reported_type": kind,
            "amount": round(float(rng.uniform(500, 200_000)), 2), "channel": "UPI" if kind == "upi" else "IMPS",
            "is_decoy": True, "seed_txn_uid": None, "seed_counterparty_key": None,
        })
    order = rng.permutation(len(rows))
    df = pd.DataFrame([rows[i] for i in order])
    df.insert(0, "complaint_id", [f"CMP-{i + 1:04d}" for i in range(len(df))])
    df["victim"] = [f"Synthetic Victim {i + 1:03d}" for i in range(len(df))]
    df["synthetic"] = True
    return df[COMPLAINT_COLUMNS]
