"""Allowlisted, aggregate-only FaroGPT views of the operational reports.

The report builders remain the source of truth. Never return their complete
contexts: VCA, for example, also contains identifiable participant rows.
"""
from __future__ import annotations

from fastapi import HTTPException


REPORTS = {
    "no_duplicado": ("No Duplicado", "no-duplicado"),
    "duplicado": ("Duplicados", "duplicado"),
    "adm": ("Informe Administrativo", "adm"),
    "vca": ("VCA", "vca"),
    "cotejo": ("Hoja de Cotejo", "hoja-cotejo"),
    "programs": ("Informe por Programa", "por-programa"),
    "productivity": ("Productividad", "productividad"),
}

PRIMARY = {"no_duplicado": "total", "duplicado": "total", "adm": "services", "vca": "served",
           "cotejo": "activities", "programs": "total", "productivity": "executed"}

METRIC_ALIASES = {
    "total": ["total"],
    "f": ["femenino", "femeninas", "mujeres"],
    "m": ["masculino", "masculinos", "hombres"],
    "services": ["servicios", "actividades"],
    "duplicates": ["duplicados", "participaciones"],
    "people": ["personas únicas", "personas unicas", "no duplicados", "personas atendidas"],
    "profile_total": ["personas con edad válida", "personas con edad valida", "perfil sociodemográfico"],
    "vca": ["vca"],
    "registered": ["registrados", "inscritos"],
    "served": ["atendidos", "participantes atendidos"],
    "unknown_age": ["sin edad", "edad sin informar"],
    "unknown_gender": ["sin género", "sin genero", "género sin informar"],
    "activities": ["actividades", "sesiones"],
    "hours": ["horas", "horas de contacto"],
    "evaluated": ["actividades evaluadas", "metas evaluadas"],
    "executed": ["actividades realizadas", "actividades ejecutadas", "realizadas en el mes"],
    "compliant": ["cumplen", "cumplidas"],
    "noncompliant": ["no cumplen", "no cumplidas", "incumplidas"],
    "period_executed": ["acumulado", "actividades acumuladas"],
    "period_goal": ["meta del período", "meta del periodo", "meta período", "meta periodo"],
    "progress": ["avance", "porcentaje de avance", "porcentaje de cumplimiento"],
}

AGE_NOTE = (
    "El reporte calcula la edad a la fecha actual y excluye del desglose por edad "
    "a quienes no tienen fecha de nacimiento válida."
)


def _metric(key, label, value, definition, unit=None):
    result = {"key": key, "label": label, "value": value, "definition": definition,
              "aliases": METRIC_ALIASES.get(key, [])}
    if unit:
        result["unit"] = unit
    return result


def _table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": rows}


def _age_table(rows, title="Por edad y género"):
    return _table(title, ["Edad", "Femenino", "Masculino", "Total"], [
        [row["label"], row["f"], row["m"], row["total"]] for row in rows
    ])


def _no_duplicado(context, duplicated):
    definition = ("Participaciones confirmadas incluidas en los rangos de edad del reporte."
                  if duplicated else
                  "Participantes únicos con asistencia confirmada incluidos en los rangos de edad del reporte.")
    return {
        "metrics": [
            _metric("total", "Duplicados" if duplicated else "No duplicados", context["total_all"], definition),
            _metric("f", "Femenino", context["total_f"], definition + " Género femenino."),
            _metric("m", "Masculino", context["total_m"], definition + " Género masculino."),
        ],
        "tables": [_age_table(context["rows"])],
        "note": AGE_NOTE + " El total puede incluir género sin informar, fuera de las columnas femenino y masculino.",
    }


def _adm(context):
    rows = context["rows"]
    profile = context["sociodemographic_total"]
    return {
        "metrics": [
            _metric("services", "Servicios", sum(row["services_count"] for row in rows),
                    "Sesiones de actividades con clasificación administrativa."),
            _metric("duplicates", "Duplicados", sum(row["duplicados"] for row in rows),
                    "Asistencias confirmadas de las actividades clasificadas, incluidas las asistencias legadas."),
            _metric("people", "Personas únicas con perfil ADM", context["family_total"],
                    "Personas únicas con expediente atendidas en sesiones administrativas; incluye edades sin informar."),
            _metric("profile_total", "Personas con edad válida", profile["total"],
                    "Personas únicas incluidas en el desglose sociodemográfico por edad."),
            _metric("f", "Femenino", profile["f"], "Personas con edad válida y género femenino."),
            _metric("m", "Masculino", profile["m"], "Personas con edad válida y género masculino."),
            _metric("vca", "VCA con edad válida", profile["vca"],
                    "Personas VCA incluidas en el desglose sociodemográfico por edad."),
        ],
        "tables": [
            _table("Por tipo de servicio", ["Servicio", "Servicios", "Duplicados", "No duplicados"], [
                [row["service_type_name"], row["services_count"], row["duplicados"], row["no_duplicados"]]
                for row in rows
            ]),
            _table("Perfil sociodemográfico", ["Edad", "Femenino", "Masculino", "Total", "Porcentaje", "VCA"], [
                [row["label"], row["f"], row["m"], row["total"], row["percent"], row["vca"]]
                for row in context["sociodemographic_rows"]
            ]),
            _table("Composición familiar de las personas atendidas", ["Composición familiar", "Personas"], [
                [row["label"], row["count"]] for row in context["family_rows"]
            ]),
        ],
        "note": (AGE_NOTE + " Los no duplicados de distintos servicios no se suman: una persona puede recibir "
                 "varios servicios. La composición familiar cuenta personas, no hogares."),
    }


