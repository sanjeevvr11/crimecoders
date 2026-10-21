"""Evaluation of the unsupervised models.

There are no fraud labels, so real-world accuracy cannot be measured. The
closest substitute is a synthetic injection test: copy real, normal-looking
account-weeks, inject known mule transaction patterns into the copies, and
check whether a model trained only on other (clean) weeks ranks the injected
copies above the untouched test weeks. Every number this module produces is a
synthetic-injection or stability metric, not real-world accuracy.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score, silhouette_score

from app import config
from app.features.window_features import window_features
from app.models.anomaly import account_anomaly, fit_anomaly_model
from app.models.features import account_baselines, level_matrix, model_matrix
from app.models.roles import _cluster

PATTERNS = ("rapid_pass_through", "fan_in_burst", "night_burst", "round_layering")


# ---------------------------------------------------------------- injection
def _tx(ts, direction, amount, cp=None):
    return {"txn_ts": ts, "direction": direction, "amount": round(float(amount), 2), "channel": "UPI", "counterparty_key": cp}


def inject_pattern(pattern: str, week_start: pd.Timestamp, scale: float, rng: np.random.Generator, tag: str) -> pd.DataFrame:
    """Transactions for one mule pattern, placed inside the given week."""
    day = week_start + pd.Timedelta(days=int(rng.integers(0, 5)))
    rows = []
    if pattern == "rapid_pass_through":
        t = day + pd.Timedelta(hours=float(rng.uniform(9, 12)))
        for _ in range(int(rng.integers(8, 16))):
            a = scale * rng.uniform(0.5, 2.0)
            rows.append(_tx(t, "CR", a))
            rows.append(_tx(t + pd.Timedelta(minutes=float(rng.uniform(10, 90))), "DR", a * rng.uniform(0.95, 1.0)))
            t += pd.Timedelta(hours=float(rng.uniform(0.5, 3)))
    elif pattern == "fan_in_burst":
        t0 = day + pd.Timedelta(hours=float(rng.uniform(10, 16)))
        offs = np.sort(rng.uniform(0, 180, size=int(rng.integers(25, 60))))
        amts = rng.uniform(200, 3000, size=len(offs))
        for i, (o, a) in enumerate(zip(offs, amts)):
            rows.append(_tx(t0 + pd.Timedelta(minutes=float(o)), "CR", a, f"upi:{tag}{i}"))
        rows.append(_tx(t0 + pd.Timedelta(minutes=float(offs[-1] + rng.uniform(30, 90))), "DR", amts.sum() * 0.97))
    elif pattern == "night_burst":
        for night in range(int(rng.integers(1, 3))):
            base = day + pd.Timedelta(days=night)
            for _ in range(int(rng.integers(8, 15))):
                t = base + pd.Timedelta(minutes=float(rng.uniform(0, 270)))
                a = scale * rng.uniform(0.3, 1.5)
                rows.append(_tx(t, "CR", a))
                rows.append(_tx(t + pd.Timedelta(minutes=float(rng.uniform(5, 25))), "DR", a * rng.uniform(0.95, 1.0)))
    elif pattern == "round_layering":
        t = day + pd.Timedelta(hours=float(rng.uniform(9, 12)))
        for _ in range(int(rng.integers(8, 16))):
            a = float(rng.choice(np.arange(10_000, 200_001, 5_000)))
            rows.append(_tx(t, "CR", a))
            rows.append(_tx(t + pd.Timedelta(minutes=float(rng.uniform(30, 180))), "DR", a))
            t += pd.Timedelta(hours=float(rng.uniform(1, 4)))
    else:
        raise ValueError(pattern)
    return pd.DataFrame(rows)


def _window_txns(txns: pd.DataFrame) -> dict[tuple, pd.DataFrame]:
    t = txns.loc[txns["time_reliable"] & txns["txn_ts"].notna(),
                 ["account_id", "txn_ts", "direction", "amount", "channel", "counterparty_key"]].copy()
    t["week_start"] = t["txn_ts"].dt.to_period("W-SUN").dt.start_time
    return {k: g.drop(columns="week_start") for k, g in t.groupby(["account_id", "week_start"])}


def injected_windows(base_keys: list[tuple], by_window: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Recompute window features for copies of base windows with one pattern each."""
    frames, meta = [], []
    for i, (acc, week) in enumerate(base_keys):
        pattern = PATTERNS[i % len(PATTERNS)]
        base = by_window[(acc, week)]
        scale = float(np.clip(base["amount"].median(), 1_000, 100_000))
        extra = inject_pattern(pattern, week, scale, rng, tag=f"inj{i}_")
        copy_id = f"INJ{i}"
        both = pd.concat([base.assign(account_id=copy_id), extra.assign(account_id=copy_id)], ignore_index=True)
        both["time_reliable"] = True
        frames.append(both)
        meta.append({"account_id": copy_id, "pattern": pattern, "baseline_account": acc})
    if not frames:
        return pd.DataFrame()
    w = window_features(pd.concat(frames, ignore_index=True))
    return w.merge(pd.DataFrame(meta), on="account_id")


