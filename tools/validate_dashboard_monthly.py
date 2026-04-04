from datetime import date
from sqlalchemy import select, func, distinct

from app.db.session import SessionLocal
from app.models.user import User
from app.models.activity_session import ActivitySession
from app.api.routes.reports import _calculate_no_duplicado_metric, _build_current_month_dashboard_cards


def validate_for_user(db, user: User):
    today = date.today()
    month_start = today.replace(day=1)
    role = (user.role or "").lower()
    scope_employee_id = 0 if role in ["admin", "supervisor"] else user.user_id

    dashboard = _build_current_month_dashboard_cards(db, user)
    dashboard_cards = {card["key"]: card["value"] for card in dashboard["dashboard_cards"]}

    no_duplicado_metric = _calculate_no_duplicado_metric(
        db,
        user,
        proposal_id=None,
        month=None,
        year=None,
        employee_id=scope_employee_id,
        duplicated=False,
        period_type="custom",
        start_date=month_start,
        end_date=today,
    )
    duplicados_metric = _calculate_no_duplicado_metric(
        db,
        user,
        proposal_id=None,
        month=None,
        year=None,
        employee_id=scope_employee_id,
        duplicated=True,
        period_type="custom",
        start_date=month_start,
        end_date=today,
    )

    session_stmt = select(func.count(distinct(ActivitySession.session_id))).where(
        ActivitySession.session_date >= month_start,
        ActivitySession.session_date <= today,
    )
    if role not in ["admin", "supervisor"]:
        session_stmt = session_stmt.where(ActivitySession.created_by_user_id == user.user_id)
    activities_count = db.execute(session_stmt).scalar_one() or 0

    return {
        "user_id": user.user_id,
        "username": getattr(user, "username", ""),
        "role": user.role,
        "scope": "global" if role in ["admin", "supervisor"] else "own",
        "period": {
            "start": month_start.isoformat(),
            "end": today.isoformat(),
        },
        "dashboard": {
            "no_duplicado": dashboard_cards.get("no-duplicado", 0),
            "duplicados": dashboard_cards.get("duplicados", 0),
            "actividades_realizadas": dashboard_cards.get("actividades-realizadas", 0),
        },
        "expected": {
            "no_duplicado": no_duplicado_metric["total_all"],
            "duplicados": duplicados_metric["total_all"],
            "actividades_realizadas": activities_count,
        },
        "matches": {
            "no_duplicado": dashboard_cards.get("no-duplicado", 0) == no_duplicado_metric["total_all"],
            "duplicados": dashboard_cards.get("duplicados", 0) == duplicados_metric["total_all"],
            "actividades_realizadas": dashboard_cards.get("actividades-realizadas", 0) == activities_count,
        },
    }


def main():
    db = SessionLocal()
    try:
        users = db.execute(select(User).order_by(User.user_id)).scalars().all()
        if not users:
            print("No hay usuarios para validar.")
            return

        sample_user = next((u for u in users if (u.role or "").lower() == "user"), users[0])
        sample_admin = next((u for u in users if (u.role or "").lower() in ["admin", "supervisor"]), users[0])

        print("=== VALIDACIÓN DASHBOARD MENSUAL ===")
        print()

        for label, target_user in [("USUARIO NORMAL", sample_user), ("ADMIN/SUPERVISOR", sample_admin)]:
            result = validate_for_user(db, target_user)
            print(f"[{label}]")
            print(f"Usuario: {result['username']} (id={result['user_id']}, role={result['role']})")
            print(f"Scope: {result['scope']}")
            print(f"Periodo: {result['period']['start']} -> {result['period']['end']}")
            print("Dashboard:")
            print(f"  No Duplicado: {result['dashboard']['no_duplicado']}")
            print(f"  Duplicados: {result['dashboard']['duplicados']}")
            print(f"  Actividades Realizadas: {result['dashboard']['actividades_realizadas']}")
            print("Esperado:")
            print(f"  No Duplicado: {result['expected']['no_duplicado']}")
            print(f"  Duplicados: {result['expected']['duplicados']}")
            print(f"  Actividades Realizadas: {result['expected']['actividades_realizadas']}")
            print("Coincidencias:")
            print(f"  No Duplicado: {'OK' if result['matches']['no_duplicado'] else 'NO COINCIDE'}")
            print(f"  Duplicados: {'OK' if result['matches']['duplicados'] else 'NO COINCIDE'}")
            print(f"  Actividades Realizadas: {'OK' if result['matches']['actividades_realizadas'] else 'NO COINCIDE'}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
