"""Central configuration: paths, thresholds and weights.

Every tunable number used by the indicators, graph and scoring lives here so
that analysts can adjust the rules without touching code.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("TRACE360_DATA_DIR", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
DUCKDB_PATH = DATA_DIR / "trace360.duckdb"

RAW_FILE_PATTERN = r"^(\d+)_SOA\.(xls|xlsx)$"

# Narration tokens such as 'TXN-AB12CDUPI9' are random 10-char strings. In the
# delivered dataset the channel codes appear inside them at roughly the rate
# random strings would produce (~0.07%), so recovering a channel from them adds
# noise, not signal. Kept as a switch in case a future extract does embed them.
RECOVER_CHANNEL_FROM_TOKENS = False

# UPI VPAs are truncated to 11 chars in CRN statements and 15 in ICORE files.
# Keys are cut to this length so the same payee matches across layouts.
UPI_KEY_LEN = 11

# ---------------------------------------------------------------- features
ROUND_AMOUNT_UNITS = (1000, 500)
SMALL_CREDIT_MAX = 5_000.0
LARGE_DEBIT_MIN = 50_000.0
FAST_OUTFLOW_HOURS = 2.0
BURST_TXNS_PER_HOUR = 10
NIGHT_HOURS = (0, 5)  # [start, end) local hour

# ---------------------------------------------------------------- indicators
# method 'ramp': sub-score rises linearly from 0 at `lo` to 1 at `hi`
# (lo > hi gives an inverted ramp, i.e. smaller is riskier).
INDICATORS: dict[str, dict] = {
    # ~1.0 for every statement in the delivered data (amounts are randomised), so it
    # barely separates accounts; kept at low weight because it is a core mule trait
    "pass_through_ratio": {"method": "ramp", "lo": 0.6, "hi": 0.95, "weight": 0.5},
    "fan_in": {"method": "ramp", "lo": 20, "hi": 300, "weight": 1.0},
    "fan_out": {"method": "ramp", "lo": 10, "hi": 150, "weight": 1.0},
    "small_in_large_out": {"method": "ramp", "lo": 2.0, "hi": 20.0, "weight": 1.0},
    "round_amount_share": {"method": "ramp", "lo": 0.15, "hi": 0.6, "weight": 0.5},
    "upi_share": {"method": "ramp", "lo": 0.4, "hi": 0.9, "weight": 0.5},
    "fast_outflow_share": {"method": "ramp", "lo": 0.2, "hi": 0.8, "weight": 2.0},
    "median_dwell_hours": {"method": "ramp", "lo": 72.0, "hi": 2.0, "weight": 1.5},
    "burst_hours": {"method": "ramp", "lo": 2, "hi": 30, "weight": 1.0},
    "night_share": {"method": "ramp", "lo": 0.05, "hi": 0.3, "weight": 1.0},
    "txns_per_active_day": {"method": "ramp", "lo": 5, "hi": 50, "weight": 1.0},
}
REASON_MIN_SUBSCORE = 0.4

# ---------------------------------------------------------------- graph
GRAPH_SEED = 42
LOUVAIN_RESOLUTION = 1.0
RING_MIN_SUBJECTS = 2  # a community needs >= this many subject accounts
NETWORK_WEIGHTS = {
    "shared_counterparties": 0.4,
    "pagerank": 0.2,
    "betweenness": 0.2,
    "ring_membership": 0.2,
}
SHARED_CP_SATURATION = 100  # shared counterparties at which the sub-score is 1
TRAIL_MAX_HOPS = 4
TRAIL_MAX_PATHS = 200

# ---------------------------------------------------------------- complaints
N_SYNTHETIC_COMPLAINTS = 150
COMPLAINT_DECOY_SHARE = 0.15
COMPLAINT_SEED = 7
MATCH_ID_CUTOFF = 80
MATCH_AMOUNT_TOLERANCE = 0.02
MATCH_TIME_WINDOW_DAYS = 3
MATCH_MIN_CONFIDENCE = 0.55

# ---------------------------------------------------------------- scoring
SCORE_WEIGHTS = {"indicator": 0.65, "network": 0.35, "anomaly": 0.0}  # anomaly: Phase 2
ALERT_THRESHOLD = 50.0
TIERS = ((70.0, "HIGH"), (50.0, "MEDIUM"), (0.0, "LOW"))
TOP_REASONS = 5

CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