def injection_test(windows: pd.DataFrame, txns: pd.DataFrame, seed: int, by_window: dict | None = None,
                   contamination: float | None = None) -> dict:
    rng = np.random.default_rng(seed)
    by_window = by_window or _window_txns(txns)
    idx = rng.permutation(len(windows))
    n_test = int(round(len(windows) * config.EVAL_TEST_SHARE))
    test, train = windows.iloc[idx[:n_test]], windows.iloc[idx[n_test:]]
    base = account_baselines(train)  # each account's typical week, from training weeks only
    model = fit_anomaly_model(model_matrix(train, base), seed=seed, contamination=contamination)

    # base windows: test weeks the model already finds normal-looking
    test_raw = model.raw_scores(model_matrix(test, base))
    normal = test.loc[test_raw <= np.median(model.train_scores)]
    n_inj = max(len(PATTERNS), int(round(config.EVAL_INJECT_SHARE / (1 - config.EVAL_INJECT_SHARE) * len(test))))
    pick = normal.iloc[rng.choice(len(normal), size=min(n_inj, len(normal)), replace=len(normal) < n_inj)]
    inj = injected_windows(list(zip(pick["account_id"], pick["week_start"])), by_window, rng)

    inj_raw = model.raw_scores(model_matrix(inj, base))
    y = np.r_[np.zeros(len(test)), np.ones(len(inj))]
    s = np.r_[test_raw, inj_raw]
    flagged = s > model.threshold
    k = len(inj)
    top_k = np.argsort(-s)[:k]
    per_pattern = {p: float((inj_raw[inj["pattern"].to_numpy() == p] > model.threshold).mean()) for p in PATTERNS}
    return {
        "seed": seed, "n_train": int(len(train)), "n_test_clean": int(len(test)), "n_injected": int(k),
        "roc_auc": float(roc_auc_score(y, s)),
        "pr_auc": float(average_precision_score(y, s)),
        "precision_at_k": float(y[top_k].mean()),
        "recall_at_threshold": float(flagged[y == 1].mean()),
        "precision_at_threshold": float(y[flagged].mean()) if flagged.any() else 0.0,
        "false_positive_rate": float(flagged[y == 0].mean()),
        "recall_by_pattern": per_pattern,
    }


def _mean_std(values: list[float]) -> dict:
    return {"mean": round(float(np.mean(values)), 3), "std": round(float(np.std(values)), 3)}


def summarise_injection(runs: list[dict]) -> dict:
    keys = ["roc_auc", "pr_auc", "precision_at_k", "recall_at_threshold", "precision_at_threshold", "false_positive_rate"]
    out = {k: _mean_std([r[k] for r in runs]) for k in keys}
    out["recall_by_pattern"] = {p: _mean_std([r["recall_by_pattern"][p] for r in runs]) for p in PATTERNS}
    out["runs"] = runs
    return out


