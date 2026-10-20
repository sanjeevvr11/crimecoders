"""Response models for the main list endpoints (others return plain JSON)."""
from __future__ import annotations

from pydantic import BaseModel


class Reason(BaseModel):
    source: str
    text: str
    contribution: float


class Lead(BaseModel):
    rank: int
    account_id: str
    risk_score: float
    tier: str
    indicator_score: float
    network_score: float
    anomaly_score: float
    ring_id: str | None = None
    layout: str | None = None
    time_reliable: bool | None = None
    n_rows: int | None = None
    is_alert: bool
    top_reason: str | None = None


class Alert(Lead):
    alert_id: str


class Ring(BaseModel):
    ring_id: str
    subject_accounts: list[str]
    n_subjects: int
    n_shared_counterparties: int
    n_nodes: int
    n_edges: int
    total_amount: float
