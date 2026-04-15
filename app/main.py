from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.ui import router as ui_router
from app.api.routes.admin import router as admin_router
from app.api.routes.catalogs import router as catalogs_router
from app.api.routes.school_grades import router as school_grades_router
from app.api.routes.school_dropout import router as school_dropout_router
from app.api.routes.pregnancy import router as pregnancy_router
from app.api.routes.reports import router as reports_router

# ✅ API routers (no rompen FASE 1 porque van bajo /api)
from app.api.routes.sessions import router as sessions_router
from app.api.routes.participants import router as participants_router
from app.api.routes.attendance import router as attendance_router
from app.api.routes.employees import router as employees_router
from app.api.routes.activity_codes import router as activity_codes_router
from app.db.schema import ensure_schema_updates

# Importa modelos nuevos para registrar mappers/relationships
import app.models.residential  # noqa: F401
import app.models.vca_column  # noqa: F401
import app.models.vca_column_activity_code  # noqa: F401
import app.models.proposal_report_program_population  # noqa: F401
import app.models.proposal_report_program_population_activity_code  # noqa: F401
import app.models.person  # noqa: F401
import app.models.proposal_participant  # noqa: F401
import app.models.activity_productivity_goal  # noqa: F401

app = FastAPI(title="Intranet App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Session middleware (LOGIN)
SESSION_SECRET = os.environ.get("SESSION_SECRET", "CAMBIA_ESTA_CLAVE_SUPER_SECRETA")

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
)

# Routers
app.include_router(auth_router)               # /login, /logout
app.include_router(ui_router, prefix="/ui")   # /ui/...
app.include_router(admin_router, prefix="/ui/admin")  # /ui/admin/...
app.include_router(catalogs_router, prefix="/ui/admin/catalogs")  # /ui/admin/catalogs/...
app.include_router(school_grades_router, prefix="/ui/school-grades")
app.include_router(school_dropout_router, prefix="/ui/school-dropout")
app.include_router(pregnancy_router, prefix="/ui/pregnancy")
app.include_router(reports_router, prefix="/ui/reports")

# ✅ API (para Postman / integraciones)
app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
app.include_router(participants_router, prefix="/api/participants", tags=["participants"])
app.include_router(attendance_router, prefix="/api/attendance", tags=["attendance"])
app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(activity_codes_router, prefix="/api/activity-codes", tags=["activity-codes"])


@app.on_event("startup")
def startup_schema_updates():
    ensure_schema_updates()


@app.get("/")
def root():
    # Mantiene tu UX: manda al login o al home según lo que ya tenías
    return RedirectResponse(url="/ui/home")
