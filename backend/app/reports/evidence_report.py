"""Per-account evidence PDF: Jinja2 HTML rendered by WeasyPrint, with a
ReportLab fallback when WeasyPrint's system libraries are unavailable."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import config
from app.masking import mask, node_label
from app.models.summary import account_ml_summary
from app.scoring.reasons import top_reasons

log = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))


def build_context(store, account_id: str) -> dict:
    acc = store.table("accounts").set_index("account_id").loc[account_id]
    score = store.table("scores").set_index("account_id").loc[account_id]
    net = store.table("network_scores").set_index("account_id").loc[account_id]
    ind = store.table("indicators")
    edges = store.table("edges")
    e = edges.loc[edges["account_id"] == account_id].nlargest(10, "amount")
    subj = store.subject_ids
    cps = [{
        "label": node_label(r.src if r.direction == "CR" else r.dst, (r.src if r.direction == "CR" else r.dst) in subj),
        "direction": "in" if r.direction == "CR" else "out", "count": int(r.count), "amount": float(r.amount),
    } for r in e.itertuples(index=False)]
    matches = store.table("complaint_matches")
    complaints = store.table("complaints").set_index("complaint_id")
    m = matches.loc[matches["account_id"] == account_id].nlargest(15, "confidence")
    linked = [{
        "complaint_id": r.complaint_id,
        "reported": mask(complaints.loc[r.complaint_id, "reported_upi_or_account"]),
        "amount": float(complaints.loc[r.complaint_id, "amount"]),
        "confidence": float(r.confidence),
    } for r in m.itertuples(index=False)]
    return {
        "a": {
            "account_id": account_id, "holder_name": mask(acc["holder_name"]), "account_number": mask(acc["account_number"]),
            "source_file": acc["source_file"], "source_sheet": acc["source_sheet"], "layout": acc["layout"],
            "n_rows": int(acc["n_rows"]), "time_reliable": bool(acc["time_reliable"]),
        },
        "score": {**score.to_dict(), "ring_id": score["ring_id"] if isinstance(score["ring_id"], str) else None},
        "n_accounts": len(subj),
        "weights": config.SCORE_WEIGHTS,
        "reasons": top_reasons(account_id, ind, store.table("network_scores"), store.ml_context()),
        "ml": account_ml_summary(store, account_id),
        "indicators": ind.loc[ind["account_id"] == account_id].to_dict(orient="records"),
        "net": net.to_dict(),
        "counterparties": cps,
        "complaints": linked,
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }


def render_html(ctx: dict) -> str:
    return _env.get_template("evidence.html").render(**ctx)


def _reportlab_pdf(ctx: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    styles = getSampleStyleSheet()
    a, s = ctx["a"], ctx["score"]
    story = [
        Paragraph(f"Trace360 evidence report: {a['account_id']}", styles["Title"]),
        Paragraph(f"Risk score {s['risk_score']:.1f} ({s['tier']}), rank {s['rank']} of {ctx['n_accounts']}", styles["Heading2"]),
        Paragraph(f"Holder {a['holder_name']} · account {a['account_number'] or 'anonymised'} · {a['source_file']} ({a['layout']})", styles["Normal"]),
        Spacer(1, 8), Paragraph("Why this account was flagged", styles["Heading3"]),
    ]
    story += [Paragraph(f"{i}. {r['text']} ({r['source']}, {r['contribution']:.1f} pts)", styles["Normal"]) for i, r in enumerate(ctx["reasons"], 1)]
    story += [Spacer(1, 8), Paragraph("Lead for investigation only. Identifiers masked. Complaints are synthetic.", styles["Italic"])]
    SimpleDocTemplate(buf, pagesize=A4).build(story)
    return buf.getvalue()


def render_account_pdf(store, account_id: str) -> bytes:
    ctx = build_context(store, account_id)
    try:
        from weasyprint import HTML

        return HTML(string=render_html(ctx), base_url=str(TEMPLATE_DIR)).write_pdf()
    except (ImportError, OSError) as exc:  # missing pango/cairo system libs
        log.warning("WeasyPrint unavailable (%s); using ReportLab fallback", exc)
        return _reportlab_pdf(ctx)
