"""Response models for every API endpoint.

These are the frontend contract: docs/openapi.json is generated from them
(scripts/export_openapi.py) and the frontend's TypeScript types are generated
from that file. Change a model here -> re-export -> `npm run gen:api`.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- shared
class Reason(BaseModel):
    source: str = Field(description="indicator | network | anomaly | role")
    text: str
    contribution: float = Field(description="points this reason adds to the 0-100 risk score")


class CounterpartyRef(BaseModel):
    ref: str = Field(description="stable id: an account id (SOA7) or a hashed counterparty id (CP-xxxxxxxxxx)")
    label: str = Field(description="masked display label")


# ---------------------------------------------------------------- stats
class Stats(BaseModel):
    generated_at: str
    n_transactions: int
    n_accounts: int
    rows_per_layout: dict[str, int]
    time_reliable_rows: int
    narrations_with_text: int
    pct_narrations_parsed: float
    pct_text_narrations_parsed: float
    pct_with_counterparty: float
    channel_mix: dict[str, int]
    n_counterparties: int
    n_shared_counterparties: int
    n_edges: int
    n_rings: int
    n_alerts: int
    alert_threshold: float
    complaints: dict[str, Any]
    models: dict[str, Any] | None = None
    timings_s: dict[str, float]


class PipelineRunResult(BaseModel):
    status: str
    stats: Stats


# ---------------------------------------------------------------- leads / alerts
class Lead(BaseModel):
    rank: int
    account_id: str
    risk_score: float = Field(description="0-100, Phase 2 (rules + network + anomaly uplift)")
    tier: str = Field(description="HIGH | MEDIUM | LOW")
    indicator_score: float
    network_score: float
    anomaly_score: float | None = Field(None, description="0-1; null when the account has no reliable timestamps")
    anomaly_uplift: float | None = None
    risk_score_phase1: float | None = Field(None, description="rules + network only, for comparison")
    flagged_weeks: int | None = None
    role: str | None = None
    ring_id: str | None = None
    layout: str | None = None
    time_reliable: bool | None = None
    n_rows: int | None = None
    is_alert: bool
    top_reason: str | None = None


class Alert(Lead):
    alert_id: str


# ---------------------------------------------------------------- accounts
class AccountListItem(BaseModel):
    account_id: str
    source_file: str
    source_sheet: str
    layout: str
    holder_name: str | None = Field(None, description="masked")
    account_number: str | None = Field(None, description="masked; null when anonymised per row")
    time_reliable: bool
    n_rows: int
    risk_score: float | None = None
    tier: str | None = None
    rank: int | None = None
    role: str | None = None
    ring_id: str | None = None


class AccountScore(BaseModel):
    account_id: str
    risk_score: float
    risk_score_phase1: float | None = None
    base_score: float | None = None
    anomaly_uplift: float | None = None
    indicator_score: float
    network_score: float
    anomaly_score: float | None = None
    score_parts: str | None = None
    ring_id: str | None = None
    tier: str
    rank: int


class Indicator(BaseModel):
    indicator: str
    value: float
    subscore: float
    weight: float
    reason: str | None = None


class ShapReason(BaseModel):
    feature: str
    contribution: float
    text: str


class FlaggedWeek(BaseModel):
    week_start: str
    anomaly_score: float
    percentile: float = Field(description="share of training weeks that are less unusual")
    role: str | None = None
    reasons: list[ShapReason]


class AccountDetail(BaseModel):
    account_id: str
    holder_name: str | None = None
    account_number: str | None = None
    source_file: str
    source_sheet: str
    layout: str
    time_reliable: bool
    n_rows: int
    score: AccountScore
    reasons: list[Reason]
    indicators: list[Indicator]
    features: dict[str, Any]
    network: dict[str, Any]
    complaint_matches: int
    anomaly_score: float | None = None
    flagged_weeks: int | None = None
    role: str | None = None
    role_source: str | None = None
    shap_reasons: list[FlaggedWeek] = Field(description="flagged weeks, most unusual first")


class TimelineTxn(BaseModel):
    txn_uid: str
    txn_ts: str | None = None
    direction: str = Field(description="CR | DR")
    amount: float
    channel: str
    counterparty: CounterpartyRef | None = None
    counterparty_type: str
    narration: str | None = Field(None, description="masked")
    raw_date: str | None = None


class DailyFlow(BaseModel):
    date: str
    cr_amount: float
    dr_amount: float
    n_txns: int


class WeekScore(BaseModel):
    week_start: str
    anomaly_score: float
    is_flagged: bool
    role: str | None = None


class Timeline(BaseModel):
    account_id: str
    total: int
    offset: int
    limit: int
    time_reliable: bool
    transactions: list[TimelineTxn]
    daily: list[DailyFlow]
    weeks: list[WeekScore] = Field(default_factory=list, description="weekly anomaly scores (time-reliable accounts)")


class TrailNode(BaseModel):
    ref: str
    label: str
    is_subject: bool


class TrailEdge(BaseModel):
    source: str
    target: str
    amount: float
    count: int
    first_ts: str | None = None
    last_ts: str | None = None


class TrailPath(BaseModel):
    direction: str
    hops: int
    total_amount: float
    nodes: list[TrailNode]
    edges: list[TrailEdge]


class Trail(BaseModel):
    start: str
    hops: int | None = None
    direction: str | None = None
    paths: list[TrailPath]


class TrailGraphNode(BaseModel):
    ref: str
    label: str
    is_subject: bool
    is_start: bool
    kind: str = Field(description="subject | upi | account | ifsc | name | other")
    level: int = Field(description="signed hop distance from the start: <0 money came from here, >0 money went here, 0 = start or a linked account")
    amount_in: float = Field(description="money into this node along the trail (INR)")
    amount_out: float = Field(description="money out of this node along the trail (INR)")
    n_subject_links: int = Field(description="how many investigated accounts this node deals with")
    circular: bool = Field(description="reached both forward and backward: money flows both from and back to the start through it")
    bank: str | None = None
    risk_score: float | None = None
    tier: str | None = None
    ring_id: str | None = None
    role: str | None = None


class TrailGraphEdge(BaseModel):
    source: str
    target: str
    amount: float
    count: int
    first_ts: str | None = None
    last_ts: str | None = None
    hop: int
    direction: str = Field(description="forward | backward, relative to the start")
    link: str = Field(description="trail = on a traced path; shared = a start counterparty dealing with another investigated account")


class TrailChain(BaseModel):
    direction: str
    kind: str = Field(description="cross-account (reaches another investigated account) | shared (common counterparty) | exit (leaves the investigated set)")
    hops: int
    amount: float = Field(description="smallest hop on the chain: the most money that can have moved end to end (INR)")
    nodes: list[str]
    first_ts: str | None = None
    last_ts: str | None = None


class TrailSummary(BaseModel):
    n_nodes: int
    n_edges: int
    n_chains: int
    n_cross_account_chains: int
    n_shared_counterparties: int
    n_intermediaries: int = Field(description="nodes that both receive and pass on money along the trail")
    n_circular: int = Field(description="nodes that money flows both to and from (round-tripping)")
    accounts_reached: list[str]
    amount_in: float = Field(description="money traced into the start account (INR)")
    amount_out: float = Field(description="money traced out of the start account (INR)")
    first_ts: str | None = None
    last_ts: str | None = None
    time_reliable: bool


class TrailGraph(BaseModel):
    start: str
    hops: int
    direction: str
    summary: TrailSummary
    nodes: list[TrailGraphNode]
    edges: list[TrailGraphEdge]
    chains: list[TrailChain]


# ---------------------------------------------------------------- conclusion
class ConclusionFinding(BaseModel):
    tab: str = Field(description="the screen the finding comes from: Leads, Money Trail, Network, Complaints, Models, Data")
    route: str = Field(description="frontend route of that screen")
    title: str
    text: str


class ConclusionTrail(BaseModel):
    amount_in: float
    amount_out: float
    n_chains: int
    n_cross_account_chains: int
    n_circular: int
    n_intermediaries: int
    accounts_reached: list[str]


class ConclusionAccount(BaseModel):
    account_id: str
    rank: int
    risk_score: float
    tier: str
    verdict: str = Field(description="Priority investigation | Investigate | Monitor")
    role: str | None = None
    ring_id: str | None = None
    linked_accounts: list[str] = Field(description="ring partners and accounts reached by the money trail")
    reasons: list[str] = Field(description="top reasons, strongest first")
    complaint_matches: int = Field(description="distinct (synthetic) complaints matched to this account")
    flagged_weeks: int | None = None
    time_reliable: bool
    trail: ConclusionTrail | None = Field(None, description="null when the statement names no counterparties")
    action: str = Field(description="suggested next step for an investigator")


class ConclusionRing(BaseModel):
    ring_id: str
    accounts: list[str]
    n_shared_counterparties: int
    total_amount: float
    max_risk: float
    text: str


class ConclusionChain(BaseModel):
    start: str
    nodes: list[str]
    labels: list[str] = Field(description="masked display label of each node")
    amount: float = Field(description="smallest hop on the chain (INR)")
    hops: int


class Conclusion(BaseModel):
    generated_at: str
    headline: str
    summary: str
    counts: dict[str, int] = Field(description="accounts, alerts, HIGH, MEDIUM, LOW, watchlist, no_action")
    findings: list[ConclusionFinding] = Field(description="one conclusion per screen")
    accounts: list[ConclusionAccount] = Field(description="accounts at or above the alert threshold, highest risk first")
    watchlist: list[ConclusionAccount] = Field(description="below the threshold but close to it or with several unusual weeks")
    rings: list[ConclusionRing]
    top_chains: list[ConclusionChain] = Field(description="largest chains that carry money from one investigated account to another")
    limitations: list[str]
    next_steps: list[str]


# ---------------------------------------------------------------- data (dataset management)
class SheetCheck(BaseModel):
    sheet: str = Field(description="sheet name, digits masked")
    layout: str = Field(description="detected statement layout, e.g. icore_short")
    n_rows: int
    first_date: str | None = Field(None, description="null when the layout's dates are unreliable")
    last_date: str | None = None
    time_reliable: bool
    pct_counterparty: float = Field(description="% of rows where a counterparty (UPI id, account, IFSC) was found")


class StagedFile(BaseModel):
    id: str = Field(description="id of the uploaded file; empty when rejected")
    original_name: str = Field(description="uploaded file name, digits masked")
    size_bytes: int
    uploaded_at: str
    ok: bool = Field(description="false = rejected and not kept; see error")
    error: str | None = None
    sheets: list[SheetCheck]


class DataFile(BaseModel):
    name: str = Field(description="stored name N_SOA.<ext>; N becomes the account id SOA<N>")
    original_name: str | None = Field(None, description="uploaded file name (digits masked); null for the original dataset")
    uploaded_at: str | None = None
    size_bytes: int
    analysed: bool = Field(description="included in the current results")
    accounts: list[str]
    layouts: list[str]
    n_rows: int | None = None
    time_reliable: bool | None = None
    has_counterparties: bool | None = None


class DataArchive(BaseModel):
    name: str
    created_at: str | None = None
    reason: str = Field(description="replaced | removed")
    files: list[str] = Field(description="file names, digits masked")
    n_files: int


class PipelineJob(BaseModel):
    state: str = Field(description="idle | running | done | failed")
    mode: str | None = Field(None, description="add | replace | restore | remove | rerun")
    step: str | None = Field(None, description="last finished step")
    steps: list[str]
    steps_done: int
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    n_transactions: int | None = None
    n_accounts: int | None = None
    n_alerts: int | None = None


class DatasetState(BaseModel):
    files: list[DataFile]
    staged: list[StagedFile]
    archives: list[DataArchive]
    job: PipelineJob
    needs_rerun: bool = Field(description="the statements changed since the results were computed")
    accepted: list[str]
    max_upload_mb: int


class RunRequest(BaseModel):
    mode: Literal["add", "replace"] = Field("add", description="add = uploads join the current statements; replace = uploads become the whole dataset (current statements are archived)")


# ---------------------------------------------------------------- graph
class Ring(BaseModel):
    ring_id: str
    subject_accounts: list[str]
    n_subjects: int
    n_shared_counterparties: int
    n_nodes: int
    n_edges: int
    total_amount: float


class CyNodeData(BaseModel):
    id: str
    label: str
    is_subject: bool
    degree: int
    ring_id: str | None = Field(None, description="ring of an investigated account (overview graph)")


class CyNode(BaseModel):
    data: CyNodeData


class CyEdgeData(BaseModel):
    id: str
    source: str
    target: str
    amount: float
    count: int | None = Field(None, description="number of transactions on this link")


class CyEdge(BaseModel):
    data: CyEdgeData


class CyElements(BaseModel):
    nodes: list[CyNode]
    edges: list[CyEdge]


class RingDetail(BaseModel):
    ring: Ring
    elements: CyElements


class NetworkOverview(BaseModel):
    rings: list[Ring]
    elements: CyElements = Field(description="every investigated account plus every counterparty shared by two or more of them")
    n_accounts: int
    n_unlinked_accounts: int = Field(description="accounts that share no counterparty with any other account")


class ConnectionAccount(BaseModel):
    account_id: str
    ring_id: str | None = None
    n_txns: int
    cr_amount: float
    dr_amount: float
    n_shared_counterparties: int = Field(description="counterparties this account shares with the clicked node (or with the clicked account)")


class ConnectionTxn(TimelineTxn):
    account_id: str


class NodeConnections(BaseModel):
    node: CounterpartyRef
    is_subject: bool
    ring_id: str | None = None
    account: str | None = Field(None, description="the account filter, when set")
    accounts: list[ConnectionAccount] = Field(description="counterparty: the investigated accounts it deals with. Account: the other accounts it shares counterparties with")
    total: int
    offset: int
    limit: int
    transactions: list[ConnectionTxn] = Field(description="sorted by date; for an account, only its transactions with shared counterparties")


# ---------------------------------------------------------------- complaints
class Complaint(BaseModel):
    complaint_id: str
    date: str | None = None
    victim: str
    reported_upi_or_account: str | None = Field(None, description="masked")
    reported_type: str
    amount: float
    channel: str
    synthetic: bool


class ComplaintListItem(Complaint):
    n_matches: int
    best_confidence: float | None = None
    best_account_id: str | None = None


class ComplaintMatch(BaseModel):
    complaint_id: str
    id_score: float
    txn_uid: str | None = None
    account_id: str
    amount_match: bool
    time_match: bool | None = None
    confidence: float
    ring_id: str | None = None
    counterparty: CounterpartyRef


class ComplaintMatches(BaseModel):
    complaint: Complaint
    matches: list[ComplaintMatch]


# ---------------------------------------------------------------- models
class ModelSummary(BaseModel):
    model_card: dict[str, Any]
    evaluation: dict[str, Any] | None = Field(None, description="synthetic-injection metrics, NOT real-world accuracy")
    role_profiles: list[dict[str, Any]]
    account_roles: list[dict[str, Any]]


class Health(BaseModel):
    status: str


class PublicSummary(BaseModel):
    """Counts only, shown on the landing page before sign-in: no names, accounts or scores."""
    ready: bool = Field(description="false until the analysis has been run")
    n_statements: int = 0
    n_transactions: int = 0
    n_counterparties: int = 0
    n_leads: int = Field(0, description="accounts at or above the alert threshold")


# ---------------------------------------------------------------- sign-in, users, audit
Role = Literal["viewer", "investigator", "admin"]


class User(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    role: Role = Field(description="viewer: read the screens; investigator: also transactions and evidence PDFs; "
                                   "admin: everything, identifiers unmasked, Ingestion and users")
    active: bool
    created_at: str | None = None
    last_login_at: str | None = None


class Me(BaseModel):
    user: User
    auth_enabled: bool = Field(description="false when sign-in is switched off (TRACE360_AUTH=off)")
    unmasked: bool = Field(description="true when this user sees names, account numbers and UPI ids in full")


class LoginRequest(BaseModel):
    username: str
    password: str


class SignedOut(BaseModel):
    status: Literal["signed out"]


class UserCreate(BaseModel):
    username: str
    password: str = Field(description="at least 8 characters")
    role: Role
    display_name: str | None = None


class UserUpdate(BaseModel):
    role: Role | None = None
    active: bool | None = Field(None, description="false blocks sign-in and ends the user's sessions")
    password: str | None = Field(None, description="new password (reset); ends the user's sessions")
    display_name: str | None = None


class AuditEntry(BaseModel):
    id: int
    ts: str
    username: str | None = None
    role: str | None = None
    action: str = Field(description="login, login_failed, logout, view_account, view_transactions, view_connections, "
                                    "download_report, run_pipeline, data_upload, data_remove, data_run, data_restore, "
                                    "user_create, user_update")
    target: str | None = Field(None, description="the account, user or file acted on")
    unmasked: bool = Field(description="the user saw identifiers in full")
    ip: str | None = None
    detail: str | None = None


class AuditPage(BaseModel):
    total: int
    items: list[AuditEntry]
