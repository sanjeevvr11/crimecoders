"""Trace360 API. Run from backend/:  uvicorn app.main:app --reload"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api.routes import accounts, alerts, complaints, graph, models, pipeline, reports
from app.schemas.api import Health

app = FastAPI(title="Trace360", version="0.3.0", description="Mule account detection: rules, money-flow graph and unsupervised models")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

for module in (pipeline, alerts, accounts, graph, complaints, reports, models):
    app.include_router(module.router)


@app.get("/api/health", response_model=Health)
def health() -> dict:
    return {"status": "ok"}
