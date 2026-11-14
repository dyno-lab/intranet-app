"""Aggregate-only FaroGPT views of the existing monthly FARO reports.

The report builders own attendance, consolidation and historical residency rules.
Only explicitly selected aggregate fields cross this boundary: no participant,
file number, employee name or referral narrative is returned to the chat.
"""
from collections import Counter, defaultdict

from fastapi import HTTPException

from app.core.roles import ADMIN_ROLE, SUPERVISOR_ROLE


REPORTS = frozenset({"notes", "pregnancy", "dropout", "visits", "courses", "bonafide", "certification"})
LETTERS = ("A", "B", "C", "D", "F")


def _metric(key, label, value, definition, *, aliases=(), unit=None):
    metric = {"key": key, "label": label, "value": value, "definition": definition, "aliases": list(aliases)}
    if unit:
        metric["unit"] = unit
    return metric


def _table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": rows}


def _result(title, primary, metrics, tables, path, note):
    return {"title": title, "primary": primary, "metrics": metrics, "tables": tables,
            "source_path": "/ui/reports/" + path, "note": note}


def _notes(context):
    total = context["total_row"]
    metrics = [_metric("total", "Participantes en el resumen de notas", total["TOTAL"],
                       "Total del resumen por edades de 0 a 21 años, con o sin promedio registrado.",
                       aliases=("participantes del informe de notas", "total de notas"))]
    metrics += [_metric(letter, f"Promedio general {letter}", total[letter],
                        f"Participantes del resumen por edades cuyo promedio corresponde a {letter}.",
                        aliases=(f"promedio {letter}", f"notas {letter}", f"nota {letter}")) for letter in LETTERS]
    metrics += [
        _metric("special", "Educación especial", total["Especial"],
                "Participantes marcados en educación especial en el resumen por edades.", aliases=("educacion especial",)),
        _metric("kinder", "Kindergarten", total["K"],
                "Participantes de kindergarten en el resumen por edades.", aliases=("kinder", "kindergarten")),
    ]
    subject_rows = []
    for subject, key in (("Español", "spanish"), ("Inglés", "english"), ("Matemáticas", "math"), ("Ciencias", "science")):
        counts = context["subject_chart"][subject]
        subject_rows.append([subject, *(counts[letter] for letter in LETTERS)])
        metrics.append(_metric(f"{key}_total", f"Notas válidas de {subject}", sum(counts.values()),
                               f"Notas de {subject} clasificadas A, B, C, D o F en el gráfico por materia; no es un promedio numérico.",
                               aliases=(f"notas de {subject}", f"calificaciones de {subject}")))
        metrics += [_metric(f"{key}_{letter.lower()}", f"{subject}: nota {letter}", counts[letter],
                            f"Notas de {subject} clasificadas como {letter} en el gráfico por materia.",
                            aliases=(f"{letter} en {subject}", f"notas {letter} de {subject}", f"{subject} con {letter}"))
                    for letter in LETTERS]
    tables = [
        _table("Resumen por edad", ["Edad", *LETTERS, "Especial", "K", "Total"],
               [[row["age_label"], *(row[k] for k in (*LETTERS, "Especial", "K", "TOTAL"))] for row in context["rows"]]),
        _table("Calificaciones por materia", ["Materia", *LETTERS], subject_rows),
        _table("Promedios válidos por residencial", ["Residencial", *LETTERS, "Total"],
               [[row["residential_name"], *(row[k] for k in (*LETTERS, "total"))] for row in context["residential_chart_rows"]]),
    ]
    return _result("Notas escolares", "total", metrics, tables, "notas",
                   "El resumen por edades incluye de 0 a 21 años. Los gráficos por materia y residencial conservan el alcance del reporte. "
                   "Especial y K no son categorías adicionales al total. Las calificaciones se presentan por letra, no como promedio numérico.")


