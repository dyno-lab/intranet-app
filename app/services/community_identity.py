"""Narrow cross-module identity matching with explicit human review.

The authorized source record is the caller's responsibility. Candidate results are
basic identity only, without residential, program, contact, profile, or fiscal data.
Services flush only; the caller owns commit/rollback. Disabled mode performs no SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.community import CPParticipant
from app.models.community_identity import CPIdentityReview
from app.models.participant import Participant

SIMILARITY_THRESHOLD = 0.80


@dataclass(frozen=True)
class BasicIdentity:
    participant_id: int
    expediente_num: str
    nombre: str
    apellido_paterno: str
    apellido_materno: str | None
    fecha_nacimiento: date | None


def normalize_identity_name(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return " ".join("".join(character for character in normalized if not unicodedata.combining(character)).casefold().split())


def identity_similarity(source: BasicIdentity, candidate: BasicIdentity) -> float | None:
    if source.fecha_nacimiento is None or source.fecha_nacimiento != candidate.fecha_nacimiento:
        return None
    scores = []
    for field in ("nombre", "apellido_paterno", "apellido_materno"):
        first = normalize_identity_name(getattr(source, field))
        second = normalize_identity_name(getattr(candidate, field))
        if field == "apellido_materno" and (not first or not second):
            continue
        if not first or not second:
            return None
        # Score only proposes a comparison; it never establishes a link.
        score = SequenceMatcher(None, first, second, autojunk=False).ratio()
        if score < SIMILARITY_THRESHOLD:
            return None
        scores.append(score)
    return sum(scores) / len(scores) if scores else None


def _source_column(source_module: str):
    if source_module == "community":
        return CPIdentityReview.cp_participant_id
    if source_module == "faro":
        return CPIdentityReview.faro_participant_id
    raise ValueError("Módulo de identidad inválido.")


def _model(source_module: str):
    _source_column(source_module)
    return CPParticipant if source_module == "community" else Participant


def _identity_query(model):
    return select(model.participant_id, model.expediente_num, model.nombre, model.apellido_paterno,
                  model.apellido_materno, model.fecha_nacimiento)


def _basic_identity(db: Session, source_module: str, participant_id: int) -> BasicIdentity | None:
    model = _model(source_module)
    row = db.execute(_identity_query(model).where(model.participant_id == participant_id)).one_or_none()
    return BasicIdentity(*row) if row else None


def has_identity_link(db: Session, source_module: str, participant_id: int) -> bool:
    if not settings.COMMUNITY_ENABLED:
        return False
    return db.scalar(select(CPIdentityReview.id).where(
        _source_column(source_module) == participant_id, CPIdentityReview.is_same_person == True,  # noqa: E712
    ).limit(1)) is not None


def has_identity_review(db: Session, source_module: str, participant_id: int) -> bool:
    if not settings.COMMUNITY_ENABLED:
        return False
    return db.scalar(select(CPIdentityReview.id).where(_source_column(source_module) == participant_id).limit(1)) is not None


def find_identity_candidates(db: Session, source_module: str, participant_id: int) -> list[BasicIdentity]:
    if not settings.COMMUNITY_ENABLED:
        return []
    source = _basic_identity(db, source_module, participant_id)
    if source is None or source.fecha_nacimiento is None or has_identity_link(db, source_module, participant_id):
        return []
    other_module = "faro" if source_module == "community" else "community"
    other_model = _model(other_module)
    target_column = _source_column(other_module)
    # A rejected pair is not proposed again from the other side. A confirmed
    # identity is not offered for a second record without a separate correction flow.
    unavailable = select(target_column).where(or_(
        _source_column(source_module) == participant_id, CPIdentityReview.is_same_person == True,  # noqa: E712
    ))
    rows = db.execute(_identity_query(other_model).where(
        other_model.fecha_nacimiento == source.fecha_nacimiento,
        other_model.participant_id.not_in(unavailable),
    )).all()
    candidates = []
    for row in rows:
        candidate = BasicIdentity(*row)
        score = identity_similarity(source, candidate)
        if score is not None:
            candidates.append((score, candidate))
    candidates.sort(key=lambda item: (-item[0], item[1].participant_id))
    return [candidate for _, candidate in candidates[:20]]


def pending_identity_review(db: Session, source_module: str, participant_id: int) -> bool:
    return bool(find_identity_candidates(db, source_module, participant_id))


def identity_review_url(source_module: str, participant_id: int) -> str:
    _source_column(source_module)
    if source_module == "community":
        return f"/community/participants/{participant_id}/identity"
    return f"/ui/new-list/{participant_id}/community-identity"


def identity_record_url(source_module: str, participant_id: int) -> str:
    _source_column(source_module)
    if source_module == "community":
        return f"/community/participants/{participant_id}"
    return f"/ui/new-list/{participant_id}/expediente"


def confirm_identity_review(db: Session, *, source_module: str, participant_id: int,
                             candidate_id: int, is_same_person: bool, actor_user_id: int) -> CPIdentityReview:
    if not settings.COMMUNITY_ENABLED:
        raise ValueError("La revisión de coincidencias no está disponible.")
    _source_column(source_module)
    if not isinstance(is_same_person, bool):
        raise ValueError("Responda Sí o No para confirmar la revisión.")
    if isinstance(actor_user_id, bool) or not isinstance(actor_user_id, int) or actor_user_id <= 0:
        raise ValueError("Usuario de revisión inválido.")
    cp_id, faro_id = (participant_id, candidate_id) if source_module == "community" else (candidate_id, participant_id)
    if db.get_bind().dialect.name == "mssql":
        # Serialize opposite-direction confirmations and demographic edits. Always
        # acquire Community before Faro, irrespective of which module initiated it.
        for model, identity_id in ((CPParticipant, cp_id), (Participant, faro_id)):
            db.execute(select(model.participant_id).where(model.participant_id == identity_id)
                       .with_hint(model, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")).first()
    # Recompute on POST: IDs supplied by a client cannot bypass similarity checks,
    # rejected decisions, or a link that another employee has already confirmed.
    if candidate_id not in {candidate.participant_id for candidate in find_identity_candidates(db, source_module, participant_id)}:
        raise ValueError("La coincidencia ya fue revisada o no corresponde a los datos actuales. Recargue la página.")
    review = CPIdentityReview(cp_participant_id=cp_id, faro_participant_id=faro_id,
                              is_same_person=is_same_person, reviewed_from=source_module,
                              reviewed_by_user_id=actor_user_id)
    db.add(review)
    db.flush()
    return review