def _vca(context):
    summary = context["vca_summary"]
    total = summary["total"]
    columns = context["columns"]
    return {
        "metrics": [
            _metric("registered", "VCA registrados", total["registered"],
                    "Personas VCA inscritas y activas al cierre del mes, tengan o no asistencia."),
            _metric("served", "VCA atendidos", total["served"],
                    "Participantes VCA únicos atendidos en los servicios configurados durante el mes."),
            _metric("f", "Femenino", total["f"], "Participantes VCA atendidos de género femenino."),
            _metric("m", "Masculino", total["m"], "Participantes VCA atendidos de género masculino."),
            _metric("unknown_age", "Edad sin informar", total["unknown_age"],
                    "Participantes VCA atendidos sin edad válida."),
            _metric("unknown_gender", "Género sin informar", total["unknown_gender"],
                    "Participantes VCA atendidos sin género femenino o masculino informado."),
        ],
        "tables": [
            _table("VCA por residencial", ["Residencial", "Registrados", "Atendidos", "Femenino", "Masculino"], [
                [row["residential_name"], row["registered"], row["served"], row["f"], row["m"]]
                for row in summary["rows"]
            ]),
            _table("VCA por servicio", ["Servicio", "Participaciones"], [
                [column.name, total["services"].get(column.vca_column_id, 0)] for column in columns
            ]),
            _table("VCA por edad y género", ["Edad", "Femenino", "Masculino"], [
                [band[2], age["f"], age["m"]]
                for band, age in zip(summary["age_bands"], total["ages"])
            ]),
        ],
        "note": ("Registrados corresponde al cierre del mes; atendidos corresponde a las asistencias del mes. "
                 "Una persona atendida en varios residenciales cuenta una sola vez en el total global; "
                 "los subtotales residenciales pueden sumar más. Las edades se calculan a la fecha actual."),
    }


def _cotejo(context):
    by_activity = {}
    detail = []
    hours = []
    for block in context["program_blocks"]:
        name = block.get("program_display_name") or getattr(block["program"], "name", "Programa")
        hours.append([name, block["program_contact_hours"]])
        for population in block["population_blocks"]:
            for row in population["rows"]:
                by_activity.setdefault(row["activity_code_id"], row)
                detail.append([name, population["population_label"], row["activity_code"],
                               row.get("activity_description", ""), row["activities_count"],
                               row["duplicados"], row["unique_participants"], row["contact_hours"]])
    return {
        "metrics": [
            _metric("activities", "Actividades", sum(row["activities_count"] for row in by_activity.values()),
                    "Sesiones de los códigos incluidos en la hoja, contadas una vez aunque el código aparezca en varios programas."),
            _metric("duplicates", "Duplicados", sum(row["duplicados"] for row in by_activity.values()),
                    "Participaciones confirmadas de las actividades incluidas, sin repetir códigos compartidos."),
            _metric("hours", "Horas de contacto", context["total_contact_hours"],
                    "Suma de horas de las sesiones; no son horas multiplicadas por participantes.", "horas"),
        ],
        "tables": [
            _table("Hoja de cotejo por actividad", ["Programa", "Población", "Código", "Actividad", "Actividades",
                   "Duplicados", "No duplicados de la actividad", "Horas"], detail),
            _table("Horas por programa", ["Programa", "Horas"], hours),
        ],
        "note": ("Los no duplicados por actividad no se suman para obtener personas únicas globales. "
                 "Un código puede aparecer en varios programas o poblaciones; los totales lo cuentan una sola vez."),
    }


def _programs(context):
    sections = context["program_sections"]
    multiple_proposals = len(context["selected_proposal_ids"]) > 1
    definition = ("Personas únicas con edad válida entre los programas y propuestas seleccionados."
                  if multiple_proposals else
                  "Suma de los no duplicados de cada programa; una persona puede contarse en varios programas.")
    return {
        "metrics": [
            _metric("total", "Total del informe por programa", context["overall_total_all"], definition),
            _metric("f", "Femenino", context["overall_total_f"], definition + " Género femenino."),
            _metric("m", "Masculino", context["overall_total_m"], definition + " Género masculino."),
        ],
        "tables": [
            _table("Por programa", ["Programa", "Femenino", "Masculino", "Total", "Códigos configurados"], [
                [section["program_display_name"], section["total_f"], section["total_m"],
                 section["total_all"], section["assigned_activity_count"]] for section in sections
            ]),
            *[_age_table(section["rows"], section["program_display_name"]) for section in sections],
        ],
        "note": AGE_NOTE + " " + definition,
    }


