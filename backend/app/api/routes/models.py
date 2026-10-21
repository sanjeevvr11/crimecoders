import json

from fastapi import APIRouter, HTTPException

from app import config
from app.api.deps import get_store, records
from app.schemas.api import ModelSummary

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/summary", response_model=ModelSummary)
def models_summary() -> dict:
    """Model card, latest evaluation (synthetic-injection metrics, not real-world
    accuracy) and current role clusters."""
    card_path = config.MODEL_DIR / "model_card.json"
    if not card_path.exists():
        raise HTTPException(503, "models not trained yet; run the pipeline or scripts/train.py")
    eval_path = config.REPORTS_DIR / "model_evaluation.json"
    s = get_store()
    profiles = s.optional_table("role_profiles")
    roles = s.optional_table("account_roles")
    return {
        "model_card": json.loads(card_path.read_text()),
        "evaluation": json.loads(eval_path.read_text()) if eval_path.exists() else None,
        "role_profiles": records(profiles) if profiles is not None else [],
        "account_roles": records(roles) if roles is not None else [],
    }
