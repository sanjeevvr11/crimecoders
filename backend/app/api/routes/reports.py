from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.api.deps import get_store
from app.reports.evidence_report import render_account_pdf
from app.auth.deps import audited, require_role

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/account/{account_id}.pdf", response_class=Response,
            dependencies=[Depends(require_role("investigator")), audited("download_report", "account_id")],
            responses={200: {"content": {"application/pdf": {}}, "description": "evidence report PDF"}})
def account_report(account_id: str) -> Response:
    s = get_store()
    s.require_account(account_id)
    pdf = render_account_pdf(s, account_id)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="trace360_{account_id}.pdf"'})
