"""Narrow cross-module identity matching with explicit human review.

The authorized source record is the caller's responsibility. Candidate results are
basic identity only, without residential, program, contact, profile, or fiscal data.
Services flush only; the caller owns commit/rollback. Disabled mode performs no SQL.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from hashlib import sha256
import json
import unicodedata

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.community import CPParticipant, _utcnow
from app.models.community_identity import CPIdentityReview, CPIdentityReviewEvent
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
    if all(normalize_identity_name(getattr(source, field)) and
           normalize_identity_name(getattr(source, field)) == normalize_identity_name(getattr(candidate, field))
           for field in ('nombre', 'apellido_paterno')):
        return 1.0  # Exact match uses these three fields; maternal surname is reference only.
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


def lock_identity_operations(db):
    """Serialize confirmations in both directions until commit/rollback on SQL Server.

    A common transaction lock avoids opposite lock ordering when a registration
    inserts the source only after checking the other module's existing records.
    Unique filtered indexes remain the final one-to-one guard.
    """
    if db.get_bind().dialect.name == 'mssql':
        result = db.execute(text("""
            DECLARE @result INT;
            EXEC @result = sys.sp_getapplock @Resource=N'cp_identity_review',
                @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=10000;
            SELECT @result;
        """)).scalar_one()
        if result < 0:
            raise ValueError('Otro empleado está revisando una identidad. Intente guardar nuevamente.')


def has_identity_link(db: Session, source_module: str, participant_id: int) -> bool:
    if not settings.COMMUNITY_ENABLED:
        return False
    return db.scalar(select(CPIdentityReview.id).where(
        _source_column(source_module) == participant_id, CPIdentityReview.is_same_person == True,  # noqa: E712
    ).limit(1)) is not None


def linked_participant_ids(db: Session, source_module: str, participant_ids: list[int]) -> set[int]:
    """Read confirmed links for an already authorized roster page in one query."""
    if not settings.COMMUNITY_ENABLED or not participant_ids:
        return set()
    source = _source_column(source_module)
    return set(db.scalars(select(source).where(
        source.in_(participant_ids), CPIdentityReview.is_same_person == True,  # noqa: E712
    )))


def has_identity_review(db: Session, source_module: str, participant_id: int) -> bool:
    if not settings.COMMUNITY_ENABLED:
        return False
    return db.scalar(select(CPIdentityReview.id).where(_source_column(source_module) == participant_id).limit(1)) is not None


def linked_identity(db: Session, source_module: str, participant_id: int) -> BasicIdentity | None:
    if not settings.COMMUNITY_ENABLED:
        return None
    other = 'faro' if source_module == 'community' else 'community'
    target_id = db.scalar(select(_source_column(other)).where(_source_column(source_module) == participant_id,
                        CPIdentityReview.is_same_person == True))  # noqa: E712
    return _basic_identity(db, other, target_id) if target_id is not None else None


def comparison_fingerprint(cp: BasicIdentity, faro: BasicIdentity) -> str:
    values = [[person.participant_id, *(normalize_identity_name(getattr(person, field))
        for field in ('nombre', 'apellido_paterno', 'apellido_materno')), str(person.fecha_nacimiento)]
        for person in (cp, faro)]
    return sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def find_identity_candidates(db: Session, source_module: str, participant_id: int, *, conflicts_only=False) -> list[BasicIdentity]:
    if not settings.COMMUNITY_ENABLED:
        return []
    source = _basic_identity(db, source_module, participant_id)
    if source is None or source.fecha_nacimiento is None or has_identity_link(db, source_module, participant_id):
        return []
    other_module = "faro" if source_module == "community" else "community"
    other_model = _model(other_module)
    target_column = _source_column(other_module)
    # Confirmed identities remain exclusive. Rejected comparisons become pending
    # again only when the compared demographics change or a supervisor reopens them.
    unavailable = select(target_column).where(CPIdentityReview.is_same_person == True)  # noqa: E712
    reviews = {getattr(review, target_column.key): review for review in db.scalars(
        select(CPIdentityReview).where(_source_column(source_module) == participant_id))}
    rows = db.execute(_identity_query(other_model).where(
        other_model.fecha_nacimiento == source.fecha_nacimiento,
        other_model.participant_id.in_(unavailable) if conflicts_only else other_model.participant_id.not_in(unavailable),
    )).all()
    candidates = []
    for row in rows:
        candidate = BasicIdentity(*row)
        review = reviews.get(candidate.participant_id)
        cp, faro = (source, candidate) if source_module == 'community' else (candidate, source)
        if review and not review.needs_review and review.comparison_fingerprint == comparison_fingerprint(cp, faro):
            continue
        score = identity_similarity(source, candidate)
        if score is not None and (not conflicts_only or score == 1.0):
            candidates.append((score, candidate))
    candidates.sort(key=lambda item: (-item[0], item[1].participant_id))
    return [candidate for _, candidate in candidates[:20]]


def pending_identity_review(db: Session, source_module: str, participant_id: int) -> bool:
    return bool(find_identity_candidates(db, source_module, participant_id)
                or find_identity_candidates(db, source_module, participant_id, conflicts_only=True))


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
                             candidate_id: int, is_same_person: bool, actor_user_id: int,
                             expected_fingerprint: str | None = None, expected_revision: int | None = None) -> CPIdentityReview:
    if not settings.COMMUNITY_ENABLED:
        raise ValueError("La revisión de coincidencias no está disponible.")
    _source_column(source_module)
    if not isinstance(is_same_person, bool):
        raise ValueError("Responda Sí o No para confirmar la revisión.")
    if isinstance(actor_user_id, bool) or not isinstance(actor_user_id, int) or actor_user_id <= 0:
        raise ValueError("Usuario de revisión inválido.")
    cp_id, faro_id = (participant_id, candidate_id) if source_module == "community" else (candidate_id, participant_id)
    lock_identity_operations(db)
    if db.get_bind().dialect.name == "mssql":
        # Serialize opposite-direction confirmations and demographic edits. Always
        # acquire Community before Faro, irrespective of which module initiated it.
        for model, identity_id in ((CPParticipant, cp_id), (Participant, faro_id)):
            db.execute(select(model.participant_id).where(model.participant_id == identity_id)
                       .with_hint(model, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")).first()
    if expected_fingerprint is not None:
        cp, faro = _basic_identity(db, 'community', cp_id), _basic_identity(db, 'faro', faro_id)
        review = db.scalar(select(CPIdentityReview).where(CPIdentityReview.cp_participant_id == cp_id,
                                                         CPIdentityReview.faro_participant_id == faro_id))
        if (cp is None or faro is None or comparison_fingerprint(cp, faro) != expected_fingerprint
                or (review.revision if review else 0) != expected_revision):
            raise ValueError('Los datos o la decisión cambiaron. Recargue la comparación antes de confirmar.')
    # Recompute on POST: IDs supplied by a client cannot bypass similarity checks,
    # rejected decisions, or a link that another employee has already confirmed.
    if candidate_id not in {candidate.participant_id for candidate in find_identity_candidates(db, source_module, participant_id)}:
        raise ValueError("La coincidencia ya fue revisada o no corresponde a los datos actuales. Recargue la página.")
    return record_identity_decision(db, cp_id, faro_id, is_same_person, source_module, actor_user_id)


def _archive_legacy_review(db, review):
    if db.scalar(select(CPIdentityReviewEvent.id).where(CPIdentityReviewEvent.review_id == review.id).limit(1)) is None:
        db.add(CPIdentityReviewEvent(review_id=review.id, previous_decision=None,
            decision=None if review.needs_review else review.is_same_person,
            comparison_fingerprint=review.comparison_fingerprint, reviewed_from=review.reviewed_from,
            reviewed_by_user_id=review.reviewed_by_user_id, reviewed_at=review.reviewed_at,
            reason='Decisión registrada antes de incorporar el historial de cambios.'))


def record_identity_decision(db, cp_id, faro_id, decision, source_module, actor_user_id):
    """Caller must validate and lock the pair first. Never commits."""
    review = db.scalar(select(CPIdentityReview).where(CPIdentityReview.cp_participant_id == cp_id,
                                                     CPIdentityReview.faro_participant_id == faro_id))
    previous = None if review is None or review.needs_review else review.is_same_person
    fingerprint = comparison_fingerprint(_basic_identity(db, 'community', cp_id), _basic_identity(db, 'faro', faro_id))
    if review is None:
        review = CPIdentityReview(cp_participant_id=cp_id, faro_participant_id=faro_id, revision=1)
        db.add(review)
    else:
        _archive_legacy_review(db, review)
        review.revision += 1
    review.is_same_person = decision
    review.needs_review = False
    review.comparison_fingerprint = fingerprint
    review.reviewed_from = source_module
    review.reviewed_by_user_id = actor_user_id
    review.reviewed_at = _utcnow()
    db.flush()
    db.add(CPIdentityReviewEvent(review_id=review.id, previous_decision=previous, decision=decision,
        comparison_fingerprint=fingerprint, reviewed_from=source_module, reviewed_by_user_id=actor_user_id))
    db.flush()
    return review


def reopen_identity_review(db, source_module, participant_id, review_id, revision, actor_user_id, reason):
    reason = (reason or '').strip()
    if not reason or len(reason) > 500:
        raise ValueError('Indique el motivo de la corrección (hasta 500 caracteres).')
    lock_identity_operations(db)
    review = db.scalar(select(CPIdentityReview).where(CPIdentityReview.id == review_id,
        _source_column(source_module) == participant_id).with_hint(CPIdentityReview, 'WITH (UPDLOCK, HOLDLOCK)', dialect_name='mssql'))
    if review is None or review.revision != revision or review.needs_review:
        raise ValueError('La decisión cambió. Recargue la página antes de corregirla.')
    previous = review.is_same_person
    _archive_legacy_review(db, review)
    # The previous decision is recorded before releasing the one-to-one link.
    db.add(CPIdentityReviewEvent(review_id=review.id, previous_decision=previous, decision=None,
        comparison_fingerprint=review.comparison_fingerprint, reviewed_from=source_module,
        reviewed_by_user_id=actor_user_id, reason=reason))
    review.is_same_person = False
    review.needs_review = True
    review.revision += 1
    review.reviewed_from = source_module
    review.reviewed_by_user_id = actor_user_id
    review.reviewed_at = _utcnow()
    db.flush()