# ---------------------------------------------------------------- stability
def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def stability(windows: pd.DataFrame, accounts: pd.DataFrame, seeds=None) -> dict:
    seeds = seeds or config.EVAL_SEEDS
    X = model_matrix(windows)
    keys = list(zip(windows["account_id"], windows["week_start"]))
    flagged, ranks = [], []
    for seed in seeds:
        m = fit_anomaly_model(X, seed=seed)
        raw = m.raw_scores(X)
        flagged.append({k for k, f in zip(keys, raw > m.threshold) if f})
        pct = m.to_unit(raw)
        ws = windows[["account_id", "week_start"]].assign(
            anomaly_score=np.clip((pct - config.ANOMALY_FLOOR_PCT) / (1 - config.ANOMALY_FLOOR_PCT), 0, 1),
            is_flagged=raw > m.threshold)
        ranks.append(account_anomaly(ws, accounts).dropna(subset=["anomaly_score"]).set_index("account_id")["anomaly_score"])
    jac = [_jaccard(a, b) for a, b in combinations(flagged, 2)]
    rho = [spearmanr(a, b.reindex(a.index)).statistic for a, b in combinations(ranks, 2)]

    # time split: fit on the earliest 70% of weeks, score the rest; compare with the full-data model
    cutoff = windows["week_start"].quantile(config.EVAL_TIME_SPLIT)
    early, late = windows["week_start"] <= cutoff, windows["week_start"] > cutoff
    early_base = account_baselines(windows.loc[early])  # no look-ahead into later weeks
    X_early = model_matrix(windows, early_base)
    m_early = fit_anomaly_model(X_early.loc[early.to_numpy()], seed=config.MODEL_SEED)
    m_full = fit_anomaly_model(X, seed=config.MODEL_SEED)
    r_early = m_early.raw_scores(X_early.loc[late.to_numpy()])
    r_full = m_full.raw_scores(X.loc[late.to_numpy()])
    lk = [k for k, l in zip(keys, late) if l]
    time_jac = _jaccard({k for k, f in zip(lk, r_early > m_early.threshold) if f}, {k for k, f in zip(lk, r_full > m_full.threshold) if f})

    # per-account split: each account's first 70% of weeks vs its last 30%, so every
    # scored account has history in training (separates drift from unseen accounts)
    order = windows.groupby("account_id")["week_start"].rank(method="first", pct=True)
    a_early, a_late = (order <= config.EVAL_TIME_SPLIT).to_numpy(), (order > config.EVAL_TIME_SPLIT).to_numpy()
    acc_base = account_baselines(windows.loc[a_early])
    Xa = model_matrix(windows, acc_base)
    m_acc = fit_anomaly_model(Xa.loc[a_early], seed=config.MODEL_SEED)
    ra_early, ra_full = m_acc.raw_scores(Xa.loc[a_late]), m_full.raw_scores(X.loc[a_late])
    ak = [k for k, l in zip(keys, a_late) if l]
    acc_jac = _jaccard({k for k, f in zip(ak, ra_early > m_acc.threshold) if f}, {k for k, f in zip(ak, ra_full > m_full.threshold) if f})
    return {
        "seeds": list(seeds),
        "flagged_jaccard_across_seeds": _mean_std(jac),
        "account_rank_spearman_across_seeds": _mean_std(rho),
        "time_split": {
            "cutoff_week": str(pd.Timestamp(cutoff).date()), "train_windows": int(early.sum()), "scored_windows": int(late.sum()),
            "window_score_spearman_vs_full_model": round(float(spearmanr(r_early, r_full).statistic), 3),
            "flagged_jaccard_vs_full_model": round(time_jac, 3),
            "flagged_share_early_model": round(float((r_early > m_early.threshold).mean()), 3),
        },
        "per_account_time_split": {
            "train_windows": int(a_early.sum()), "scored_windows": int(a_late.sum()),
            "window_score_spearman_vs_full_model": round(float(spearmanr(ra_early, ra_full).statistic), 3),
            "flagged_jaccard_vs_full_model": round(acc_jac, 3),
            "flagged_share_early_model": round(float((ra_early > m_acc.threshold).mean()), 3),
        },
    }


