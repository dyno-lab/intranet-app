"""Proposal-period participant goals and AMP codes for the complete report.

Use the proposal's business identifiers and the residential RQ, never database
IDs or fuzzy residential names. These goals do not depend on the report month
and do not write to the existing activity-goal or attendance tables.
"""
from __future__ import annotations


PROPOSAL_TARGETS = {
    ("006", "2025-000094-C"): {
        "by_rq": {
            "RQ1014": 192,  # Arístides Chavier
            "RQ1009": 110,  # Pedro J. Rosaly
            "RQ1001": 100,  # Juan Ponce de León
            "RQ1017": 155,  # Ernesto Ramos Antonini
            "RQ1016": 155,  # Rafael López Nussa
            "RQ5022": 105,  # La Ceiba
            "RQ5148": 90,   # Leónardo Santiago
            "RQ3089": 90,   # Villa del Parque
            "RQ5045": 75,   # Brisas del Mar
            "RQ3090": 80,   # Bella Vista
            "RQ5266": 58,   # Valles de Guayama
            "RQ5184": 65,   # Jardines de Guamani
            "RQ5314": 80,   # Fernando Calimano
            "RQ5048": 100,  # San Antonio Carioca
            "RQ4010": 72,   # El Carmen
            "RQ4009": 72,   # Manuel Hernandez Rosa
            "RQ4011": 75,   # Rafael Hernandez
            "RQ4001": 108,  # Columbus Landing
        },
        "amp_by_rq": {
            "RQ1014": "RQ005009017P",
            "RQ1009": "RQ005009015P",
            "RQ1001": "RQ005009010P",
            "RQ1017": "RQ005009020P",
            "RQ1016": "RQ005009019P",
            "RQ5022": "RQ005009022P",
            "RQ5148": "RQ005006022P",
            "RQ3089": "RQ005006021P",
            "RQ5045": "RQ005006029P",
            "RQ3090": "RQ005006028P",
            "RQ5266": "RQ005006020P",
            "RQ5184": "RQ005006019P",
            "RQ5314": "RQ005006016P",
            "RQ5048": "RQ005006018P",
            "RQ4010": "RQ005008015P",
            "RQ4009": "RQ005008014P",
            "RQ4011": "RQ005008016P",
            "RQ4001": "RQ005008007P",
        },
    },
}

# Both proposals explicitly share the same approved plan. Selecting both uses
# that plan once; it does not add their identical goals together.
PROPOSAL_TARGETS[("005", "2025-000094-B")] = PROPOSAL_TARGETS[("006", "2025-000094-C")]


def selected_extension(proposals):
    """Return the base and extension only when both are explicitly selected."""
    by_key = {(proposal.code.strip(), proposal.name.strip()): proposal for proposal in proposals}
    keys = (("005", "2025-000094-B"), ("006", "2025-000094-C"))
    return [by_key[key] for key in keys] if all(key in by_key for key in keys) else []


def configured_targets(proposals, residentials):
    """Resolve the approved plan shared by all selected proposals, if available."""
    proposals = list({proposal.proposal_id: proposal for proposal in proposals}.values())
    configs = [PROPOSAL_TARGETS.get((proposal.code.strip(), proposal.name.strip())) for proposal in proposals]
    # Only proposals explicitly linked to this same plan may share its goals.
    # An unconfigured proposal or another plan retains the manual-input path.
    if not configs or configs[0] is None or any(config is not configs[0] for config in configs):
        return {"targets": {}, "amps": {}}
    config = configs[0]
    residentials = list(residentials)
    return {
        "targets": {
            row.residential_id: config["by_rq"][str(row.rq_code or "").strip().upper()]
            for row in residentials
            if str(row.rq_code or "").strip().upper() in config["by_rq"]
        },
        "amps": {
            row.residential_id: config["amp_by_rq"][str(row.rq_code or "").strip().upper()]
            for row in residentials
            if str(row.rq_code or "").strip().upper() in config["amp_by_rq"]
        },
    }
