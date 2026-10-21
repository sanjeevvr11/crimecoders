# Trace360 frontend integration guide

Hand this folder (`docs/`) to whoever builds or redesigns the UI. It explains the seam between the
FastAPI backend and the React frontend, which parts to keep and which to replace, and how to
check that a new UI still works.

Files in `docs/`:

| File | What it is |
|---|---|
| `FRONTEND_INTEGRATION.md` | this guide |
| `openapi.json` | the API contract (generated from the backend; source of the TypeScript types) |
| `api_examples.md` | one real, masked example response per endpoint |

## 1. How the pieces fit

```
backend/app/schemas/api.py   Pydantic response models (the contract, defined once)
        │  python scripts/export_openapi.py
        ▼
docs/openapi.json            committed; a backend test fails if it is stale
        │  npm run gen:api
        ▼
frontend/src/api/schema.gen.ts   generated TypeScript (never edit by hand)
frontend/src/api/types.ts        friendly aliases: Lead, AccountDetail, Trail, …
frontend/src/api/client.ts       api.leads(), api.account(id), … the ONLY code that calls fetch
        ▼
frontend/src/hooks/index.ts      useLeads(), useAccount(id), … → { data, error, loading, reload }
        ▼
frontend/src/pages, components   screens; read data only through hooks
```

| Folder / file | Keep or replace in a redesign |
|---|---|
| `frontend/src/api/` | **Keep.** Regenerate with `npm run gen:api` when the backend changes. |
| `frontend/src/hooks/` | **Keep.** Add hooks here if a new screen needs a new combination of calls. |
| `frontend/src/pages/`, `frontend/src/components/` | **Replace freely.** |
| `frontend/src/App.tsx`, `main.tsx`, `styles.css` | Replace; keep the routes in §6 if links are shared. |
| `frontend/vite.config.ts`, `package.json` | Keep the `/api` proxy and the `gen:api` / `check:api` scripts. Add UI libraries as needed. |

Rule of thumb: a new UI may add any styling or component library, but it must not call `fetch`
directly or change `src/api/schema.gen.ts`.

## 2. Ports, URLs, environment, CORS

| What | Value |
|---|---|
| API | `http://localhost:8000` (interactive docs at `/docs`) |
| Web (dev) | `http://localhost:5173` (`npm run dev`) |
| Web (preview of a build) | `http://localhost:4173` (`npm run preview`) |
| `VITE_API_BASE_URL` | Empty (default) = same origin; in dev the Vite proxy forwards `/api/*` to the API. Set it (e.g. `http://localhost:8000`) to call the API directly. |
| `VITE_PROXY_TARGET` | Where the dev proxy forwards `/api` (default `http://localhost:8000`). |
| CORS | The API allows `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:4173`, `http://127.0.0.1:4173` (`backend/app/config.py`, `CORS_ORIGINS`). |

Copy `frontend/.env.example` to `frontend/.env` to change these.

## 3. Endpoints

All responses are JSON unless noted. Full field definitions are in `openapi.json`; a real example of
each is in `api_examples.md`. Errors return `{"detail": "..."}` with 404 (unknown id), 409 (pipeline
already running), 422 (bad query parameter) or 503 (pipeline not run yet).

| Method & path | Query params | Response type (`src/api/types.ts`) | Client function |
|---|---|---|---|
| `GET /api/health` | none | `{status}` | `api.health()` |
| `GET /api/stats` | none | `Stats` | `api.stats()` |
| `POST /api/pipeline/run` | none (takes about a minute) | `PipelineRunResult` | `api.runPipeline()` |
| `GET /api/leads` | `tier` (HIGH/MEDIUM/LOW), `limit` (≤1000) | `Lead[]` ranked by risk | `api.leads({tier, limit})` |
| `GET /api/alerts` | none | `Alert[]` (leads at or above the alert threshold) | `api.alerts()` |
| `GET /api/accounts` | `tier`, `role`, `ring_id`, `time_reliable`, `q` | `AccountListItem[]` | `api.accounts(filters)` |
| `GET /api/accounts/{id}` | none | `AccountDetail` | `api.account(id)` |
| `GET /api/accounts/{id}/timeline` | `limit` (≤2000), `offset`, `direction` (CR/DR), `order` (asc/desc: sorts every row by date and time before paging) | `Timeline` | `api.timeline(id, opts)` |
| `GET /api/accounts/{id}/trail` | `hops` (1-4), `direction` (forward/backward/both), `max_paths` (≤200) | `Trail` | `api.trail(id, opts)` |
| `GET /api/reports/account/{id}.pdf` | none | PDF file | `api.reportUrl(id)` (use as a link `href`) |
| `GET /api/graph/rings` | none | `Ring[]` | `api.rings()` |
| `GET /api/graph/rings/{ring_id}` | none | `RingDetail` (Cytoscape.js `elements`) | `api.ring(ringId)` |
| `GET /api/complaints` | none | `ComplaintListItem[]` | `api.complaints()` |
| `GET /api/complaints/{id}/matches` | none | `ComplaintMatches` | `api.complaintMatches(id)` |
| `GET /api/models/summary` | none | `ModelSummary` | `api.modelSummary()` |

