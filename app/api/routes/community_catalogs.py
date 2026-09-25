import re
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.community_access import CommunityContext, require_community_admin, csrf_token, validate_csrf
from app.models.community_catalog import CPCatalogType, CPCatalogOption, CPProfileField
from app.services.community_catalog import CATEGORY_FIELDS

router = APIRouter(prefix="/community/catalogs", tags=["community-catalogs"])
templates = Jinja2Templates(directory="app/templates")


def redirect(message=None, error=None):
    return RedirectResponse("/community/catalogs?" + urlencode({"error": error} if error else {"msg": message}), status_code=303)


@router.get("")
def catalogs(request: Request, db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    options = db.execute(select(CPCatalogType, CPCatalogOption).join(CPCatalogOption).order_by(
        CPCatalogType.label, CPCatalogOption.sort_order, func.coalesce(CPCatalogOption.label, CPCatalogOption.value))).all()
    return templates.TemplateResponse(request=request, name="community/catalogs.html", context={
        "request": request, "cp": context, "current_user": context.user, "csrf_token": csrf_token(request),
        "message": request.query_params.get("msg"), "error": request.query_params.get("error"),
        "category_fields": CATEGORY_FIELDS, "options": options,
        "fields": db.scalars(select(CPProfileField).order_by(CPProfileField.sort_order, CPProfileField.label)).all(),
    })


@router.post("/options")
def add_option(request: Request, field_key: str = Form(...), value: str = Form(...), token: str = Form(...),
               db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    value = value.strip()
    if field_key not in CATEGORY_FIELDS or not value or len(value) > CATEGORY_FIELDS[field_key][1]:
        return redirect(error="Revise la categoría y la longitud de la opción.")
    catalog = db.scalar(select(CPCatalogType).where(CPCatalogType.field_key == field_key))
    try:
        if catalog is None:
            catalog = CPCatalogType(field_key=field_key, label=CATEGORY_FIELDS[field_key][0])
            db.add(catalog)
            db.flush()
        db.add(CPCatalogOption(catalog_type_id=catalog.catalog_type_id, value=value))
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(error="La opción ya existe en esa categoría.")
    return redirect(message="Opción añadida.")


@router.post("/fields")
def add_field(request: Request, field_key: str = Form(...), label: str = Form(...), field_type: str = Form(...),
              is_required: str | None = Form(default=None), sort_order: int = Form(0), token: str = Form(...),
              db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    field_key = field_key.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", field_key) or not label.strip() or len(label.strip()) > 150 or field_type not in {"text", "phone", "email"}:
        return redirect(error="Revise el identificador, etiqueta y tipo del campo.")
    db.add(CPProfileField(field_key=field_key, label=label.strip(), field_type=field_type,
                          is_required=is_required == "on", sort_order=sort_order))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return redirect(error="Ya existe un campo con ese identificador.")
    return redirect(message="Campo de perfil añadido.")


@router.post("/{kind}/{item_id}/state")
def toggle_item(request: Request, kind: str, item_id: int, enabled: bool = Form(...), token: str = Form(...),
                db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    model = {"options": CPCatalogOption, "fields": CPProfileField}.get(kind)
    item = db.get(model, item_id) if model else None
    if item is None:
        raise HTTPException(404, "Elemento no encontrado.")
    item.is_active = enabled
    db.commit()
    return redirect(message="Disponibilidad actualizada. Los valores históricos se conservan.")
