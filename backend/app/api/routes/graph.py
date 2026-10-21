from fastapi import APIRouter, HTTPException

from app.api.deps import get_store, records
from app.graph.communities import ring_cytoscape
from app.masking import node_label, node_ref
from app.schemas.api import Ring, RingDetail

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/rings", response_model=list[Ring])
def list_rings() -> list[dict]:
    rings = get_store().table("rings").copy()
    rings["subject_accounts"] = rings["subject_accounts"].map(list)
    return records(rings)


@router.get("/rings/{ring_id}", response_model=RingDetail)
def ring_detail(ring_id: str) -> dict:
    s = get_store()
    rings = s.table("rings")
    row = rings.loc[rings["ring_id"] == ring_id]
    if row.empty:
        raise HTTPException(404, f"unknown ring '{ring_id}'")
    subj = s.subject_ids
    members = s.table("nodes")[["node_id", "community", "ring_id"]]
    elements = ring_cytoscape(
        s.core, members, ring_id,
        label_fn=lambda n: node_label(n, n in subj),
        id_fn=lambda n: node_ref(n, n in subj),
    )
    for el in elements["nodes"]:
        el["data"]["is_subject"] = el["data"]["id"] in subj
    info = records(row.assign(subject_accounts=row["subject_accounts"].map(list)))[0]
    return {"ring": info, "elements": elements}
