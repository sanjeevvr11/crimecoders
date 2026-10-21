from fastapi import APIRouter, HTTPException

from app.api.deps import get_store, pipeline_lock
from app.pipeline.run_pipeline import run
from app.schemas.api import PipelineRunResult, Stats

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/stats", response_model=Stats)
def stats() -> dict:
    return get_store().stats()


@router.post("/pipeline/run", response_model=PipelineRunResult)
def run_pipeline() -> dict:
    """Re-run ingestion, features, graph, complaints and scoring (about a minute on the full data)."""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "pipeline already running")
    try:
        store = get_store()
        result = run(processed_dir=store.processed_dir)
        store.reload()
        return {"status": "ok", "stats": result}
    finally:
        pipeline_lock.release()
