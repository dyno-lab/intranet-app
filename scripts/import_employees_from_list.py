from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.employee import Employee

# ============================================================
# LISTA DE EMPLEADOS
# ============================================================
RAW = """
CSW-Trabajador Social,
SF-Facilitador de Servicios,
ETK-6- Tutor,
ET7-12- Tutor,
HWA-Instructor de Bienestar y Salud,
VEP-Promotor Vocacional y Educativo,
LCSW- Trabajador Social Clínico con Licencia,
AP - Personal Administrativo,
SA  - Seniors Advocate
"""


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalize_spaces(text: str) -> str:
    return " ".join(text.strip().split())


def parse_items(raw: str) -> list[tuple[str, str]]:
    """
    Convierte el texto RAW en lista de tuplas:
    (employee_code, full_name)

    Maneja casos como:
    - ETK-6- Tutor  -> code="ETK-6", name="Tutor"
    - AP - Personal Administrativo
    """

    items: list[tuple[str, str]] = []

    parts = [p.strip() for p in raw.strip().split(",") if p.strip()]

    for p in parts:
        p = normalize_spaces(p)

        segments = [normalize_spaces(x) for x in p.split("-") if normalize_spaces(x)]

        if len(segments) < 2:
            code = segments[0] if segments else p
            name = code
        elif len(segments) == 2:
            code, name = segments[0], segments[1]
        else:
            code = "-".join(segments[:-1])
            name = segments[-1]

        code = normalize_spaces(code)
        name = normalize_spaces(name)

        if not code:
            continue

        if not name:
            name = code

        items.append((code, name))

    # Eliminar duplicados por código
    dedup: dict[str, str] = {}
    for code, name in items:
        dedup[code] = name

    return [(c, dedup[c]) for c in sorted(dedup.keys())]


# ============================================================
# PROCESO DE INSERCIÓN
# ============================================================

def main():
    rows = parse_items(RAW)

    db: Session = SessionLocal()

    created = 0
    updated = 0
    skipped = 0

    for code, name in rows:

        existing = db.execute(
            select(Employee).where(Employee.employee_code == code)
        ).scalar_one_or_none()

        if existing:
            # Si ya existe, actualizar nombre si cambió
            if existing.full_name != name or existing.is_active is False:
                existing.full_name = name
                existing.is_active = True
                updated += 1
            else:
                skipped += 1
            continue

        emp = Employee(
            employee_code=code,
            full_name=name,
            is_active=True
        )

        db.add(emp)
        created += 1

    db.commit()
    db.close()

    print("====================================")
    print("IMPORTACIÓN DE EMPLEADOS COMPLETADA")
    print("====================================")
    print(f"Total procesados: {len(rows)}")
    print(f"Creados: {created}")
    print(f"Actualizados: {updated}")
    print(f"Omitidos: {skipped}")
    print("====================================")


if __name__ == "__main__":
    main()