def _productivity(context):
    rows = context["summary_rows"]
    compliance_key = "period_compliance_label" if context["is_global"] else "compliance_label"
    progress = context["global_progress"]
    global_scope = context["is_global"]
    return {
        "metrics": [
            _metric("evaluated", "Actividades evaluadas", len(rows), "Códigos de actividad con metas activas evaluadas."),
            _metric("executed", "Actividades realizadas en el mes", sum(row["global_executed"] for row in rows),
                    "Sesiones del mes correspondientes a los códigos con metas activas."),
            _metric("compliant", "Cumplen período" if global_scope else "Cumplen", sum(row[compliance_key] == "Cumple" for row in rows),
                    "Actividades que cumplen según la evaluación del reporte: período para Global, mensual para residencial."),
            _metric("noncompliant", "No cumplen período" if global_scope else "No cumplen", sum(row[compliance_key] == "No cumple" for row in rows),
                    "Actividades que no cumplen según la evaluación del reporte."),
            _metric("period_executed", "Actividades acumuladas de la propuesta", sum(row["period_executed"] for row in rows),
                    "Acumulado de las propuestas seleccionadas, sin corte al mes consultado, conforme a Productividad."),
            _metric("period_goal", "Meta del período", sum(row["period_goal"] or 0 for row in rows),
                    "Suma de las metas de período configuradas para los códigos evaluados."),
            _metric("progress", "Avance del período" if global_scope else "Cumplimiento mensual", progress["percentage"],
                    "Porcentaje de avance acumulado del período en Global; porcentaje de actividades que cumplen para un residencial.", "%"),
        ],
        "tables": [
            _table("Productividad por actividad", ["Propuesta", "Código", "Actividad", "Realizadas en el mes", "Meta",
                   "Acumulado de la propuesta", "Meta período", "Cumplimiento"], [
                [row["proposal_name"], row["activity_code"], row["activity_description"], row["global_executed"],
                 row["goal_label"], row["period_executed"], row["period_goal"], row[compliance_key]] for row in rows
            ]),
            _table("Cumplimiento por residencial", ["Residencial", "Actividades evaluadas", "Cumplen", "No cumplen", "Porcentaje"], [
                [row["residential_name"], row["total_activities"], row["cumple"], row["no_cumple"], row["percentage"]]
                for row in context["residential_summary_rows"]
            ]),
        ],
        "note": ("Las realizadas en el mes respetan el mes solicitado. El acumulado de la propuesta y la meta del período "
                 "no se limitan a ese mes, tal como en el reporte de Productividad. "
                 + " ".join(context["warning_messages"])),
    }


def build(report, db, user, proposal_ids, month, year, residential_id):
    """Build a read-only monthly report projection for a validated FaroGPT scope."""
    # Lazy import avoids a route/service import cycle during application startup.
    from app.api.routes import reports

    if report not in REPORTS:
        raise HTTPException(status_code=422, detail="Reporte de FaroGPT no reconocido.")
    selected_ids = reports._proposal_ids(proposal_ids)
    if not selected_ids or not isinstance(month, int) or not 1 <= month <= 12 or not isinstance(year, int) or not 1 <= year <= 9999:
        raise HTTPException(status_code=422, detail="Selecciona propuesta, mes y año válidos para consultar el reporte.")
    if residential_id is not None and (not isinstance(residential_id, int) or residential_id <= 0):
        raise HTTPException(status_code=422, detail="Residencial no válido.")
    employee_id = -residential_id if residential_id is not None else 0
    scope = reports._resolve_reporting_scope(user, employee_id, db)
    selected = scope["selected_user"]
    if ((residential_id is None and not scope["is_global"])
            or (residential_id is not None and (not selected or selected.residential_id != residential_id))):
        raise HTTPException(status_code=403, detail="El contexto de acceso no permite consultar ese alcance.")

    args = (db, user, selected_ids, month, year, employee_id)
    if report in ("no_duplicado", "duplicado"):
        context = reports._calculate_no_duplicado_metric(*args, duplicated=report == "duplicado")
        content = _no_duplicado(context, report == "duplicado")
    else:
        builders = {
            "adm": (reports._build_adm_context, _adm),
            "vca": (reports._build_vca_context, _vca),
            "cotejo": (reports._build_hoja_cotejo_context, _cotejo),
            "programs": (reports._build_por_programa_context, _programs),
            "productivity": (reports._build_productivity_context, _productivity),
        }
        builder, project = builders[report]
        content = project(builder(*args))
    title, slug = REPORTS[report]
    return {"title": title, **content, "primary": PRIMARY[report], "source_path": "/ui/reports/" + slug}
