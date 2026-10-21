"""Response models for every API endpoint.

These are the frontend contract: docs/openapi.json is generated from them
(scripts/export_openapi.py) and the frontend's TypeScript types are generated
from that file. Change a model here -> re-export -> `npm run gen:api`.
"""
from __future__ import annotations

from typing import Any

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


class CyNode(BaseModel):
    data: CyNodeData


class CyEdgeData(BaseModel):
    id: str
    source: str
    target: str
    amount: float


class CyEdge(BaseModel):
    data: CyEdgeData


class CyElements(BaseModel):
    nodes: list[CyNode]
    edges: list[CyEdge]


class RingDetail(BaseModel):
    ring: Ring
    elements: CyElements


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
