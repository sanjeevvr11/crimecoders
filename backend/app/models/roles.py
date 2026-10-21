"""HDBSCAN behaviour roles.

Use case: group weeks (and accounts) that behave alike, and name each group by
the mule role its typical behaviour resembles: collector (many credits in,
little out), distributor (many debits out), layering (money passes straight
through with short dwell) or normal-looking. Points that fit no group are
'unclassified'. HDBSCAN picks the number of groups itself and leaves outliers
unassigned instead of forcing them into a cluster.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import HDBSCAN
from sklearn.preprocessing import RobustScaler

from app import config
from app.models.features import level_matrix

PROFILE_COLUMNS = ["cluster", "size", "cr_count_share", "pass_through", "fast_outflow_share", "median_dwell_hours", "n_txns",
                   "night_share", "round_amount_share", "max_txns_per_hour", "n_accounts", "role"]
ACCOUNT_FEATURES = ["log_n_txns", "cr_count_share", "log_small_in_large_out", "round_amount_share", "pass_through"]


def name_role(cr_count_share: float, pass_through: float, fast_outflow: float | None, dwell_hours: float | None) -> str:
    lo, hi = config.ROLE_LAYERING_PASS_THROUGH
    quick = (fast_outflow is not None and not np.isnan(fast_outflow) and fast_outflow >= config.ROLE_LAYERING_MIN_FAST_OUTFLOW) or (
        dwell_hours is not None and not np.isnan(dwell_hours) and dwell_hours <= config.ROLE_LAYERING_MAX_DWELL_HOURS)
    if not np.isnan(pass_through) and lo <= pass_through <= hi and quick:
        return "layering"
    if cr_count_share >= config.ROLE_COLLECTOR_MIN_CR_SHARE:
        return "collector"
    if cr_count_share <= config.ROLE_DISTRIBUTOR_MAX_CR_SHARE:
        return "distributor"
    return "normal-looking"


def _cluster(X: np.ndarray, min_cluster_size: int, min_samples: int | None, method: str | None = None) -> np.ndarray:
    if len(X) < max(min_cluster_size, 2):
        return np.full(len(X), -1)
    method = method or config.HDBSCAN_SELECTION
    return HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                   cluster_selection_method=method, copy=True).fit(X).labels_


def window_roles(windows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Cluster active windows (>= ROLE_MIN_WEEK_TXNS transactions); sparser weeks
    are labelled 'sparse' (cluster -2) since a role means little for a week with
    one or two transactions. Returns (per-window labels+roles, cluster profiles,
    scaled matrix of the clustered windows)."""
    active = (windows["n_txns"] >= config.ROLE_MIN_WEEK_TXNS).to_numpy()
    X = level_matrix(windows.loc[active])
    Z = RobustScaler().fit_transform(X) if len(X) else np.empty((0, 0))
    labels = np.full(len(windows), -2)
    labels[active] = _cluster(Z, config.HDBSCAN_WINDOW_MIN_CLUSTER, config.HDBSCAN_WINDOW_MIN_SAMPLES)
    w = windows.assign(cluster=labels)
    w["cr_count_share"] = w["n_cr"] / w["n_txns"].clip(lower=1)
    profiles = []
    for c, g in w.loc[w["cluster"] >= 0].groupby("cluster"):
        prof = {
            "cluster": int(c), "size": int(len(g)),
            "cr_count_share": float(g["cr_count_share"].median()),
            "pass_through": float(g["pass_through_ratio"].median()),
            "fast_outflow_share": float(g["fast_outflow_share"].median()),
            "median_dwell_hours": float(g["median_dwell_hours"].median()),
            "n_txns": float(g["n_txns"].median()),
            "night_share": float(g["night_share"].median()),
            "round_amount_share": float(g["round_amount_share"].median()),
            "max_txns_per_hour": float(g["max_txns_per_hour"].median()),
            "n_accounts": int(g["account_id"].nunique()),
        }
        prof["role"] = name_role(prof["cr_count_share"], prof["pass_through"], prof["fast_outflow_share"], prof["median_dwell_hours"])
        profiles.append(prof)
    prof_df = pd.DataFrame(profiles, columns=PROFILE_COLUMNS)
    role_of = prof_df.set_index("cluster")["role"].to_dict() if len(prof_df) else {}
    w["role"] = [role_of.get(c, "sparse" if c == -2 else "unclassified") for c in labels]
    return w[["account_id", "week_start", "cluster", "role"]], prof_df, Z


def account_matrix(features: pd.DataFrame) -> pd.DataFrame:
    """Non-temporal account features available for all accounts."""
    f = features
    m = pd.DataFrame(index=f.index)
    m["log_n_txns"] = np.log1p(f["n_txns"])
    m["cr_count_share"] = f["n_cr"] / f["n_txns"].clip(lower=1)
    m["log_small_in_large_out"] = np.log(f["small_in_large_out"].fillna(1.0).clip(lower=1e-3))
    m["round_amount_share"] = f["round_amount_share"].fillna(0.0)
    m["pass_through"] = f["pass_through_ratio"].fillna(1.0).clip(0, 3)
    return m[ACCOUNT_FEATURES]


def account_roles(features: pd.DataFrame, window_role_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Role per account. Time-reliable accounts take their dominant non-noise
    window role; the others use HDBSCAN on non-temporal account features
    (layering needs timing, so those can only be collector/distributor/normal)."""
    X = account_matrix(features)
    Z = RobustScaler().fit_transform(X)
    labels = _cluster(Z, config.HDBSCAN_ACCOUNT_MIN_CLUSTER, None, method="eom")
    acc = features[["account_id", "time_reliable", "n_cr", "n_txns", "pass_through_ratio"]].assign(account_cluster=labels)
    acc_role = {}
    for c, g in acc.loc[acc["account_cluster"] >= 0].groupby("account_cluster"):
        share = float((g["n_cr"] / g["n_txns"].clip(lower=1)).median())
        acc_role[c] = name_role(share, np.nan, None, None)

    rows = []
    for r in acc.itertuples(index=False):
        wr = window_role_df.loc[(window_role_df["account_id"] == r.account_id) & (window_role_df["cluster"] >= 0), "role"]
        if r.time_reliable and len(wr):
            counts = wr.value_counts()
            role, source = counts.index[0], "window clusters"
            share = float(counts.iloc[0] / (window_role_df["account_id"] == r.account_id).sum())
            if share < config.ROLE_MIN_SHARE:
                role = "unclassified"  # too few of its weeks behave alike to name a role
        elif r.time_reliable:
            role, source, share = "unclassified", "window clusters", 0.0
        else:
            role = acc_role.get(r.account_cluster, "unclassified")
            own = name_role(r.n_cr / max(r.n_txns, 1), np.nan, None, None)
            if role != own:
                role = "unclassified"  # the cluster's label does not hold for this account itself
            source, share = "account clusters", np.nan
        rows.append({"account_id": r.account_id, "role": role, "role_source": source,
                     "role_share": share, "account_cluster": int(r.account_cluster)})
    return pd.DataFrame(rows), Z, labels
