"""Bidirectional identity review, authorized by the source module and record."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.api.deps import get_db
from app.core.community_access import CommunityContext, csrf_token, require_community_writer, validate_csrf
from app.core.config import settings, require_session_secret
from app.core.residential_scope import has_global_residential_access, require_faro_access, require_record_residential_id
from app.models.community import CPParticipant, CPParticipantProgram
from app.models.participant import Participant
from app.models.user import User
from app.models.community_identity import CPIdentityReview, CPIdentityReviewEvent
from app.services.community_identity import (
    BasicIdentity, confirm_identity_review, find_identity_candidates, linked_identity,
    identity_record_url, identity_review_url, _source_column, comparison_fingerprint, reopen_identity_review,
)
from app.services.community_identity_registration import CONTACTS, exact_identity


def require_identity_enabled():
    if not settings.COMMUNITY_ENABLED:
        raise HTTPException(404, "La revisión de coincidencias no está disponible.")


router = APIRouter(tags=["community-identity"], dependencies=[Depends(require_identity_enabled)])
templates = Jinja2Templates(directory="app/templates")


def _community_source(db: Session, participant_id: int, context: CommunityContext):
    record = db.scalar(select(CPParticipant).where(
        CPParticipant.participant_id == participant_id,
        select(CPParticipantProgram.participant_id).where(
            CPParticipantProgram.participant_id == CPParticipant.participant_id,
            CPParticipantProgram.program_id.in_(context.visible_program_ids),
        ).exists(),
    ))
    if record is None:
        raise HTTPException(404, "Expediente no disponible.")
    return record


def _faro_source(request: Request, db: Session, participant_id: int, user: User):
    if user.role == "viewer":
        raise HTTPException(403, "El rol Viewer permite consulta solamente.")
    record = db.get(Participant, participant_id)
    if record is None:
        raise HTTPException(404, "Expediente no disponible.")
    if not has_global_residential_access(user) and record.residential_id != require_record_residential_id(request, user):
        raise HTTPException(404, "Expediente no disponible.")
    return record


def _render(request: Request, db: Session, source_module: str, record, user: User,
            context: CommunityContext | None = None):
    source = BasicIdentity(record.participant_id, record.expediente_num, record.nombre,
                           record.apellido_paterno, record.apellido_materno, record.fecha_nacimiento)
    candidates = find_identity_candidates(db, source_module, record.participant_id)
    reviews = list(db.scalars(select(CPIdentityReview).where(_source_column(source_module) == record.participant_id)))
    other_column = _source_column('faro' if source_module == 'community' else 'community')
    revisions = {getattr(row, other_column.key): row.revision for row in reviews}
    token = csrf_token(request)
    confirmations = {}
    serializer = URLSafeTimedSerializer(require_session_secret(), salt='identity-review')
    for candidate in candidates:
        cp, faro = (source, candidate) if source_module == 'community' else (candidate, source)
        confirmations[candidate.participant_id] = serializer.dumps([source_module, source.participant_id,
            candidate.participant_id, user.user_id, token, comparison_fingerprint(cp, faro), revisions.get(candidate.participant_id, 0)])
    linked = linked_identity(db, source_module, record.participant_id)
    # Include exact conflicts without offering a second link to the same target.
    conflicts = find_identity_candidates(db, source_module, source.participant_id, conflicts_only=True)
    can_correct = (context.role if context else user.role) in {'admin', 'supervisor'}
    events = list(db.execute(select(CPIdentityReviewEvent, User.username).join(
        User, User.user_id == CPIdentityReviewEvent.reviewed_by_user_id).where(
        CPIdentityReviewEvent.review_id.in_([row.id for row in reviews])).order_by(
        CPIdentityReviewEvent.id.desc()))) if reviews and can_correct else []
    return templates.TemplateResponse(request=request, name="community/identity_review.html", context={
        "request": request, "current_user": user, "cp": context, "today": date.today(),
        "base_template": "community/_base.html" if source_module == "community" else "ui/_base.html",
        "source": source, "source_label": "Comunidad y Prevención" if source_module == "community" else "Faro",
        "other_label": "Faro" if source_module == "community" else "Comunidad y Prevención",
        "candidates": candidates, "exact_ids": {row.participant_id for row in candidates if exact_identity(source, row)},
        "confirmations": confirmations, "contact": CONTACTS[source_module], "conflicts": conflicts,
        "linked": linked, "can_correct": can_correct, "reviews": reviews, "events": events,
        "csrf_token": token, "message": request.query_params.get("msg"),
        "error": request.query_params.get("error"),
        "post_url": identity_review_url(source_module, record.participant_id),
        "back_url": identity_record_url(source_module, record.participant_id),
    })


def _review(db: Session, source_module: str, participant_id: int, candidate_id: int,
            decision: str, user: User, confirmation: str, token: str):
    if decision not in {"yes", "no"}:
        raise HTTPException(422, "Responda Sí o No para confirmar la revisión.")
    try:
        try:
            proof = URLSafeTimedSerializer(require_session_secret(), salt='identity-review').loads(confirmation, max_age=900)
            if not isinstance(proof, list) or len(proof) != 7 or proof[:5] != [source_module, participant_id, candidate_id, user.user_id, token]:
                raise ValueError('Revise nuevamente la coincidencia antes de confirmar.')
        except BadSignature:
            raise ValueError('La confirmación venció. Recargue la comparación.') from None
        confirm_identity_review(db, source_module=source_module, participant_id=participant_id,
                                candidate_id=candidate_id, is_same_person=decision == "yes", actor_user_id=user.user_id,
                                expected_fingerprint=proof[5], expected_revision=proof[6])
        db.commit()
    except ValueError as exc:
        db.rollback()
        path = identity_review_url(source_module, participant_id)
        return RedirectResponse(f"{path}?{urlencode({'error': str(exc)})}", status_code=303)
    except IntegrityError:
        db.rollback()
        path = identity_review_url(source_module, participant_id)
        return RedirectResponse(f"{path}?{urlencode({'error': 'La coincidencia ya fue revisada por otro empleado. Recargue la página.'})}", status_code=303)
    path = identity_record_url(source_module, participant_id) if decision == "yes" else identity_review_url(source_module, participant_id)
    message = "Identidad vinculada. Los expedientes se conservan independientes." if decision == "yes" else "Revisión guardada: son personas distintas."
    return RedirectResponse(f"{path}?{urlencode({'msg': message})}", status_code=303)


@router.get("/community/participants/{participant_id}/identity")
def community_identity(request: Request, participant_id: int, db: Session = Depends(get_db),
                       context: CommunityContext = Depends(require_community_writer)):
    record = _community_source(db, participant_id, context)
    return _render(request, db, "community", record, context.user, context)


@router.post("/community/participants/{participant_id}/identity")
def review_community_identity(request: Request, participant_id: int, token: str = Form(...),
                              candidate_id: int = Form(...), decision: str = Form(...),
                              confirmation: str = Form(''),
                              db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    _community_source(db, participant_id, context)
    return _review(db, "community", participant_id, candidate_id, decision, context.user, confirmation, token)


@router.get("/ui/new-list/{participant_id}/community-identity")
def faro_identity(request: Request, participant_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_faro_access)):
    record = _faro_source(request, db, participant_id, user)
    return _render(request, db, "faro", record, user)


@router.post("/ui/new-list/{participant_id}/community-identity")
def review_faro_identity(request: Request, participant_id: int, token: str = Form(...),
                         candidate_id: int = Form(...), decision: str = Form(...),
                         confirmation: str = Form(''),
                         db: Session = Depends(get_db), user: User = Depends(require_faro_access)):
    validate_csrf(request, token)
    _faro_source(request, db, participant_id, user)
    return _review(db, "faro", participant_id, candidate_id, decision, user, confirmation, token)


def _reopen(db, source_module, participant_id, review_id, revision, user, reason):
    path = identity_review_url(source_module, participant_id)
    try:
        reopen_identity_review(db, source_module, participant_id, review_id, revision, user.user_id, reason)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"{path}?{urlencode({'error': str(exc)})}", status_code=303)
    return RedirectResponse(f"{path}?{urlencode({'msg': 'Decisión reabierta. El vínculo anterior queda sin efecto; revise nuevamente la identidad.'})}", status_code=303)


@router.post('/community/participants/{participant_id}/identity/reopen')
def reopen_community_identity(request: Request, participant_id: int, token: str = Form(...),
        review_id: int = Form(...), revision: int = Form(...), reason: str = Form(...),
        db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    _community_source(db, participant_id, context)
    if context.role not in {'admin', 'supervisor'}:
        raise HTTPException(403, 'Solo un Supervisor o Administrador puede corregir una decisión.')
    return _reopen(db, 'community', participant_id, review_id, revision, context.user, reason)


@router.post('/ui/new-list/{participant_id}/community-identity/reopen')
def reopen_faro_identity(request: Request, participant_id: int, token: str = Form(...),
        review_id: int = Form(...), revision: int = Form(...), reason: str = Form(...),
        db: Session = Depends(get_db), user: User = Depends(require_faro_access)):
    validate_csrf(request, token)
    _faro_source(request, db, participant_id, user)
    if user.role not in {'admin', 'supervisor'}:
        raise HTTPException(403, 'Solo un Supervisor o Administrador puede corregir una decisión.')
    return _reopen(db, 'faro', participant_id, review_id, revision, user, reason)
