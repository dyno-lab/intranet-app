from __future__ import annotations

import hmac
import logging
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.routing import APIRoute
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_db
from app.core.auth import require_admin
from app.core.roles import report_authorized_name
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.user import User
from app.services.full_monthly_report_targets import configured_targets

templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)
MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_TOTAL_BYTES = 60 * 1024 * 1024
PDF_FIELDS = ("staffing_pdf", "centers_pdf", "targets_pdf", "visit_roles_pdf", "signed_bonafide_pdf")


class _BoundedReportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def bounded(request: Request):
            if request.method != "POST":
                return await handler(request)
            # Bound the stream before multipart parsing writes temporary files,
            # including requests without Content-Length and unknown file fields.
            received = 0
            limit = MAX_TOTAL_BYTES + 1024 * 1024
            async def receive():
                nonlocal received
                message = await request.receive()
                received += len(message.get("body", b""))
                if received > limit:
                    # Let the multipart parser close any temporary files first.
                    raise MultiPartException("El envío supera el límite de 60 MB para anexos.")
                return message
            try:
                return await handler(Request(request.scope, receive=receive))
            except StarletteHTTPException as exc:
                if received > limit:
                    raise HTTPException(413, "El envío supera el límite de 60 MB para anexos.") from exc
                raise
        return bounded


router = APIRouter(route_class=_BoundedReportRoute)


def _selection(values, db: Session):
    try:
        ids = list(dict.fromkeys(int(value) for value in values.getlist("proposal_id")))
        month, year = int(values.get("month", "")), int(values.get("year", ""))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Selecciona las propuestas, el mes y el año.") from exc
    if not ids or len(ids) > 50 or any(value <= 0 for value in ids):
        raise HTTPException(400, "Selecciona entre una y 50 propuestas válidas.")
    if not 1 <= month <= 12 or not 2000 <= year <= 2100:
        raise HTTPException(400, "Mes o año inválido.")
    proposals = db.scalars(select(Proposal).where(Proposal.proposal_id.in_(ids)).order_by(Proposal.code)).all()
    if len(proposals) != len(ids):
        raise HTTPException(400, "Una de las propuestas seleccionadas no existe.")
    return ids, month, year, proposals