`{id}` in `/trail` may also be a counterparty ref such as `CP-1a2b3c4d5e` (from `counterparty.ref`
or a trail node's `ref`), so a UI can follow money from a counterparty.

## 4. Hooks

Every hook returns `{ data, error, loading, reload }`, re-fetches when its arguments change, and
ignores stale responses. Import from `src/hooks`.

| Hook | Wraps | `data` type |
|---|---|---|
| `useStats()` | `/api/stats` | `Stats` |
| `useLeads(tier?)` | `/api/leads` | `Lead[]` |
| `useAlerts()` | `/api/alerts` | `Alert[]` |
| `useAccounts(filters)` | `/api/accounts` | `AccountListItem[]` |
| `useAccount(id)` | `/api/accounts/{id}` | `AccountDetail` |
| `useTimeline(id, limit, offset, direction?, order?)` | `/api/accounts/{id}/timeline` | `Timeline` |
| `useTrail(id, hops, direction, maxPaths)` | `/api/accounts/{id}/trail` | `Trail` |
| `useRings()` / `useRing(ringId)` | `/api/graph/rings[/{id}]` | `Ring[]` / `RingDetail` |
| `useComplaints()` / `useComplaintMatches(id)` | `/api/complaints[/{id}/matches]` | `ComplaintListItem[]` / `ComplaintMatches` |
| `useModelSummary()` | `/api/models/summary` | `ModelSummary` |

`useApi(fn, deps, enabled)` is the generic building block for new hooks. For actions (re-run the
pipeline) call `api.runPipeline()` directly from an event handler and then `reload()` the hooks.

## 5. Meaning of the data (UI must respect these)

- **Masking.** Names, account numbers, PAN, UPI ids and long numbers arrive already masked to the
  last 4 characters (`*******rora`). Never try to unmask; show them as given. Counterparty ids
  are hashed refs (`CP-…`); account ids are `SOA<n>`.
- **Scores.** `risk_score` (0-100) = base (65% rules + 35% network) + anomaly uplift.
  `risk_score_phase1` is the rules + network score, for comparison. `tier`: HIGH ≥ 70, MEDIUM ≥ 50, LOW.
- **Null is not zero.** `anomaly_score`, `flagged_weeks` and the weekly charts are `null` / empty for
  SOA1-6, whose statements have no reliable timestamps. Show "n/a", not 0.
- **Roles** (HDBSCAN): `collector`, `distributor`, `layering`, `normal-looking`, `unclassified`
  (no consistent behaviour), `sparse` (week with < 10 transactions).
- **Reasons.** `reasons[]` are the top 5, each with `source` (indicator / network / anomaly / role)
  and `contribution` in score points. `shap_reasons[]` are the flagged weeks, most unusual first.
- **Synthetic complaints.** Every complaint has `synthetic: true`; the UI must say so.
- **Model metrics are not accuracy.** `/api/models/summary.evaluation` holds synthetic-injection
  metrics; label them that way (the dataset has no fraud labels).
- **Leads, not verdicts.** Wording such as "flagged for review" is fine; "fraudster" or "guilty" is not.

## 6. Routes used by the current UI

`/` overview · `/leads` · `/accounts/:id` · `/network` and `/network/:ringId` · `/complaints` · `/models`

## 7. Replacing the UI: steps

1. Start the backend (`make api`) with processed data (`make pipeline` once).
2. In `frontend/`, keep `src/api/`, `src/hooks/`, `vite.config.ts` and the `package.json` scripts.
3. Replace `src/pages/`, `src/components/`, `src/App.tsx`, `src/styles.css` with the new design.
   Get data only through the hooks (or `api.*` for actions).
4. `npm install` any new UI dependencies, then `npm run typecheck` and `npm run build`.
5. Run `npm run dev` and work through the checklist below.

If the new design needs data the API does not provide yet: add the field or endpoint and its
response model in `backend/app/schemas/api.py`, run `python scripts/export_openapi.py` in
`backend/`, then `npm run gen:api` in `frontend/`, then add a client function and a hook.

## 8. Checklist for a new UI

- [ ] `npm run typecheck` and `npm run build` pass; `npm run check:api` reports no diff.
- [ ] No `fetch(` outside `src/api/client.ts` (`grep -rn "fetch(" src | grep -v src/api`).
- [ ] Overview shows `/api/stats` numbers (494,275 transactions, 25 accounts on the full data) and the alerts.
- [ ] Leads table ranks all 25 accounts; filters by level and role work.
- [ ] Account page for a time-reliable account (e.g. SOA8) shows the score breakdown, reasons,
      flagged weeks with SHAP reasons, weekly and daily charts, paginated transactions, money trail and
      a working PDF download.
- [ ] Account page for SOA2 shows "n/a" for anomaly and explains that dates are shuffled.
- [ ] Unknown account (`/accounts/SOA999`) shows an error state, not a blank page.
- [ ] Network page lists 3 rings and draws the selected ring; clicking an account node opens it.
- [ ] Complaints page marks complaints as synthetic and shows matches with confidence.
- [ ] Models page labels the metrics as synthetic-injection, not accuracy.
- [ ] Loading and API-down states are visible (stop the API and reload).
- [ ] Only masked identifiers appear anywhere.
