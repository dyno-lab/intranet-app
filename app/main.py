from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.core.config import require_session_secret
from app.api.routes.institutional_reports import router as institutional_reports_router
from app.api.routes.portal import router as portal_router
from app.api.routes.platform_settings import router as platform_settings_router
from app.api.routes.residential_context import router as residential_context_router
from app.api.routes.ui import router as ui_router
from app.api.routes.admin import router as admin_router
from app.api.routes.catalogs import router as catalogs_router
from app.api.routes.consolidado_mensual_global import router as consolidado_mensual_global_router
from app.api.routes.plantilla_duplicado import router as plantilla_duplicado_router
from app.api.routes.hoja_cotejo_admin import router as hoja_cotejo_admin_router
from app.api.routes.school_grades import router as school_grades_router
from app.api.routes.school_dropout import router as school_dropout_router
from app.api.routes.pregnancy import router as pregnancy_router
from app.api.routes.reports import router as reports_router
from app.api.routes.automation_reports import router as automation_reports_router

# ✅ API routers (no rompen FASE 1 porque van bajo /api)
from app.api.routes.sessions import router as sessions_router
from app.api.routes.participants import router as participants_router
from app.api.routes.attendance import router as attendance_router
from app.api.routes.employees import router as employees_router
from app.api.routes.activity_codes import router as activity_codes_router
from app.db.schema import ensure_schema_updates
from app.core.platform_permissions import (
    ACCESS_INSTITUTIONAL_REPORTS,
    require_platform_permission,
)
from app.core.residential_scope import require_faro_access

# Importa modelos nuevos para registrar mappers/relationships
import app.models.residential  # noqa: F401
import app.models.vca_column  # noqa: F401
import app.models.vca_column_activity_code  # noqa: F401
import app.models.proposal_report_program_population  # noqa: F401
import app.models.proposal_report_program_population_activity_code  # noqa: F401
import app.models.person  # noqa: F401
import app.models.proposal_participant  # noqa: F401
import app.models.proposal_activity_code  # noqa: F401
import app.models.activity_productivity_goal  # noqa: F401
import app.models.report_template  # noqa: F401
import app.models.participant_profile_field  # noqa: F401
import app.models.participant_profile_field_value  # noqa: F401
import app.models.platform_permission  # noqa: F401
import app.models.platform_user_audit  # noqa: F401
import app.models.user_platform_permission  # noqa: F401
import app.models.user_residential  # noqa: F401

app = FastAPI(title="Intranet App")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Session middleware (LOGIN)
SESSION_SECRET = require_session_secret()

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=True,
)

# Routers
faro_dependencies = [Depends(require_faro_access)]
institutional_report_dependencies = [
    Depends(require_platform_permission(ACCESS_INSTITUTIONAL_REPORTS))
]

app.include_router(portal_router)             # /home
app.include_router(platform_settings_router)  # /platform/settings
app.include_router(
    institutional_reports_router,
    dependencies=institutional_report_dependencies,
)  # /reporteinstitucionales/...
app.include_router(auth_router)               # /login, /logout
app.include_router(residential_context_router)  # /ui/context/residential
app.include_router(ui_router, prefix="/ui", dependencies=faro_dependencies)   # /ui/...
app.include_router(admin_router, prefix="/ui/admin", dependencies=faro_dependencies)  # /ui/admin/...
app.include_router(catalogs_router, prefix="/ui/admin/catalogs", dependencies=faro_dependencies)  # /ui/admin/catalogs/...
app.include_router(consolidado_mensual_global_router, prefix="/ui/admin", dependencies=faro_dependencies)  # /ui/admin/consolidado-mensual-global/...
app.include_router(plantilla_duplicado_router, prefix="/ui/admin", dependencies=faro_dependencies)  # /ui/admin/plantilla-duplicado/...
app.include_router(hoja_cotejo_admin_router, prefix="/ui/admin", dependencies=faro_dependencies)  # /ui/admin/hoja-cotejo/...
app.include_router(school_grades_router, prefix="/ui/school-grades", dependencies=faro_dependencies)
app.include_router(school_dropout_router, prefix="/ui/school-dropout", dependencies=faro_dependencies)
app.include_router(pregnancy_router, prefix="/ui/pregnancy", dependencies=faro_dependencies)
app.include_router(reports_router, prefix="/ui/reports", dependencies=faro_dependencies)
app.include_router(automation_reports_router, prefix="/api/automation", tags=["automation"])

# ✅ API (para Postman / integraciones)
app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"], dependencies=faro_dependencies)
app.include_router(participants_router, prefix="/api/participants", tags=["participants"], dependencies=faro_dependencies)
app.include_router(attendance_router, prefix="/api/attendance", tags=["attendance"], dependencies=faro_dependencies)
app.include_router(employees_router, prefix="/api/employees", tags=["employees"], dependencies=faro_dependencies)
app.include_router(activity_codes_router, prefix="/api/activity-codes", tags=["activity-codes"], dependencies=faro_dependencies)


@app.on_event("startup")
def startup_schema_updates():
    ensure_schema_updates()


@app.get("/")
def root():
    return RedirectResponse(url="/home")
