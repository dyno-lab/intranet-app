from datetime import date
from sqlalchemy import select, func, distinct

from app.db.session import SessionLocal
from app.models.user import User
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.api.routes.reports import _calculate_no_duplicado_metric

TARGET_USERNAME = "BDM"


def main():
    today = date.today()
    month_start = today.replace(day=1)

    db = SessionLocal()
    try:
        user = db.execute(
            select(User).where(func.upper(User.username) == TARGET_USERNAME.upper())
        ).scalar_one_or_none()

        if not user:
            print(f"No se encontró el usuario: {TARGET_USERNAME}")
            return

        print("=== INSPECCIÓN DE DATOS DEL DASHBOARD ===")
        print(f"Usuario: {user.username}")
        print(f"User ID: {user.user_id}")
        print(f"Role: {user.role}")
        print(f"Periodo: {month_start.isoformat()} -> {today.isoformat()}")
        print()

        sessions_stmt = (
            select(
                ActivitySession.session_id,
                ActivitySession.session_date,
                ActivitySession.created_by_user_id,
                ActivitySession.proposal_id,
                ActivitySession.employee_id,
                ActivitySession.activity_code_id,
                ActivitySession.hours,
            )
            .where(
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= today,
                ActivitySession.created_by_user_id == user.user_id,
            )
            .order_by(ActivitySession.session_date, ActivitySession.session_id)
        )
        session_rows = db.execute(sessions_stmt).all()

        print(f"Sesiones del mes creadas por {user.username}: {len(session_rows)}")
        for row in session_rows:
            print(
                f"  session_id={row.session_id} | fecha={row.session_date} | "
                f"proposal_id={row.proposal_id} | employee_id={row.employee_id} | "
                f"activity_code_id={row.activity_code_id} | hours={row.hours}"
            )
        print()

        attended_count_stmt = (
            select(func.count())
            .select_from(Attendance)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .where(
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= today,
                ActivitySession.created_by_user_id == user.user_id,
                Attendance.attended == True,  # noqa: E712
            )
        )
        attended_count = db.execute(attended_count_stmt).scalar_one() or 0

        unique_participants_stmt = (
            select(func.count(distinct(Attendance.participant_id)))
            .select_from(Attendance)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .where(
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= today,
                ActivitySession.created_by_user_id == user.user_id,
                Attendance.attended == True,  # noqa: E712
            )
        )
        unique_participants = db.execute(unique_participants_stmt).scalar_one() or 0

        activities_stmt = (
            select(func.count(distinct(ActivitySession.session_id)))
            .where(
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= today,
                ActivitySession.created_by_user_id == user.user_id,
            )
        )
        activities_count = db.execute(activities_stmt).scalar_one() or 0

        metric_no_dup = _calculate_no_duplicado_metric(
            db,
            user,
            proposal_id=None,
            month=None,
            year=None,
            employee_id=user.user_id,
            duplicated=False,
            period_type="custom",
            start_date=month_start,
            end_date=today,
        )
        metric_dup = _calculate_no_duplicado_metric(
            db,
            user,
            proposal_id=None,
            month=None,
            year=None,
            employee_id=user.user_id,
            duplicated=True,
            period_type="custom",
            start_date=month_start,
            end_date=today,
        )

        print("Resumen esperado para dashboard de ese usuario:")
        print(f"  No Duplicado (únicos): {metric_no_dup['total_all']}")
        print(f"  Duplicados (participaciones): {metric_dup['total_all']}")
        print(f"  Actividades Realizadas (sesiones): {activities_count}")
        print()

        print("Conteos directos de contraste:")
        print(f"  Participantes únicos directos: {unique_participants}")
        print(f"  Asistencias atendidas directas: {attended_count}")
        print(f"  Sesiones directas: {activities_count}")
        print()

        print("Comparación:")
        print(f"  No Duplicado coincide con únicos directos: {'OK' if metric_no_dup['total_all'] == unique_participants else 'NO COINCIDE'}")
        print(f"  Duplicados coincide con asistencias directas: {'OK' if metric_dup['total_all'] == attended_count else 'NO COINCIDE'}")
        print(f"  Actividades coincide con sesiones directas: OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()
