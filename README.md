# Trace360

Mule account detection for PS-01: ingest bank statements in many layouts, score each account
with explainable rules and money-flow network analysis, link (synthetic) victim complaints, and
produce ranked leads with evidence reports.

**Phase 1 (this repo):** rules + graph, **no trained ML models**. Phase 2 adds Isolation Forest on
the account-week window features, SHAP explanations and HDBSCAN; the risk score already reserves
an `anomaly_score` slot at weight 0 for it.

## Layout

```
data/
  raw/          N_SOA.xls/.xlsx statements (gitignored, never committed)
  processed/    parquet outputs + stats.json (gitignored)
  synthetic/    generated complaints (gitignored)
backend/
  app/
    config.py               all thresholds and weights
    ingestion/              layout detector, one adapter per layout, narration parser, canonical schema
    features/               per-account features, account-week windows, 0-1 rule indicators + reasons
    graph/                  flow graph, Louvain rings, PageRank/betweenness, money trail
    complaints/             synthetic complaint generator + RapidFuzz matcher
    scoring/                risk score (0-100), top-5 reasons, alerts / lead list
    reports/                evidence PDF (Jinja2 + WeasyPrint, ReportLab fallback)
    pipeline/run_pipeline.py
    api/                    FastAPI routes
  scripts/                  ingest.py, profile_data.py
  tests/                    fixtures are built in code (no real data)
frontend/                   placeholder for the dashboard
```

## Setup

Python 3.11+.

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

WeasyPrint needs Pango (`brew install pango` on macOS). If it is missing, PDFs fall back to ReportLab automatically.

Copy the 25 statements from `Proposed_Data_Randomized_Final.zip` into `data/raw/` (the
`~$25_SOA.xlsx` lock file is ignored):

```bash
unzip -j Proposed_Data_Randomized_Final.zip -d data/raw
```

## Run

From `backend/`:

```bash
.venv/bin/python -m app.pipeline.run_pipeline   # full pipeline, ~45 s on the full data
.venv/bin/python scripts/profile_data.py        # per-file rows, dates, parse rate, channel mix
.venv/bin/python scripts/ingest.py              # ingestion only
.venv/bin/uvicorn app.main:app --reload         # API on http://localhost:8000 (docs at /docs)
.venv/bin/python -m pytest                      # tests
```

Outputs: `data/processed/*.parquet`, `data/processed/stats.json` and `data/trace360.duckdb`
(tables `transactions`, `accounts`, `account_features`, `window_features`, `indicators`, `edges`,
`nodes`, `rings`, `network_scores`, `complaints`, `complaint_matches`, `scores`, `reasons`, `leads`, `alerts`).

## API

| Method | Path | |
|---|---|---|
| GET | `/api/stats` | pipeline stats |
| GET | `/api/alerts` | accounts at or above `ALERT_THRESHOLD` |
| GET | `/api/leads?tier=&limit=` | all accounts ranked by risk |
| GET | `/api/accounts` | account list |
| GET | `/api/accounts/{id}` | score, top-5 reasons, indicators, features, network |
| GET | `/api/accounts/{id}/timeline?limit=&offset=&direction=` | transactions + daily totals |
| GET | `/api/accounts/{id}/trail?hops=&direction=forward\|backward\|both` | money trail (id may be an account or a `CP-…` counterparty ref) |
| GET | `/api/graph/rings` | rings |
| GET | `/api/graph/rings/{ring_id}` | ring as Cytoscape.js elements |
| GET | `/api/complaints` | synthetic complaints with best match |
| GET | `/api/complaints/{id}/matches` | matches with confidence, account and ring |
| GET | `/api/reports/account/{id}.pdf` | evidence report |
| POST | `/api/pipeline/run` | re-run the pipeline and reload |

Names, account numbers, PAN, VPAs and long numbers are masked to their last 4 characters in every
response. Counterparty node ids are replaced by stable hashed refs (`CP-xxxxxxxxxx`). CORS allows
`http://localhost:5173`.

## How the data is handled

- **Layouts:** CRN statement (files 2, 4, 5; person-name headers, so D/C and CRN columns are found
  by content and position), debit/credit (6), ICORE short (7–9, 11, 12, 17–20, 22–24, 26, 28, 48),
  ICORE full (14–16, 25), misc ledger (1) and the 26-column extract (3, blank rows dropped, PAN never loaded).
- **Account identity:** one statement file is one subject account, `account_id = SOA<n>`. The
  account number is kept only where it is constant (files 2, 4–9) and is used solely to fold
  `acct:<number>` counterparties into subject nodes. Per-row account numbers are anonymised and
  never used for linking (files 26 and 48 share them as an artefact).
- **Time:** only ICORE `pstd_dt` is a usable timestamp (`time_reliable=True`). Every date in files
  1–6 and every `Tran_Date` is shuffled and is kept only as `raw_date`. Time features (dwell,
  bursts, night share) exist only for ICORE accounts.
- **Balances** are randomised and are never used.
- **Narrations:** real text only in files 2 and 4–9. The parser extracts channel and a typed
  counterparty key (`upi:`, `acct:`, `ifsc:`, `name:`). UPI VPAs are cut to their 11-character local
  part so that CRN-layout truncation matches ICORE. The `TXN-XXXXXXXXXX` tokens elsewhere contain
  channel codes only at the rate random strings would, so recovery from tokens is off
  (`RECOVER_CHANNEL_FROM_TOKENS`).
- **No labels, no complaints:** scores are rule- and network-based leads, not predictions.
  Complaints are synthetic, generated from real counterparties with typos and truncation, and
  labelled `synthetic=True`. "Dormant & Total Freeze" status is not treated as a label.

## Scoring

`risk = 100 × (0.65·indicator + 0.35·network + 0.0·anomaly)`. Weights, ramps and thresholds are in
`backend/app/config.py`.

- **Indicators** (each a 0–1 ramp, weighted mean over those applicable): pass-through ratio,
  fan-in, fan-out, small-credit/large-debit ratio, round-amount share, UPI share, fast outflow
  (credit value debited within 2 h), median dwell, burst hours, night share and transactions per
  active day.
- **Network:** shared counterparties with other subjects, PageRank (amount-weighted flow graph),
  weighted betweenness and ring membership. Rings come from Louvain (fixed seed) on the core graph
  of subject accounts plus counterparties shared by two or more of them.
