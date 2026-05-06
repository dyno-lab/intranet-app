from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.report_template import ProposalReportTemplate, ReportTemplate, ReportTemplateVersion


DEFAULT_REPORT_TEMPLATE_CONFIGS: dict[str, dict[str, Any]] = {
    "bonafide": {
        "template_key": "bonafide_base_v1",
        "version_label": "Base v1 - formato actual",
        "header": {
            "image": "/static/img/bonafide-header-avp.png",
            "title": "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES",
            "subtitle": "CERTIFICACIÓN DE PARTICIPACIÓN DE RESIDENTES BONAFIDE",
            "organization": "CENTROS SOR ISOLINA FERRÉ",
            "program": "PROGRAMA FARO DE ESPERANZA",
            "description": "Autosuficiencia Económica y Social. Apoyo y Prevención",
        },
        "footer": {
            "text": "Los residentes bonafides antes mencionados participaron de los servicios/actividades desarrolladas por el Programa Faro de Esperanza de los Centros Sor Isolina Ferré, durante el periodo indicado.",
            "new_entry_note": "(*) Participante de nuevo ingreso.",
        },
    },
    "hoja_cotejo": {
        "template_key": "hoja_cotejo_base_v1",
        "version_label": "Base v1 - formato actual",
        "header": {
            "image": "/static/img/bonafide-header-avp.png",
            "line_1": "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES",
            "line_2": "PROGRAMA DE AUTOSUFICIENCIA ECONOMICA Y SOCIAL, APOYO Y PREVENCIÓN",
            "repeat_on_every_page": True,
        },
        "footer": {
            "image": "/static/img/no-duplicado-footer-faro.png",
        },
        "columns": [
            {"key": "population_label", "label": "PROGRAMA / CLASIFICACIÓN", "width": "22%", "align": "left"},
            {"key": "activity_text", "label": "ACTIVIDADES", "width": "38%", "align": "left"},
            {"key": "activities_count", "label": "REALIZADAS", "width": "9%", "align": "center"},
            {"key": "duplicados", "label": "DUPLICADOS", "width": "9%", "align": "center"},
            {"key": "unique_participants", "label": "ÚNICOS", "width": "9%", "align": "center"},
            {"key": "contact_hours", "label": "HORAS", "width": "13%", "align": "center", "format": "decimal_2"},
        ],
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries without losing default values from partial configs."""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def default_report_template_config(report_key: str) -> dict[str, Any]:
    return deepcopy(DEFAULT_REPORT_TEMPLATE_CONFIGS.get(report_key, {}))


def resolve_report_template_config(db: Session, proposal_id: int | None, report_key: str) -> dict[str, Any]:
    """Return the active template config for a proposal/report, falling back to the frozen base format.

    The fallback is intentionally stable: existing reports keep the current visual/column contract until an
    administrator explicitly assigns a newer version to a proposal.
    """
    fallback = default_report_template_config(report_key)
    if not proposal_id:
        return fallback

    assignment = db.execute(
        select(ProposalReportTemplate, ReportTemplateVersion, ReportTemplate)
        .join(
            ReportTemplateVersion,
            ReportTemplateVersion.report_template_version_id == ProposalReportTemplate.report_template_version_id,
        )
        .join(
            ReportTemplate,
            ReportTemplate.report_template_id == ReportTemplateVersion.report_template_id,
        )
        .where(
            ProposalReportTemplate.proposal_id == proposal_id,
            ProposalReportTemplate.report_key == report_key,
            ProposalReportTemplate.is_active == True,  # noqa: E712
            ReportTemplateVersion.is_active == True,  # noqa: E712
            ReportTemplate.is_active == True,  # noqa: E712
        )
        .order_by(ProposalReportTemplate.proposal_report_template_id.desc())
    ).first()

    if not assignment:
        return fallback

    _, version, template = assignment
    try:
        config = json.loads(version.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    merged = deep_merge(fallback, config)
    merged.setdefault("template_key", template.report_key)
    merged["template_name"] = template.name
    merged["template_version_id"] = version.report_template_version_id
    merged["version_label"] = version.version_label
    return merged


def report_template_columns(config: dict[str, Any]) -> list[dict[str, Any]]:
    columns = config.get("columns")
    if isinstance(columns, list) and columns:
        return columns
    return default_report_template_config("hoja_cotejo").get("columns", [])
