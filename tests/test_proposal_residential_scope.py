from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import admin as admin_routes  # noqa: E402
from app.core.residential_scope import ACTIVE_RESIDENTIAL_SESSION_KEY  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.models.person import Person  # noqa: E402
from app.models.proposal import Proposal  # noqa: E402
from app.models.proposal_participant import ProposalParticipant  # noqa: E402
from app.models.residential import Residential  # noqa: E402
from app.models.user import User  # noqa: E402


class _Request:
    def __init__(self, residential_id: int | None = None):
        self.session = {}
        if residential_id is not None:
            self.session[ACTIVE_RESIDENTIAL_SESSION_KEY] = residential_id


class _Result:
    def __init__(self, *, values=None, scalar=None):
        self.values = list(values or [])
        self.scalar_value = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalar(self):
        return self.scalar_value


class _Database:
    def __init__(self, *, objects=None, results=None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.statements = []
        self.added = []
        self.deleted = []
        self.commits = 0
        self.flushes = 0

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        self.statements.append(statement)
        if getattr(statement, "is_update", False):
            return _Result()
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    def add(self, value):
        self.added.append(value)

    def delete(self, value):
        self.deleted.append(value)

    def flush(self):
        self.flushes += 1

    def commit(self):
        self.commits += 1


def _user(
    user_id: int,
    *,
    role: str = "admin",
    active_residential_id: int | None = None,
) -> User:
    user = User(
        username=f"user{user_id}@csifpr.org",
        email=f"user{user_id}@csifpr.org",
        password_hash="not-rendered",
        role=role,
        is_active=True,
        local_login_enabled=False,
        session_version=1,
    )
    user.user_id = user_id
    if active_residential_id is not None:
        setattr(user, "_active_residential_id", active_residential_id)
    return user


def _proposal(proposal_id: int = 7) -> Proposal:
    proposal = Proposal(
        code=f"P-{proposal_id}",
        name=f"Propuesta {proposal_id}",
        is_active=True,
        status="active",
    )
    proposal.proposal_id = proposal_id
    return proposal


def _residential(residential_id: int) -> Residential:
    residential = Residential(
        code=f"R-{residential_id}",
        name=f"Residencial {residential_id}",
        municipality="Ponce",
        rq_code=f"RQ-{residential_id}",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


def _participant(
    participant_id: int,
    residential_id: int,
    *,
    created_by_user_id: int = 999,
    name: str = "Ana",
) -> Participant:
    participant = Participant(
        residential_id=residential_id,
        created_by_user_id=created_by_user_id,
        expediente_num=f"FE-{residential_id}-{participant_id}",
        nombre=name,
        inicial=None,
        apellido_paterno="Pérez",
        apellido_materno=None,
        genero="F",
        fecha_nacimiento=None,
        edificio=None,
        apart=None,
        vca=None,
        primera_vez=None,
        composicion_familiar=None,
        estatus=None,
        grupo_familiar=None,
        fuente_ingreso_principal=None,
        rango_ingreso=None,
        is_active=True,
    )
    participant.participant_id = participant_id
    return participant


def _person(person_id: int, participant_id: int) -> Person:
    person = Person(
        legacy_participant_id=participant_id,
        nombre="Nombre anterior",
        inicial=None,
        apellido_paterno="Pérez",
        apellido_materno=None,
        genero="F",
        fecha_nacimiento=None,
    )
    person.person_id = person_id
    return person


def _proposal_participant(
    proposal_participant_id: int,
    *,
    proposal_id: int = 7,
    person_id: int = 30,
    residential_id: int = 1,
) -> ProposalParticipant:
    proposal_participant = ProposalParticipant(
        proposal_id=proposal_id,
        person_id=person_id,
        residential_id=residential_id,
        created_by_user_id=321,
        is_active=True,
    )
    proposal_participant.proposal_participant_id = proposal_participant_id
    return proposal_participant


def _statement_sql(statement) -> str:
    return str(statement)


def _statement_values(statement) -> set:
    values = set()
    for value in statement.compile().params.values():
        if isinstance(value, (list, tuple, set)):
            values.update(value)
        else:
            values.add(value)
    return values


class ProposalResidentialScopeTests(unittest.TestCase):
    def test_admin_proposals_scopes_counts_and_preserves_global_counts(self):
        proposal = _proposal()
        scoped_db = _Database(
            results=[
                _Result(values=[proposal]),
                _Result(values=[(proposal.proposal_id, 1)]),
            ]
        )
        global_db = _Database(
            results=[
                _Result(values=[proposal]),
                _Result(values=[(proposal.proposal_id, 2)]),
            ]
        )

        with patch.object(
            admin_routes.templates,
            "TemplateResponse",
            side_effect=lambda _name, context: context,
        ):
            scoped_context = admin_routes.admin_proposals(
                request=_Request(1),
                msg=None,
                db=scoped_db,
                current_user=_user(10, active_residential_id=1),
            )
            global_context = admin_routes.admin_proposals(
                request=_Request(),
                msg=None,
                db=global_db,
                current_user=_user(11),
            )

        scoped_count_sql = _statement_sql(scoped_db.statements[1])
        self.assertIn("proposal_participants.residential_id =", scoped_count_sql)
        self.assertIn(1, _statement_values(scoped_db.statements[1]))
        self.assertEqual(scoped_context["participant_counts"], {7: 1})

        global_count_sql = _statement_sql(global_db.statements[1])
        self.assertNotIn("proposal_participants.residential_id =", global_count_sql)
        self.assertEqual(global_context["participant_counts"], {7: 2})

    def test_participant_page_forces_active_scope_for_all_residential_data(self):
        proposal = _proposal()
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[
                _Result(values=[proposal]),
                _Result(values=[_residential(1)]),
                _Result(),
                _Result(),
            ],
        )

        with patch.object(
            admin_routes.templates,
            "TemplateResponse",
            side_effect=lambda _name, context: context,
        ):
            context = admin_routes.admin_proposal_participants(
                request=_Request(1),
                proposal_id=proposal.proposal_id,
                residential_id="2",
                status_filter="active",
                q=None,
                only_available=1,
                msg=None,
                db=db,
                current_user=_user(10, active_residential_id=1),
            )

        self.assertEqual(context["selected_residential_id"], 1)
        self.assertEqual([row.residential_id for row in context["residentials"]], [1])

        residential_sql = _statement_sql(db.statements[1])
        assigned_sql = _statement_sql(db.statements[2])
        available_sql = _statement_sql(db.statements[3])
        self.assertIn("residentials.residential_id =", residential_sql)
        self.assertIn(1, _statement_values(db.statements[1]))
        self.assertIn("proposal_participants.residential_id =", assigned_sql)
        self.assertIn(1, _statement_values(db.statements[2]))
        self.assertNotIn("proposal_participants.created_by_user_id =", assigned_sql)
        self.assertIn("participants.residential_id =", available_sql)
        self.assertIn(1, _statement_values(db.statements[3]))
        self.assertNotIn("participants.created_by_user_id =", available_sql)

    def test_global_participant_page_honors_selected_residential(self):
        proposal = _proposal()
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[
                _Result(values=[proposal]),
                _Result(values=[_residential(1), _residential(2)]),
                _Result(),
                _Result(),
            ],
        )

        with patch.object(
            admin_routes.templates,
            "TemplateResponse",
            side_effect=lambda _name, context: context,
        ):
            context = admin_routes.admin_proposal_participants(
                request=_Request(),
                proposal_id=proposal.proposal_id,
                residential_id="2",
                status_filter="all",
                q=None,
                only_available=1,
                msg=None,
                db=db,
                current_user=_user(12, role="supervisor"),
            )

        self.assertEqual(context["selected_residential_id"], 2)
        self.assertNotIn(
            "residentials.residential_id =",
            _statement_sql(db.statements[1]),
        )
        self.assertIn(
            "proposal_participants.residential_id =",
            _statement_sql(db.statements[2]),
        )
        self.assertIn(2, _statement_values(db.statements[2]))
        self.assertIn(
            "participants.residential_id =",
            _statement_sql(db.statements[3]),
        )
        self.assertIn(2, _statement_values(db.statements[3]))

    def test_add_rejects_participant_from_another_residential(self):
        proposal = _proposal()
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[_Result()],
        )

        with self.assertRaises(HTTPException) as context:
            admin_routes.admin_add_participants_to_proposal(
                request=_Request(1),
                proposal_id=proposal.proposal_id,
                participant_ids=[20],
                residential_id=2,
                status_filter="active",
                q=None,
                only_available=1,
                db=db,
                current_user=_user(10, active_residential_id=1),
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("participants.residential_id =", _statement_sql(db.statements[0]))
        self.assertIn(1, _statement_values(db.statements[0]))
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.added, [])

    def test_add_uses_active_residential_and_keeps_creator_as_audit(self):
        proposal = _proposal()
        participant = _participant(20, 1, created_by_user_id=777)
        person = _person(30, participant.participant_id)
        current_user = _user(10, active_residential_id=1)
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[
                _Result(values=[participant]),
                _Result(scalar=person),
                _Result(),
            ],
        )

        response = admin_routes.admin_add_participants_to_proposal(
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            participant_ids=[participant.participant_id],
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            db=db,
            current_user=current_user,
        )

        created = next(
            value for value in db.added if isinstance(value, ProposalParticipant)
        )
        self.assertEqual(created.residential_id, 1)
        self.assertEqual(created.created_by_user_id, current_user.user_id)
        self.assertNotEqual(created.created_by_user_id, participant.created_by_user_id)
        self.assertEqual(db.commits, 1)
        self.assertIn("residential_id=1", response.headers["location"])

    def test_single_sync_rejects_association_from_another_residential(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=2)
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[_Result()],
        )

        with self.assertRaises(HTTPException) as context:
            admin_routes.admin_sync_proposal_participant(
                proposal_participant_id=association.proposal_participant_id,
                request=_Request(1),
                proposal_id=proposal.proposal_id,
                residential_id=2,
                status_filter="active",
                q=None,
                only_available=1,
                db=db,
                current_user=_user(10, active_residential_id=1),
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn(
            "proposal_participants.residential_id =",
            _statement_sql(db.statements[0]),
        )
        self.assertIn(1, _statement_values(db.statements[0]))
        self.assertEqual(db.commits, 0)

    def test_single_sync_rejects_source_from_another_residential(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=1)
        person = _person(association.person_id, 20)
        db = _Database(
            objects={
                (Proposal, proposal.proposal_id): proposal,
                (ProposalParticipant, association.proposal_participant_id): association,
                (Person, person.person_id): person,
            },
            results=[
                _Result(scalar=association),
                _Result(),
            ],
        )

        response = admin_routes.admin_sync_proposal_participant(
            proposal_participant_id=association.proposal_participant_id,
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            db=db,
            current_user=_user(10, active_residential_id=1),
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("participants.residential_id =", _statement_sql(db.statements[1]))
        self.assertIn(1, _statement_values(db.statements[1]))
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.added, [])

    def test_single_sync_updates_only_selected_association_in_active_scope(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=1)
        person = _person(association.person_id, 20)
        original_person_name = person.nombre
        source = _participant(20, 1, name="Nombre actualizado")
        db = _Database(
            objects={
                (Proposal, proposal.proposal_id): proposal,
                (ProposalParticipant, association.proposal_participant_id): association,
                (Person, person.person_id): person,
            },
            results=[
                _Result(scalar=association),
                _Result(scalar=source),
            ],
        )

        response = admin_routes.admin_sync_proposal_participant(
            proposal_participant_id=association.proposal_participant_id,
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=db,
            current_user=_user(10, active_residential_id=1),
        )

        update_statements = [
            statement
            for statement in db.statements
            if getattr(statement, "is_update", False)
        ]
        self.assertEqual(len(update_statements), 1)
        update_sql = _statement_sql(update_statements[0])
        self.assertIn("proposal_participants.proposal_participant_id =", update_sql)
        self.assertIn("proposal_participants.proposal_id =", update_sql)
        self.assertIn(association.proposal_participant_id, _statement_values(update_statements[0]))
        self.assertIn(proposal.proposal_id, _statement_values(update_statements[0]))
        self.assertEqual(person.nombre, original_person_name)
        self.assertFalse(
            any("UPDATE persons" in _statement_sql(statement) for statement in db.statements)
        )
        self.assertEqual(db.commits, 1)
        self.assertIn("residential_id=1", response.headers["location"])

    def test_sync_all_forces_active_residential_filter(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=1)
        source = _participant(20, 1, name="Nombre actualizado")
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[_Result(values=[(association, source)])],
        )

        response = admin_routes.admin_sync_all_proposal_participants(
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=db,
            current_user=_user(10, active_residential_id=1),
        )

        select_statement = db.statements[0]
        select_sql = _statement_sql(select_statement)
        self.assertIn("proposal_participants.residential_id =", select_sql)
        self.assertIn("participants.residential_id =", select_sql)
        self.assertIn(1, _statement_values(select_statement))
        self.assertNotIn(2, _statement_values(select_statement))

        update_statements = [
            statement
            for statement in db.statements
            if getattr(statement, "is_update", False)
        ]
        self.assertEqual(len(update_statements), 1)
        self.assertIn(
            association.proposal_participant_id,
            _statement_values(update_statements[0]),
        )
        self.assertIn(proposal.proposal_id, _statement_values(update_statements[0]))
        self.assertEqual(db.commits, 1)
        self.assertIn("residential_id=1", response.headers["location"])

    def test_sync_all_scopes_source_join_to_active_residential(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=1)
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[_Result(values=[(association, None)])],
        )

        response = admin_routes.admin_sync_all_proposal_participants(
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=db,
            current_user=_user(10, active_residential_id=1),
        )

        self.assertEqual(response.status_code, 303)
        select_statement = db.statements[0]
        select_sql = _statement_sql(select_statement)
        self.assertIn("participants.residential_id =", select_sql)
        self.assertIn("proposal_participants.residential_id =", select_sql)
        self.assertIn(1, _statement_values(select_statement))
        self.assertNotIn(2, _statement_values(select_statement))
        self.assertFalse(
            any(getattr(statement, "is_update", False) for statement in db.statements)
        )
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.added, [])

    def test_remove_rejects_association_from_another_residential(self):
        proposal = _proposal()
        association = _proposal_participant(40, residential_id=2)
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[_Result()],
        )

        with self.assertRaises(HTTPException) as context:
            admin_routes.admin_remove_participant_from_proposal(
                proposal_participant_id=association.proposal_participant_id,
                request=_Request(1),
                proposal_id=proposal.proposal_id,
                residential_id=2,
                status_filter="active",
                q=None,
                only_available=1,
                db=db,
                current_user=_user(10, active_residential_id=1),
            )

        self.assertEqual(context.exception.status_code, 403)
        self.assertIn(
            "proposal_participants.residential_id =",
            _statement_sql(db.statements[0]),
        )
        self.assertIn(1, _statement_values(db.statements[0]))
        self.assertEqual(db.deleted, [])
        self.assertEqual(db.commits, 0)

    def test_remove_uses_active_scope_and_global_mode_remains_global(self):
        proposal = _proposal()
        scoped_association = _proposal_participant(40, residential_id=1)
        global_association = _proposal_participant(41, residential_id=2)
        scoped_db = _Database(
            objects={
                (Proposal, proposal.proposal_id): proposal,
                (
                    ProposalParticipant,
                    scoped_association.proposal_participant_id,
                ): scoped_association,
            },
            results=[
                _Result(scalar=scoped_association),
                _Result(scalar=0),
            ],
        )
        global_db = _Database(
            objects={
                (Proposal, proposal.proposal_id): proposal,
                (
                    ProposalParticipant,
                    global_association.proposal_participant_id,
                ): global_association,
            },
            results=[_Result(scalar=0)],
        )

        scoped_response = admin_routes.admin_remove_participant_from_proposal(
            proposal_participant_id=scoped_association.proposal_participant_id,
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            db=scoped_db,
            current_user=_user(10, active_residential_id=1),
        )
        global_response = admin_routes.admin_remove_participant_from_proposal(
            proposal_participant_id=global_association.proposal_participant_id,
            request=_Request(),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="active",
            q=None,
            only_available=1,
            db=global_db,
            current_user=_user(12, role="supervisor"),
        )

        self.assertEqual(scoped_db.deleted, [scoped_association])
        self.assertEqual(scoped_db.commits, 1)
        self.assertIn("residential_id=1", scoped_response.headers["location"])
        self.assertEqual(global_db.deleted, [global_association])
        self.assertEqual(global_db.commits, 1)
        self.assertIn("residential_id=2", global_response.headers["location"])


if __name__ == "__main__":
    unittest.main()
