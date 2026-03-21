from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.ui import router as ui_router
from app.api.routes.admin import router as admin_router

# ✅ API routers (no rompen FASE 1 porque van bajo /api)
from app.api.routes.sessions import router as sessions_router
from app.api.routes.participants import router as participants_router
from app.api.routes.attendance import router as attendance_router
from app.api.routes.employees import router as employees_router
from app.api.routes.activity_codes import router as activity_codes_router

app = FastAPI(title="Intranet App")

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

# ✅ API (para Postman / integraciones)
app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
app.include_router(participants_router, prefix="/api/participants", tags=["participants"])
app.include_router(attendance_router, prefix="/api/attendance", tags=["attendance"])
app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(activity_codes_router, prefix="/api/activity-codes", tags=["activity-codes"])


@app.get("/")
def root():
    # Mantiene tu UX: manda al login o al home según lo que ya tenías
    return RedirectResponse(url="/ui/home")