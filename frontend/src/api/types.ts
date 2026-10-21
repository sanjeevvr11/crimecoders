/**
 * API response types: KEEP when replacing the UI.
 *
 * Every type is an alias of the generated OpenAPI schema (schema.gen.ts), which
 * is produced from docs/openapi.json by `npm run gen:api`. Never edit
 * schema.gen.ts by hand; change the backend model, re-export, regenerate.
 */
import type { components } from "./schema.gen";

type S = components["schemas"];

export type Stats = S["Stats"];
export type Lead = S["Lead"];
export type Alert = S["Alert"];
export type Conclusion = S["Conclusion"];
export type ConclusionAccount = S["ConclusionAccount"];
export type ConclusionChain = S["ConclusionChain"];
export type ConclusionFinding = S["ConclusionFinding"];
export type ConclusionRing = S["ConclusionRing"];
export type AccountListItem = S["AccountListItem"];
export type AccountDetail = S["AccountDetail"];
export type AccountScore = S["AccountScore"];
export type Reason = S["Reason"];
export type Indicator = S["Indicator"];
export type FlaggedWeek = S["FlaggedWeek"];
export type ShapReason = S["ShapReason"];
export type Timeline = S["Timeline"];
export type TimelineTxn = S["TimelineTxn"];
export type DailyFlow = S["DailyFlow"];
export type WeekScore = S["WeekScore"];
export type Trail = S["Trail"];
export type TrailPath = S["TrailPath"];
export type TrailNode = S["TrailNode"];
export type TrailEdge = S["TrailEdge"];
export type TrailGraph = S["TrailGraph"];
export type TrailGraphNode = S["TrailGraphNode"];
export type TrailGraphEdge = S["TrailGraphEdge"];
export type TrailChain = S["TrailChain"];
export type TrailSummary = S["TrailSummary"];
export type Ring = S["Ring"];
export type RingDetail = S["RingDetail"];
export type NetworkOverview = S["NetworkOverview"];
export type NodeConnections = S["NodeConnections"];
export type ConnectionAccount = S["ConnectionAccount"];
export type ConnectionTxn = S["ConnectionTxn"];
export type CyElements = S["CyElements"];
export type ComplaintListItem = S["ComplaintListItem"];
export type ComplaintMatches = S["ComplaintMatches"];
export type ComplaintMatch = S["ComplaintMatch"];
export type CounterpartyRef = S["CounterpartyRef"];
export type ModelSummary = S["ModelSummary"];
export type PipelineRunResult = S["PipelineRunResult"];

export type Tier = "HIGH" | "MEDIUM" | "LOW";
export type Role = "collector" | "distributor" | "layering" | "normal-looking" | "unclassified" | "sparse";
export type TrailDirection = "forward" | "backward" | "both";
/** timeline date order: asc = oldest first, desc = newest first */
export type SortOrder = "asc" | "desc";

export interface AccountFilters {
  tier?: Tier;
  role?: string;
  ring_id?: string;
  time_reliable?: boolean;
  q?: string;
}
