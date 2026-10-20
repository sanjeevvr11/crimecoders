from fastapi import APIRouter, Query

from app.api.deps import get_store, records
from app.schemas.api import Alert, Lead

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[Alert])
def list_alerts() -> list[dict]:
    return records(get_store().table("alerts"))


@router.get("/leads", response_model=list[Lead])
def list_leads(tier: str | None = Query(None, description="HIGH, MEDIUM or LOW"), limit: int = Query(100, ge=1, le=1000)) -> list[dict]:
    leads = get_store().table("leads")
    if tier:
        leads = leads.loc[leads["tier"] == tier.upper()]
    return records(leads.head(limit))