def _pregnancy(context):
    total = context["total"]
    specs = [
        ("pregnancy_cases", "Casos de embarazo registrados", "Suma de los indicadores femenino y masculino de embarazo registrados en el informe; no es el total de participantes en seguimiento.", ("embarazos", "casos de embarazo")),
        ("recruited", "Participantes en seguimiento de embarazo", "Participantes incluidos en el informe de embarazo, tengan o no embarazo registrado.", ("seguimiento de embarazo", "reclutados de embarazo")),
        ("participation", "Participantes en talleres", "Participantes con talleres reportados en el período.", ("participacion en talleres", "talleres de embarazo")),
        ("pregnant_f", "Embarazo registrado · femenino", "Participantes de género femenino con el indicador de embarazo registrado.", ("embarazadas", "embarazos femeninos")),
        ("pregnant_m", "Embarazo registrado · masculino", "Participantes de género masculino con el indicador de embarazo registrado, según el informe.", ("embarazos masculinos",)),
        ("f", "Participantes de género femenino", "Participantes de género femenino incluidos en el seguimiento, con o sin embarazo registrado.", ("mujeres en seguimiento",)),
        ("m", "Participantes de género masculino", "Participantes de género masculino incluidos en el seguimiento, con o sin embarazo registrado.", ("hombres en seguimiento",)),
        ("non_pregnant", "No embarazos en el indicador de prevención", "Participantes en talleres menos casos de embarazo registrados, con mínimo de cero, según la fórmula del reporte.", ("no embarazos", "sin embarazo")),
        ("prevention_pct", "Porcentaje de prevención", "No embarazos del indicador divididos entre participantes en talleres, según la fórmula del reporte.", ("porcentaje de prevencion", "prevencion de embarazo")),
    ]
    metrics = [_metric(key, label, total[key], definition, aliases=aliases,
                       unit="%" if key == "prevention_pct" else None) for key, label, definition, aliases in specs]
    columns = ["Residencial", "Participantes", "Femenino", "Masculino", "Talleres", "Embarazo F", "Embarazo M", "Casos", "No embarazos", "Prevención (%)"]
    keys = ("recruited", "f", "m", "participation", "pregnant_f", "pregnant_m", "pregnancy_cases", "non_pregnant", "prevention_pct")
    return _result("Seguimiento de embarazo", "pregnancy_cases", metrics,
                   [_table("Seguimiento por residencial", columns,
                           [[row["residential_name"], *(row[key] for key in keys)] for row in context["rows"]])],
                   "embarazo", "Se consulta el informe regular de Embarazo. Estar en seguimiento o participar en talleres no implica tener un embarazo registrado.")


def _dropout(context):
    total = context["total"]
    specs = [
        ("recruited", "Participantes en seguimiento escolar", "Participantes incluidos en el informe de deserción escolar; no es un conteo de desertores.", ("seguimiento escolar", "reclutados escolares")),
        ("f", "Participantes de género femenino", "Participantes de género femenino incluidos en el informe.", ("femenino", "mujeres")),
        ("m", "Participantes de género masculino", "Participantes de género masculino incluidos en el informe.", ("masculino", "hombres")),
        ("tutoring", "Participantes con tutorías", "Participantes con asistencia a tutorías marcada en el informe.", ("tutorias", "tutoria")),
        ("school", "Participantes con asistencia escolar", "Participantes con asistencia a la escuela marcada en el informe.", ("asistencia escolar", "asisten a la escuela")),
        ("tutoring_pct", "Porcentaje con tutorías", "Participantes con tutorías entre participantes en seguimiento escolar, por cien.", ("porcentaje de tutorias",)),
        ("school_pct", "Porcentaje de asistencia escolar", "Participantes con asistencia escolar entre participantes en seguimiento, por cien.", ("porcentaje de asistencia escolar",)),
    ]
    metrics = [_metric(key, label, total[key], definition, aliases=aliases,
                       unit="%" if key.endswith("_pct") else None) for key, label, definition, aliases in specs]
    for weeks in (10, 20, 30, 40):
        metrics.append(_metric(f"report_{weeks}", f"Informes de {weeks} semanas", total[f"report_{weeks}"],
                               f"Participantes con el informe de {weeks} semanas marcado.", aliases=(f"{weeks} semanas",)))
    for grade in context["grade_columns"]:
        metrics.append(_metric(f"grade_{grade.lower()}", f"Grado escolar {grade}", total["grades"][grade],
                               f"Participantes cuyo grado actual registrado en seguimiento es {grade}.",
                               aliases=(f"grado {grade}",)))
    keys = ("recruited", "f", "m", "tutoring", "school", "report_10", "report_20", "report_30", "report_40", "tutoring_pct", "school_pct")
    tables = [
        _table("Seguimiento por residencial", ["Residencial", "Participantes", "Femenino", "Masculino", "Tutorías", "Asistencia escolar", "10 semanas", "20 semanas", "30 semanas", "40 semanas", "Tutorías (%)", "Asistencia escolar (%)"],
               [[row["residential_name"], *(row[key] for key in keys)] for row in context["rows"]]),
        _table("Grados escolares", ["Grado", "Participantes"], [[grade, total["grades"][grade]] for grade in context["grade_columns"]]),
    ]
    return _result("Seguimiento de deserción escolar", "recruited", metrics, tables, "desercion-escolar",
                   "El total representa participantes en seguimiento escolar, no desertores. Se conservan los indicadores registrados en el reporte.")


