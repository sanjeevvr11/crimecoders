"""The Data screen: upload statements, check them, add or replace the dataset, re-run the analysis.

The analysis runs in a background thread (about a minute on the full data);
the frontend polls GET /api/data/job for progress.
"""
import threading
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.deps import get_store, pipeline_lock
from app.ingestion import dataset
from app.masking import mask_digits
from app.pipeline.run_pipeline import STEPS, run
from app.schemas.api import DatasetState, PipelineJob, RunRequest, StagedFile
from app.auth.deps import audited

router = APIRouter(prefix="/api/data", tags=["data"])

_job: dict = {"state": "idle", "mode": None, "step": None, "steps_done": 0, "started_at": None, "finished_at": None,
              "error": None, "n_transactions": None, "n_accounts": None, "n_alerts": None}
_job_lock = threading.Lock()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def job_state() -> dict:
    with _job_lock:
        return {**_job, "steps": list(STEPS)}


def _set_job(**kw) -> None:
    with _job_lock:
        _job.update(kw)


def _worker() -> None:
    store = get_store()
    try:
        stats = run(processed_dir=store.processed_dir, on_step=lambda name: _set_job(step=name, steps_done=STEPS.index(name) + 1))
        store.reload()
        _set_job(state="done", n_transactions=stats["n_transactions"], n_accounts=stats["n_accounts"], n_alerts=stats["n_alerts"])
    except Exception as e:  # reported to the UI; the previous results stay in place
        _set_job(state="failed", error=str(e) or type(e).__name__)
    finally:
        _set_job(finished_at=_now())
        pipeline_lock.release()


def _start(mode: str, change=None) -> None:
    """Take the pipeline lock, apply `change` to the statements, then analyse in the background."""
    if not pipeline_lock.acquire(blocking=False):
        raise HTTPException(409, "an analysis is already running; wait for it to finish")
    try:
        if change:
            change()
    except dataset.DatasetError as e:
        pipeline_lock.release()
        raise HTTPException(400, str(e)) from e
    except BaseException:
        pipeline_lock.release()
        raise
    _set_job(state="running", mode=mode, step=None, steps_done=0, started_at=_now(), finished_at=None, error=None,
             n_transactions=None, n_accounts=None, n_alerts=None)
    threading.Thread(target=_worker, name="trace360-pipeline", daemon=True).start()


def _require_idle() -> None:
    if pipeline_lock.locked():
        raise HTTPException(409, "an analysis is running; wait for it to finish")


def _analysed() -> dict[str, dict]:
    """source file -> what the current results know about it."""
    s = get_store()
    if not s.ready:
        return {}
    try:
        acc = s.table("accounts")
        g = s.graph
    except HTTPException:
        return {}
    out: dict[str, dict] = {}
    for a in acc.itertuples(index=False):
        d = out.setdefault(a.source_file, {"accounts": [], "layouts": [], "n_rows": 0, "time_reliable": False, "has_counterparties": False})
        d["accounts"].append(a.account_id)
        if a.layout not in d["layouts"]:
            d["layouts"].append(a.layout)
        d["n_rows"] += int(a.n_rows)
        d["time_reliable"] |= bool(a.time_reliable)
        d["has_counterparties"] |= bool(a.account_id in g and g.degree(a.account_id) > 0)
    return out


def _masked_staged(rec: dict) -> dict:
    return {**rec, "original_name": mask_digits(rec["original_name"]),
            "sheets": [{**sh, "sheet": mask_digits(sh["sheet"])} for sh in rec["sheets"]]}


def dataset_state() -> dict:
    analysed = _analysed()
    files = []
    for f in dataset.current_files():
        a = analysed.get(f["name"])
        files.append({
            **f, "original_name": mask_digits(f["original_name"]) if f["original_name"] else None,
            "analysed": a is not None,
            "accounts": a["accounts"] if a else [], "layouts": a["layouts"] if a else [],
            "n_rows": a["n_rows"] if a else None, "time_reliable": a["time_reliable"] if a else None,
            "has_counterparties": a["has_counterparties"] if a else None,
        })
    archives = [{**a, "files": [mask_digits(n) for n in a["files"]]} for a in dataset.archives()]
    return {
        "files": files, "staged": [_masked_staged(r) for r in dataset.staged()], "archives": archives, "job": job_state(),
        "needs_rerun": {f["name"] for f in files} != set(analysed),
        "accepted": list(dataset.ALLOWED_SUFFIXES), "max_upload_mb": dataset.MAX_UPLOAD_MB,
    }


@router.get("", response_model=DatasetState)
def get_dataset() -> dict:
    """The statements in the dataset, uploads waiting to be analysed, archived sets and the analysis job."""
    return dataset_state()


@router.get("/job", response_model=PipelineJob)
def get_job() -> dict:
    return job_state()


@router.post("/staged", response_model=StagedFile, dependencies=[audited("data_upload")])
async def upload_statement(request: Request, filename: str = Query(..., description="the file's original name, e.g. 30_SOA.xlsx")) -> dict:
    """Upload one statement as the raw request body. It is checked like the pipeline would read it;
    a file that cannot be analysed comes back with ok=false and is not kept."""
    _require_idle()
    data = await request.body()
    return _masked_staged(dataset.stage(filename, data))


@router.delete("/staged/{file_id}", response_model=DatasetState)
def delete_staged(file_id: str) -> dict:
    _require_idle()
    try:
        dataset.unstage(file_id)
    except dataset.DatasetError as e:
        raise HTTPException(404, str(e)) from e
    return dataset_state()


@router.post("/run", response_model=DatasetState, dependencies=[audited("data_run")])
def run_analysis(body: RunRequest) -> dict:
    """Move the uploads into the dataset (add, or replace the current statements) and analyse in the background.
    With no uploads and mode=add it simply re-analyses the current statements."""
    has_uploads = bool(dataset.staged())
    _start(body.mode if has_uploads else "rerun", (lambda: dataset.apply_staged(body.mode)) if has_uploads or body.mode == "replace" else None)
    return dataset_state()


@router.delete("/files/{name}", response_model=DatasetState, dependencies=[audited("data_remove", "name")])
def remove_statement(name: str) -> dict:
    """Set a statement aside (it goes to the archive and can be restored), then re-analyse."""
    _start("remove", lambda: dataset.remove_file(name))
    return dataset_state()


@router.post("/archives/{name}/restore", response_model=DatasetState, dependencies=[audited("data_restore", "name")])
def restore_archive(name: str) -> dict:
    """Bring an archived set back (a replaced dataset swaps places with the current one), then re-analyse."""
    _start("restore", lambda: dataset.restore(name))
    return dataset_state()
