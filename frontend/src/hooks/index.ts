/**
 * Data hooks: KEEP when replacing the UI.
 *
 * Each hook wraps one api.* call and returns { data, error, loading, reload }.
 * A redesigned UI should get all its data through these hooks.
 */
import { api } from "../api";
import type { AccountFilters, SortOrder, Tier, TrailDirection } from "../api/types";
import { useApi } from "./useApi";

export { useApi } from "./useApi";
export type { ApiState } from "./useApi";

export const useStats = () => useApi(() => api.stats(), []);
export const useLeads = (tier?: Tier) => useApi(() => api.leads({ tier, limit: 1000 }), [tier]);
export const useAlerts = () => useApi(() => api.alerts(), []);
export const useConclusion = () => useApi(() => api.conclusion(), []);
export const useAccounts = (f: AccountFilters = {}) =>
  useApi(() => api.accounts(f), [f.tier, f.role, f.ring_id, f.time_reliable, f.q]);
export const useAccount = (id: string | undefined) => useApi(() => api.account(id!), [id], !!id);
export const useTimeline = (id: string | undefined, limit = 200, offset = 0, direction?: "CR" | "DR", order: SortOrder = "asc") =>
  useApi(() => api.timeline(id!, { limit, offset, direction, order }), [id, limit, offset, direction, order], !!id);
export const useTrail = (id: string | undefined, hops: number, direction: TrailDirection, maxPaths = 50) =>
  useApi(() => api.trail(id!, { hops, direction, max_paths: maxPaths }), [id, hops, direction, maxPaths], !!id);
export const useTrailGraph = (id: string | undefined, hops: number, direction: TrailDirection) =>
  useApi(() => api.trailGraph(id!, { hops, direction }), [id, hops, direction], !!id);
export const useRings = () => useApi(() => api.rings(), []);
export const useNetworkOverview = () => useApi(() => api.networkOverview(), []);
export const useNodeTransactions = (ref: string | undefined, account?: string, limit = 50, offset = 0, order: SortOrder = "asc") =>
  useApi(() => api.nodeTransactions(ref!, { account, limit, offset, order }), [ref, account, limit, offset, order], !!ref);
export const useRing = (ringId: string | undefined) => useApi(() => api.ring(ringId!), [ringId], !!ringId);
export const useComplaints = () => useApi(() => api.complaints(), []);
export const useComplaintMatches = (id: string | undefined) => useApi(() => api.complaintMatches(id!), [id], !!id);
export const useModelSummary = () => useApi(() => api.modelSummary(), []);
export const useDataset = () => useApi(() => api.dataset(), []);