def _visits(context):
    summary = context["summary"]
    counts = Counter(row["referral_type"] for row in context["referral_rows"])
    metrics = [
        _metric("visits", "Visitas", summary["visits"], "Sesiones de actividades configuradas para el reporte de Visitas.", aliases=("visitas",)),
        _metric("attendances", "Participaciones en visitas", summary["attendances"], "Asistencias confirmadas en las sesiones incluidas en Visitas.", aliases=("participaciones en visitas", "asistencias en visitas")),
        _metric("hours", "Horas de visitas", summary["hours"], "Suma de horas de las sesiones incluidas en Visitas, sin multiplicar por participantes.", aliases=("horas de visitas",), unit="horas"),
        _metric("referrals", "Referidos registrados", context["referral_count"], "Filas de referidos guardadas en los informes de Visitas del mes seleccionado.", aliases=("referidos", "total de referidos")),
    ]
    for value, key, label, aliases in (
        ("Interno", "referrals_internal", "Referidos internos", ("referidos internos", "referido interno")),
        ("Externo", "referrals_external", "Referidos externos", ("referidos externos", "referido externo")),
        ("Visita Agencia", "referrals_agency", "Visitas a agencias registradas", ("visitas a agencias", "visitas agencias", "visita a agencia")),
    ):
        metrics.append(_metric(key, label, counts[value], f"Filas guardadas con tipo «{value}» en el informe mensual de Visitas.", aliases=aliases))
    residentials = defaultdict(lambda: {"visits": 0, "attendances": 0, "hours": 0.0})
    for row in context["rows"]:
        bucket = residentials[row["residential_name"]]
        for key in ("visits", "attendances", "hours"):
            bucket[key] += row[key]
    return _result("Visitas y referidos", "visits", metrics, [
        _table("Visitas por residencial", ["Residencial", "Visitas", "Participaciones", "Horas"],
               [[name, row["visits"], row["attendances"], round(row["hours"], 2)] for name, row in sorted(residentials.items())]),
        _table("Referidos por tipo", ["Tipo", "Referidos"], [[kind, counts[kind]] for kind in ("Interno", "Externo", "Visita Agencia")]),
    ], "visitas", "Las visitas de actividades y las filas de referidos son medidas diferentes. Los referidos se guardan por propuesta, residencial y mes; no equivalen a personas únicas.")


def _courses(context):
    from app.services.participant_courses import COURSES

    counts = Counter(cell["course"] for row in context["rows"] for cell in row["cells"] if cell["attended"] and cell["course"])
    metrics = [
        _metric("total", "Participantes elegibles para cursos", context["total"], "Participantes únicos con asistencia confirmada a la actividad 2.b.5 en el período.", aliases=("participantes en cursos", "participacion en cursos")),
        _metric("pending", "Cursos pendientes de seleccionar", context["pending"], "Participantes del mes con asistencia a 2.b.5 y sin curso seleccionado.", aliases=("cursos pendientes", "pendientes de cursos")),
    ]
    for key, label in COURSES.items():
        metrics.append(_metric(key, f"Participantes en {label}", counts[key],
                               f"Participantes del mes con asistencia a 2.b.5 y selección de {label} registrada.", aliases=(label,)))
    return _result("Cursos", "total", metrics,
                   [_table("Cursos registrados", ["Curso", "Participantes"], [[label, counts[key]] for key, label in COURSES.items()])],
                   "cursos", "La elegibilidad procede de asistencias confirmadas a 2.b.5. Cada participante tiene una selección de curso por mes, compartida entre propuestas.")