@router.get("/completo", response_class=HTMLResponse)
def full_monthly_prepare(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.api.routes.reports import MONTH_OPTIONS

    ids, month, year, proposals = _selection(request.query_params, db)
    token = request.session.setdefault("full_report_token", secrets.token_urlsafe(32))
    residentials = db.scalars(select(Residential).where(Residential.is_active == True).order_by(Residential.municipality, Residential.name)).all()  # noqa: E712
    return templates.TemplateResponse(request=request, name="ui/reports/full_monthly.html", context={
        "request": request, "current_user": current_user, "proposals": proposals,
        "selected_proposal_ids": ids, "selected_month": month, "selected_year": year,
        "month_options": MONTH_OPTIONS, "year_options": range(2000, max(date.today().year, year) + 2),
        "residentials": residentials, "full_report_token": token,
        "fixed_targets": configured_targets(proposals, residentials)["targets"],
        "letter_date": date.today().isoformat(),
        "authorized_name": report_authorized_name(current_user, request.query_params.get("authorized_name")),
    }, headers={"Cache-Control": "no-store"})


def _build_pdf(db, user, ids, month, year, supplements):
    # Imports remain local: installing PDF dependencies is only required when
    # using the new report, not when importing existing report routes.
    from app.services.full_monthly_report_data import build_full_monthly_report_data
    from app.services.full_monthly_report_pdf import build_full_monthly_pdf

    data = build_full_monthly_report_data(db, user, ids, month, year, supplements["authorized_name"])
    return build_full_monthly_pdf(data, supplements)


@router.post("/completo/pdf")
async def full_monthly_pdf(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    # Authenticate before parsing attachments or performing report queries.
    try:
        from app.services.full_monthly_report_pdf import validate_supplement_file
    except ImportError as exc:
        raise HTTPException(503, "La generación del informe completo requiere actualizar las dependencias de la aplicación.") from exc
    from app.services.report_pdf import PDFBackendUnavailableError, PDFRenderError

    async with request.form(max_files=25, max_fields=200, max_part_size=256 * 1024) as form:
        token = str(form.get("token", ""))
        expected = request.session.get("full_report_token", "")
        if not expected or not hmac.compare_digest(token.encode("utf-8"), expected.encode("utf-8")):
            raise HTTPException(403, "Vuelve a abrir la preparación del informe e intenta nuevamente.")
        ids, month, year, proposals = _selection(form, db)
        disposition = str(form.get("disposition", "inline"))
        if disposition not in {"inline", "attachment"}:
            raise HTTPException(400, "Formato de salida inválido.")
        supplements = {"files": {}, "photos": [], "targets": {}}
        for key, limit in (("narrative", 20000), ("centers_notes", 10000), ("authorized_name", 200),
                           ("letter_date", 10), ("letter_signer_name", 200), ("letter_signer_title", 200), ("letter_copy", 500)):
            value = form.get(key, "")
            if not isinstance(value, str) or len(value) > limit:
                raise HTTPException(400, f"El campo {key} supera el tamaño permitido.")
            supplements[key] = value.strip()
        if supplements["letter_date"]:
            try:
                date.fromisoformat(supplements["letter_date"])
            except ValueError as exc:
                raise HTTPException(400, "La fecha de la carta no es válida.") from exc
        supplements["authorized_name"] = report_authorized_name(current_user, supplements["authorized_name"])
        residentials = db.scalars(select(Residential).where(Residential.is_active == True)).all()  # noqa: E712
        valid_residential_ids = {row.residential_id for row in residentials}
        fixed_targets = configured_targets(proposals, residentials)["targets"]
        supplements["targets"].update(fixed_targets)
        for key, value in form.multi_items():
            if not key.startswith("target_") or value == "":
                continue
            try:
                residential_id, target = int(key[7:]), int(value)
            except (ValueError, TypeError) as exc:
                raise HTTPException(400, "Las metas deben ser números enteros.") from exc
            if residential_id not in valid_residential_ids or not 0 <= target <= 1000000:
                raise HTTPException(400, "Meta o residencial inválido.")
            if residential_id in fixed_targets and target != fixed_targets[residential_id]:
                raise HTTPException(400, "La meta está fijada para la propuesta. Vuelve a abrir la preparación del informe.")
            supplements["targets"][residential_id] = target
        total_bytes = 0
        for key in (*PDF_FIELDS, "photos"):
            uploads = [item for item in form.getlist(key) if isinstance(item, UploadFile) and item.filename]
            if len(uploads) > (20 if key == "photos" else 1):
                raise HTTPException(400, "Cantidad de archivos no permitida.")
            for upload in uploads:
                payload = await upload.read(MAX_FILE_BYTES + 1)
                total_bytes += len(payload)
                if len(payload) > MAX_FILE_BYTES or total_bytes > MAX_TOTAL_BYTES:
                    raise HTTPException(413, "Máximo 15 MB por archivo y 60 MB entre todos los anexos.")
                try:
                    item = await run_in_threadpool(validate_supplement_file, payload, key == "photos")
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                if key == "photos":
                    supplements["photos"].append(item)
                else:
                    supplements["files"][key] = item
        try:
            pdf = await run_in_threadpool(_build_pdf, db, current_user, ids, month, year, supplements)
        except PDFBackendUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc
        except PDFRenderError as exc:
            logger.exception("No se pudo generar el informe completo")
            raise HTTPException(500, "No se pudo generar el PDF completo. Intenta nuevamente o contacta al administrador.") from exc
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'{disposition}; filename="informe_mensual_completo_{year}_{month:02d}.pdf"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })
