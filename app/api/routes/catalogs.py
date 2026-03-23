from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import require_admin
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def admin_catalogs(
    request: Request,
    selected_type_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    catalog_types = db.execute(
        select(CatalogType).order_by(CatalogType.name)
    ).scalars().all()

    if selected_type_id is None and catalog_types:
        selected_type_id = catalog_types[0].catalog_type_id

    selected_type = db.get(CatalogType, selected_type_id) if selected_type_id else None
    options = []
    if selected_type:
        options = db.execute(
            select(CatalogOption)
            .where(CatalogOption.catalog_type_id == selected_type.catalog_type_id)
            .order_by(CatalogOption.sort_order, CatalogOption.label)
        ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/catalogs.html",
        {
            "request": request,
            "current_user": current_user,
            "catalog_types": catalog_types,
            "selected_type": selected_type,
            "options": options,
            "msg": msg,
        },
    )


@router.post("/types/create")
def create_catalog_type(
    key: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    normalized_key = key.strip().lower().replace(" ", "_")
    existing = db.execute(
        select(CatalogType).where(CatalogType.key == normalized_key)
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse("/ui/admin/catalogs?msg=Error: La clave del catálogo ya existe.", status_code=303)

    catalog_type = CatalogType(key=normalized_key, name=name.strip(), description=description)
    db.add(catalog_type)
    db.commit()

    return RedirectResponse(
        f"/ui/admin/catalogs?selected_type_id={catalog_type.catalog_type_id}&msg=Catálogo creado exitosamente.",
        status_code=303,
    )


@router.post("/types/{catalog_type_id}/edit")
def edit_catalog_type(
    catalog_type_id: int,
    key: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    catalog_type = db.get(CatalogType, catalog_type_id)
    if not catalog_type:
        return RedirectResponse("/ui/admin/catalogs?msg=Error: Catálogo no encontrado.", status_code=303)

    normalized_key = key.strip().lower().replace(" ", "_")
    existing = db.execute(
        select(CatalogType).where(CatalogType.key == normalized_key, CatalogType.catalog_type_id != catalog_type_id)
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/admin/catalogs?selected_type_id={catalog_type_id}&msg=Error: La clave del catálogo ya existe.",
            status_code=303,
        )

    catalog_type.key = normalized_key
    catalog_type.name = name.strip()
    catalog_type.description = description
    catalog_type.is_active = is_active == "on"
    db.add(catalog_type)
    db.commit()

    return RedirectResponse(
        f"/ui/admin/catalogs?selected_type_id={catalog_type_id}&msg=Catálogo actualizado exitosamente.",
        status_code=303,
    )


@router.post("/options/create")
def create_catalog_option(
    catalog_type_id: int = Form(...),
    value: str = Form(...),
    label: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    catalog_type = db.get(CatalogType, catalog_type_id)
    if not catalog_type:
        return RedirectResponse("/ui/admin/catalogs?msg=Error: Catálogo no encontrado.", status_code=303)

    option = CatalogOption(
        catalog_type_id=catalog_type_id,
        value=value.strip(),
        label=label.strip(),
        sort_order=sort_order,
    )
    db.add(option)
    db.commit()

    return RedirectResponse(
        f"/ui/admin/catalogs?selected_type_id={catalog_type_id}&msg=Opción creada exitosamente.",
        status_code=303,
    )


@router.post("/options/{catalog_option_id}/edit")
def edit_catalog_option(
    catalog_option_id: int,
    value: str = Form(...),
    label: str = Form(...),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    option = db.get(CatalogOption, catalog_option_id)
    if not option:
        return RedirectResponse("/ui/admin/catalogs?msg=Error: Opción no encontrada.", status_code=303)

    option.value = value.strip()
    option.label = label.strip()
    option.sort_order = sort_order
    option.is_active = is_active == "on"
    db.add(option)
    db.commit()

    return RedirectResponse(
        f"/ui/admin/catalogs?selected_type_id={option.catalog_type_id}&msg=Opción actualizada exitosamente.",
        status_code=303,
    )
