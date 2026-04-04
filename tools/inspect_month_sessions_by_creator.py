from datetime import date
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.proposal import Proposal
from app.models.user import User


def main():
    today = date.today()
    month_start = today.replace(day=1)

    db = SessionLocal()
    try:
        stmt = (
            select(
                ActivitySession.session_id,
                ActivitySession.session_date,
                ActivitySession.created_by_user_id,
                User.username,
                User.role,
                Proposal.code.label("proposal_code"),
                Proposal.name.label("proposal_name"),
                ActivityCode.code.label("activity_code"),
                ActivityCode.description.label("activity_description"),
                Employee.employee_code,
                Employee.full_name,
                ActivitySession.hours,
            )
            .outerjoin(User, User.user_id == ActivitySession.created_by_user_id)
            .outerjoin(Proposal, Proposal.proposal_id == ActivitySession.proposal_id)
            .outerjoin(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
            .outerjoin(Employee, Employee.employee_id == ActivitySession.employee_id)
            .where(
                ActivitySession.session_date >= month_start,
                ActivitySession.session_date <= today,
            )
            .order_by(
                ActivitySession.session_date,
                ActivitySession.created_by_user_id,
                ActivitySession.session_id,
            )
        )

        rows = db.execute(stmt).all()

        print("=== SESIONES DEL MES POR CREADOR ===")
        print(f"Periodo: {month_start.isoformat()} -> {today.isoformat()}")
        print(f"Total sesiones: {len(rows)}")
        print()

        if not rows:
            print("No hay sesiones en el mes actual.")
            return

        current_creator = None
        creator_count = 0
        for row in rows:
            creator_key = (row.created_by_user_id, row.username or "(sin usuario)")
            if creator_key != current_creator:
                if current_creator is not None:
                    print(f"  Total sesiones de este creador: {creator_count}")
                    print()
                current_creator = creator_key
                creator_count = 0
                print(
                    f"Creador: {row.username or '(sin usuario)'} "
                    f"(user_id={row.created_by_user_id}, role={row.role or 'N/A'})"
                )

            creator_count += 1
            proposal_text = f"{row.proposal_code or ''} {row.proposal_name or ''}".strip() or "Sin propuesta"
            activity_text = f"{row.activity_code or ''} {row.activity_description or ''}".strip() or "Sin actividad"
            employee_text = f"{row.employee_code or ''} {row.full_name or ''}".strip() or "Sin empleado"

            print(
                f"  session_id={row.session_id} | fecha={row.session_date} | "
                f"propuesta={proposal_text} | actividad={activity_text} | "
                f"empleado={employee_text} | horas={row.hours}"
            )

        if current_creator is not None:
            print(f"  Total sesiones de este creador: {creator_count}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