def _bonafide(context):
    rows = context["rows"]
    metrics = [
        _metric("total", "Registros en Bonafide", len(rows), "Filas del Bonafide generado con los mismos filtros y sus reglas de consolidación.", aliases=("bonafide", "participantes en bonafide")),
        _metric("f", "Registros de género femenino", sum(bool(row["f"]) for row in rows), "Filas del Bonafide con marca de género femenino.", aliases=("femenino", "mujeres")),
        _metric("m", "Registros de género masculino", sum(bool(row["m"]) for row in rows), "Filas del Bonafide con marca de género masculino.", aliases=("masculino", "hombres")),
    ]
    return _result("Hoja Bonafide", "total", metrics, [], "bonafide",
                   "Se presentan conteos de las filas del Bonafide. Los nombres, expedientes y direcciones permanecen en el reporte de origen.")


def _certification(context):
    totals = context["totals"]
    metrics = [
        _metric("people", "Personas únicas certificadas", context["people_count"], "Participantes únicos con asistencias confirmadas en la Certificación, sin duplicar por residencial.", aliases=("personas certificadas", "participantes certificados")),
        _metric("total", "Participaciones certificadas", totals["total"], "Asistencias confirmadas incluidas en la Certificación, clasificadas o pendientes de clasificación.", aliases=("participaciones certificadas", "total de certificacion")),
    ]
    metrics += [_metric(program, f"Participaciones en {program}", totals[program],
                        f"Asistencias confirmadas clasificadas en {program} según la configuración de cada propuesta.",
                        aliases=(program,)) for program in ("1A", "2B", "3C", "4D")]
    metrics += [
        _metric("vca", "Registros VCA en Certificación", totals["vca"], "Filas persona-residencial marcadas VCA; un traslado puede generar más de una fila por persona.", aliases=("vca",)),
        _metric("unclassified", "Participaciones sin clasificación única", totals["unclassified"], "Asistencias sin programa configurado o con más de un programa asignado.", aliases=("sin clasificacion", "no clasificadas")),
    ]
    keys = ("1A", "2B", "3C", "4D", "total", "vca", "unclassified")
    return _result("Certificación", "people", metrics,
                   [_table("Certificación por residencial", ["Residencial", "1A", "2B", "3C", "4D", "Participaciones", "VCA", "Sin clasificación única"],
                           [[section["residential_name"], *(section["totals"][key] for key in keys)] for section in context["sections"]])],
                   "certificacion", "Cada residencial conserva las participaciones de su período histórico. El total de personas únicas no suma duplicados entre residenciales.")


def build(report, db, user, proposal_ids, month, year, residential_id):
    """Return an explicitly allowlisted, monthly report view for FaroGPT."""
    if getattr(user, "role", None) not in {ADMIN_ROLE, SUPERVISOR_ROLE}:
        raise HTTPException(403, "FaroGPT está disponible para administradores y supervisores.")
    if report not in REPORTS:
        raise HTTPException(422, "Reporte de FaroGPT no reconocido.")
    if (type(month) is not int or not 1 <= month <= 12 or type(year) is not int or not 2000 <= year <= 2100
            or not isinstance(proposal_ids, (list, tuple)) or not proposal_ids
            or any(type(value) is not int or value <= 0 for value in proposal_ids)
            or (residential_id is not None and (type(residential_id) is not int or residential_id <= 0))):
        raise HTTPException(422, "Selecciona propuestas, residencial y período válidos.")
    selected = list(dict.fromkeys(proposal_ids))
    employee_id = 0 if residential_id is None else -residential_id
    from app.api.routes import reports
    from app.helpers.report_context import resolve_reporting_scope

    # Reading a report must never flush unrelated pending changes in the session.
    with db.no_autoflush:
        scope = resolve_reporting_scope(user, employee_id, db)
        if not scope["is_global"] and not scope["selected_residential"]:
            raise HTTPException(403, "El residencial seleccionado no está disponible para esta consulta.")
        if report == "courses":
            from app.services.participant_courses import build_course_report
            context = build_course_report(db, user, proposal_ids=selected, month=month, year=year, employee_id=employee_id)
        elif report == "certification":
            from app.services.certification_report import build_certification_report
            context = build_certification_report(db, user, selected_proposals=selected, month=month, year=year, employee_id=employee_id)
        else:
            builders = {"notes": reports._build_notes_context, "pregnancy": reports._build_pregnancy_summary_context,
                        "dropout": reports._build_school_dropout_summary_context, "visits": reports._build_visits_context,
                        "bonafide": reports._build_bonafide_context}
            context = builders[report](db, user, selected, month, year, employee_id)
    return {"notes": _notes, "pregnancy": _pregnancy, "dropout": _dropout, "visits": _visits,
            "courses": _courses, "bonafide": _bonafide, "certification": _certification}[report](context)
