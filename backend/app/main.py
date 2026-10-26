"""Trace360 API. Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api.routes import accounts, admin, alerts, auth, complaints, conclusion, data, graph, models, pipeline, reports
from app.auth.deps import require_role
from app.schemas.api import Health

app = FastAPI(title="Trace360", version="0.3.0", description="Mule account detection: rules, money-flow graph and unsupervised models")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

# Least role each router needs (single routes may ask for more, e.g. transactions need investigator).
# Viewer: read every screen. Investigator: also transactions and evidence PDFs. Admin: everything,
# identifiers unmasked, Ingestion, re-running the analysis, users and the audit log.
app.include_router(auth.router)
for module, role in ((pipeline, "viewer"), (alerts, "viewer"), (conclusion, "viewer"), (accounts, "viewer"), (graph, "viewer"),
                     (complaints, "viewer"), (models, "viewer"), (reports, "investigator"), (data, "admin"), (admin, "admin")):
    app.include_router(module.router, dependencies=[Depends(require_role(role))])


@app.get("/api/health", response_model=Health)
def health() -> dict:
    return {"status": "ok"}
