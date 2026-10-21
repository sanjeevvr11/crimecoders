/**
 * API client: KEEP when replacing the UI.
 *
 * The only place in the frontend that talks to the backend. One function per
 * endpoint; pages and components must use these (usually via hooks/), never fetch().
 *
 * Base URL: VITE_API_BASE_URL (e.g. http://localhost:8000) or, when empty, the
 * same origin, where the Vite dev proxy forwards /api to the backend.
 */
import type {
  AccountDetail, AccountFilters, AccountListItem, Alert, ComplaintListItem, ComplaintMatches, Lead,
  ModelSummary, NetworkOverview, NodeConnections, PipelineRunResult, Ring, RingDetail, SortOrder, Stats, Tier, Timeline, Trail, TrailDirection, TrailGraph,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Params = Record<string, string | number | boolean | undefined | null>;

export function apiUrl(path: string, params?: Params): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const q = qs.toString();
  return `${BASE}${path}${q ? `?${q}` : ""}`;
}

async function request<T>(path: string, params?: Params, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path, params), init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  stats: () => request<Stats>("/api/stats"),
  runPipeline: () => request<PipelineRunResult>("/api/pipeline/run", undefined, { method: "POST" }),

  leads: (opts: { tier?: Tier; limit?: number } = {}) => request<Lead[]>("/api/leads", opts),
  alerts: () => request<Alert[]>("/api/alerts"),

  accounts: (filters: AccountFilters = {}) => request<AccountListItem[]>("/api/accounts", { ...filters }),
  account: (id: string) => request<AccountDetail>(`/api/accounts/${encodeURIComponent(id)}`),
  /** order sorts all rows by date and time before paging: asc = oldest first, desc = newest first */
  timeline: (id: string, opts: { limit?: number; offset?: number; direction?: "CR" | "DR"; order?: SortOrder } = {}) =>
    request<Timeline>(`/api/accounts/${encodeURIComponent(id)}/timeline`, opts),
  /** id may be an account id (SOA7) or a counterparty ref (CP-xxxxxxxxxx) */
  trail: (id: string, opts: { hops?: number; direction?: TrailDirection; max_paths?: number } = {}) =>
    request<Trail>(`/api/accounts/${encodeURIComponent(id)}/trail`, opts),
  /** the trail merged into one graph for the Money Trail view: nodes by hop distance, transfers, chains, summary */
  trailGraph: (id: string, opts: { hops?: number; direction?: TrailDirection; max_paths?: number; shared?: number } = {}) =>
    request<TrailGraph>(`/api/accounts/${encodeURIComponent(id)}/trail/graph`, opts),
  /** URL for the evidence PDF (use as a link href; it is not JSON) */
  reportUrl: (id: string) => apiUrl(`/api/reports/account/${encodeURIComponent(id)}.pdf`),

  /** every investigated account and every counterparty shared by two or more of them */
  networkOverview: () => request<NetworkOverview>("/api/graph/overview"),
  /** transactions behind a graph node (ref = account id or CP-xxxxxxxxxx); account narrows it to one link */
  nodeTransactions: (ref: string, opts: { account?: string; limit?: number; offset?: number; order?: SortOrder } = {}) =>
    request<NodeConnections>(`/api/graph/nodes/${encodeURIComponent(ref)}/transactions`, opts),
  rings: () => request<Ring[]>("/api/graph/rings"),
  ring: (ringId: string) => request<RingDetail>(`/api/graph/rings/${encodeURIComponent(ringId)}`),

  complaints: () => request<ComplaintListItem[]>("/api/complaints"),
  complaintMatches: (id: string) => request<ComplaintMatches>(`/api/complaints/${encodeURIComponent(id)}/matches`),

  modelSummary: () => request<ModelSummary>("/api/models/summary"),
};