# ---------------------------------------------------------------- clustering
def clustering_quality(windows: pd.DataFrame, window_role_df: pd.DataFrame, profiles: pd.DataFrame,
                       account_role_df: pd.DataFrame) -> dict:
    from hdbscan.validity import validity_index
    from sklearn.preprocessing import RobustScaler

    active = windows["n_txns"] >= config.ROLE_MIN_WEEK_TXNS
    Z = RobustScaler().fit_transform(level_matrix(windows.loc[active]))

    def quality(labels: np.ndarray) -> dict:
        k = int(labels.max() + 1) if len(labels) else 0
        nz = labels >= 0
        q = {"clusters": k, "noise_share": round(float((~nz).mean()), 3) if len(labels) else None,
             "silhouette_non_noise": None, "dbcv": None}
        if k > 1:
            q["silhouette_non_noise"] = round(float(silhouette_score(Z[nz], labels[nz])), 3)
            q["dbcv"] = round(float(validity_index(Z.astype(np.float64), labels)), 3)
        return q

    labels = window_role_df.loc[active.to_numpy(), "cluster"].to_numpy()
    eom = _cluster(Z, config.HDBSCAN_WINDOW_MIN_CLUSTER, config.HDBSCAN_WINDOW_MIN_SAMPLES, method="eom")
    return {
        "active_weeks": int(active.sum()), "sparse_weeks": int((~active).sum()),
        "chosen": {"selection": config.HDBSCAN_SELECTION, **quality(labels)},
        "alternative_eom": {"selection": "eom", **quality(eom)},
        "profiles": profiles.round(3).to_dict(orient="records"),
        "account_roles": account_role_df.to_dict(orient="records"),
    }


# ---------------------------------------------------------------- report
def agreement(anomaly: pd.DataFrame, indicator: pd.DataFrame) -> dict:
    d = anomaly.dropna(subset=["anomaly_score"]).merge(indicator, on="account_id")
    if len(d) < 3:
        return {"accounts": int(len(d)), "spearman": None}
    r = spearmanr(d["anomaly_score"], d["indicator_score"])
    return {"accounts": int(len(d)), "spearman": round(float(r.statistic), 3), "p_value": round(float(r.pvalue), 3)}


def run_evaluation(txns: pd.DataFrame, windows: pd.DataFrame, accounts: pd.DataFrame, trained: dict,
                   indicator: pd.DataFrame, seeds=None) -> dict:
    seeds = seeds or config.EVAL_SEEDS
    by_window = _window_txns(txns)
    runs = [injection_test(windows, txns, s, by_window) for s in seeds]
    sweep = {}
    for c in (0.05, 0.10):
        rs = [injection_test(windows, txns, s, by_window, contamination=c) for s in seeds]
        sweep[str(c)] = {k: _mean_std([r[k] for r in rs]) for k in ("recall_at_threshold", "precision_at_threshold", "false_positive_rate")}
    return {
        "note": "No fraud labels exist. Injection metrics measure detection of synthetic mule patterns "
                "inserted into real weeks; they are not real-world accuracy.",
        "contamination": config.IFOREST_CONTAMINATION,
        "injection": summarise_injection(runs),
        "contamination_sweep": sweep,
        "stability": stability(windows, accounts, seeds),
        "agreement_with_rules": agreement(trained["anomaly"], indicator),
        "clustering": clustering_quality(windows, trained["window_roles"], trained["role_profiles"], trained["roles"]),
    }
