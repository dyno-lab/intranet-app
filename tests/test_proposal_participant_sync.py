from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch


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
from app.services.proposal_participant_sync import (  # noqa: E402
    get_different_proposal_participant_fields,
    get_proposal_participant_update_values,
)


SYNC_FIELDS = (
    "nombre",
    "inicial",
    "apellido_paterno",
    "apellido_materno",
    "genero",
    "fecha_nacimiento",
    "exp_year",
    "exp_employee_initials",
    "exp_seq4",
    "expediente_num",
    "edificio",
    "apart",
    "vca",
    "primera_vez",
    "escolaridad_participante",
    "composicion_familiar",
    "relacion_familiar",
    "estatus",
    "grupo_familiar",
    "fuente_ingreso_principal",
    "rango_ingreso",
    "is_head_of_household",
    "is_active",
)

SOURCE_VALUES = {
    "nombre": " Ana María ",
    "inicial": " L ",
    "apellido_paterno": " Rivera ",
    "apellido_materno": " Soto ",
    "genero": " F ",
    "fecha_nacimiento": date(1990, 5, 12),
    "exp_year": 2026,
    "exp_employee_initials": " AM ",
    "exp_seq4": " 0042 ",
    "expediente_num": " FE-2026-R1-0042 ",
    "edificio": " B ",
    "apart": " 203 ",
    "vca": " SI ",
    "primera_vez": " NO ",
    "escolaridad_participante": " Bachillerato ",
    "composicion_familiar": " Dos adultos ",
    "relacion_familiar": " Jefa ",
    "estatus": " Activo ",
    "grupo_familiar": " GF-42 ",
    "fuente_ingreso_principal": " Empleo ",
    "rango_ingreso": " 1000-1499 ",
    "is_head_of_household": True,
    "is_active": True,
}

EXPECTED_SYNC_VALUES = {
    field_name: value.strip() if isinstance(value, str) else value
    for field_name, value in SOURCE_VALUES.items()
}


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


class _Database:
    def __init__(self, *, objects=None, results=None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.statements = []
        self.get_calls = []
        self.added = []
        self.deleted = []
        self.commits = 0

    def get(self, model, object_id):
        self.get_calls.append((model, object_id))
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

    def commit(self):
        self.commits += 1


def _user(user_id: int = 10, *, residential_id: int | None = 1) -> User:
    user = User(
        username=f"user{user_id}@csifpr.org",
        email=f"user{user_id}@csifpr.org",
        password_hash="not-rendered",
        role="admin",
        is_active=True,
        local_login_enabled=False,
        session_version=1,
    )
    user.user_id = user_id
    if residential_id is not None:
        setattr(user, "_active_residential_id", residential_id)
    return user


def _proposal(proposal_id: int = 7, *, status: str = "active") -> Proposal:
    proposal = Proposal(
        code=f"P-{proposal_id}",
        name=f"Propuesta {proposal_id}",
        is_active=True,
        status=status,
    )
    proposal.proposal_id = proposal_id
    return proposal


def _residential(residential_id: int = 1) -> Residential:
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
    *,
    residential_id: int = 1,
    **overrides,
) -> Participant:
    values = {**SOURCE_VALUES, **overrides}
    participant = Participant(
        residential_id=residential_id,
        created_by_user_id=99,
        **values,
    )
    participant.participant_id = participant_id
    return participant


def _person(person_id: int, participant_id: int) -> Person:
    person = Person(
        legacy_participant_id=participant_id,
        nombre="Nombre de Person",
        inicial="P",
        apellido_paterno="Persistente",
        apellido_materno="Original",
        genero="F",
        fecha_nacimiento=date(1985, 1, 2),
    )
    person.person_id = person_id
    return person


def _proposal_participant(
    proposal_participant_id: int,
    participant: Participant,
    *,
    proposal_id: int = 7,
    person_id: int | None = None,
) -> ProposalParticipant:
    proposal_participant = ProposalParticipant(
        proposal_id=proposal_id,
        person_id=person_id or proposal_participant_id + 1000,
        residential_id=participant.residential_id,
        created_by_user_id=88,
        **get_proposal_participant_update_values(participant),
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


def _update_statements(db: _Database) -> list:
    return [
        statement
        for statement in db.statements
        if getattr(statement, "is_update", False)
    ]


class ProposalParticipantSyncServiceTests(unittest.TestCase):
    def test_all_23_snapshot_fields_are_compared_and_copied(self):
        participant = _participant(20)
        update_values = get_proposal_participant_update_values(participant)

        self.assertEqual(tuple(update_values), SYNC_FIELDS)
        self.assertEqual(len(update_values), 23)
        self.assertEqual(update_values, EXPECTED_SYNC_VALUES)

        snapshot = _proposal_participant(40, participant)
        self.assertEqual(
            get_different_proposal_participant_fields(snapshot, participant),
            [],
        )

        for field_name in SYNC_FIELDS:
            with self.subTest(field_name=field_name):
                original_value = getattr(snapshot, field_name)
                if isinstance(original_value, bool):
                    different_value = not original_value
                elif isinstance(original_value, int):
                    different_value = original_value + 1
                elif isinstance(original_value, date):
                    different_value = original_value.replace(year=original_value.year - 1)
                else:
                    different_value = f"{original_value} anterior"

                setattr(snapshot, field_name, different_value)
                self.assertEqual(
                    get_different_proposal_participant_fields(snapshot, participant),
                    [field_name],
                )
                setattr(snapshot, field_name, original_value)

    def test_detects_name_surnames_schooling_and_building_changes(self):
        participant = _participant(20)
        snapshot = _proposal_participant(40, participant)
        snapshot.nombre = "Nombre anterior"
        snapshot.apellido_paterno = "Apellido anterior"
        snapshot.apellido_materno = "Segundo apellido anterior"
        snapshot.edificio = "Edificio anterior"
        snapshot.escolaridad_participante = "Escolaridad anterior"

        self.assertEqual(
            get_different_proposal_participant_fields(snapshot, participant),
            [
                "nombre",
                "apellido_paterno",
                "apellido_materno",
                "edificio",
                "escolaridad_participante",
            ],
        )


class ProposalParticipantSyncRouteTests(unittest.TestCase):
    def test_outdated_filter_excludes_current_snapshot(self):
        proposal = _proposal()
        residential = _residential()
        current_source = _participant(20)
        outdated_source = _participant(21, nombre=" Beatriz ")
        current_snapshot = _proposal_participant(40, current_source, person_id=30)
        outdated_snapshot = _proposal_participant(41, outdated_source, person_id=31)
        outdated_snapshot.nombre = "Nombre anterior"
        current_person = _person(30, current_source.participant_id)
        outdated_person = _person(31, outdated_source.participant_id)
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[
                _Result(values=[proposal]),
                _Result(values=[residential]),
                _Result(
                    values=[
                        (
                            current_snapshot,
                            current_person,
                            current_source,
                            "owner@example.test",
                            residential.name,
                        ),
                        (
                            outdated_snapshot,
                            outdated_person,
                            outdated_source,
                            "owner@example.test",
                            residential.name,
                        ),
                    ]
                ),
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
                status_filter="all",
                q=None,
                only_available=1,
                sync_filter="outdated",
                msg=None,
                db=db,
                current_user=_user(),
            )

        self.assertEqual(context["selected_sync_filter"], "outdated")
        self.assertEqual(
            [
                row["proposal_participant"].proposal_participant_id
                for row in context["assigned_rows"]
            ],
            [outdated_snapshot.proposal_participant_id],
        )
        self.assertEqual(context["assigned_rows"][0]["outdated_fields"], ["nombre"])
        self.assertTrue(context["assigned_rows"][0]["is_outdated"])

    def test_single_sync_updates_only_selected_proposal_and_leaves_person_clean(self):
        proposal = _proposal()
        source = _participant(20, nombre=" Nombre actualizado ")
        person = _person(30, source.participant_id)
        snapshot = _proposal_participant(401, source, person_id=person.person_id)
        snapshot.nombre = "Nombre anterior"
        original_person_values = (
            person.nombre,
            person.inicial,
            person.apellido_paterno,
            person.apellido_materno,
            person.genero,
            person.fecha_nacimiento,
        )
        db = _Database(
            objects={
                (Proposal, proposal.proposal_id): proposal,
                (Person, person.person_id): person,
            },
            results=[
                _Result(scalar=snapshot),
                _Result(scalar=source),
            ],
        )

        response = admin_routes.admin_sync_proposal_participant(
            proposal_participant_id=snapshot.proposal_participant_id,
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="all",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=db,
            current_user=_user(),
        )

        updates = _update_statements(db)
        self.assertEqual(len(updates), 1)
        update_statement = updates[0]
        update_sql = _statement_sql(update_statement)
        self.assertEqual(update_statement.table.name, "proposal_participants")
        self.assertIn("proposal_participants.proposal_participant_id =", update_sql)
        self.assertIn("proposal_participants.proposal_id =", update_sql)
        self.assertIn(snapshot.proposal_participant_id, _statement_values(update_statement))
        self.assertIn(proposal.proposal_id, _statement_values(update_statement))
        self.assertEqual(
            (
                person.nombre,
                person.inicial,
                person.apellido_paterno,
                person.apellido_materno,
                person.genero,
                person.fecha_nacimiento,
            ),
            original_person_values,
        )
        self.assertFalse(
            any("UPDATE persons" in _statement_sql(statement) for statement in db.statements)
        )
        self.assertEqual(db.added, [])
        self.assertEqual(db.deleted, [])
        self.assertEqual(db.commits, 1)
        self.assertIn("residential_id=1", response.headers["location"])

    def test_finalized_proposal_performs_no_sync_writes(self):
        proposal = _proposal(status="finalized")

        single_db = _Database(objects={(Proposal, proposal.proposal_id): proposal})
        single_response = admin_routes.admin_sync_proposal_participant(
            proposal_participant_id=401,
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=1,
            status_filter="all",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=single_db,
            current_user=_user(),
        )

        sync_all_db = _Database(objects={(Proposal, proposal.proposal_id): proposal})
        sync_all_response = admin_routes.admin_sync_all_proposal_participants(
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=1,
            status_filter="all",
            q=None,
            only_available=1,
            sync_filter="outdated",
            db=sync_all_db,
            current_user=_user(),
        )

        for db, response in (
            (single_db, single_response),
            (sync_all_db, sync_all_response),
        ):
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 303)
                self.assertEqual(db.statements, [])
                self.assertEqual(db.added, [])
                self.assertEqual(db.deleted, [])
                self.assertEqual(db.commits, 0)

    def test_sync_all_updates_only_outdated_snapshots_within_scope(self):
        proposal = _proposal()
        outdated_source = _participant(20, nombre=" Nombre actualizado ")
        current_source = _participant(21, nombre=" Beatriz ")
        outdated_snapshot = _proposal_participant(401, outdated_source, person_id=30)
        current_snapshot = _proposal_participant(402, current_source, person_id=31)
        outdated_snapshot.nombre = "Nombre anterior"
        db = _Database(
            objects={(Proposal, proposal.proposal_id): proposal},
            results=[
                _Result(
                    values=[
                        (outdated_snapshot, outdated_source),
                        (current_snapshot, current_source),
                    ]
                )
            ],
        )

        response = admin_routes.admin_sync_all_proposal_participants(
            request=_Request(1),
            proposal_id=proposal.proposal_id,
            residential_id=2,
            status_filter="all",
            q=None,
            only_available=1,
            sync_filter="all",
            db=db,
            current_user=_user(),
        )

        select_statement = db.statements[0]
        select_sql = _statement_sql(select_statement)
        self.assertIn("proposal_participants.proposal_id =", select_sql)
        self.assertIn("proposal_participants.residential_id =", select_sql)
        self.assertIn("participants.residential_id =", select_sql)
        self.assertIn(proposal.proposal_id, _statement_values(select_statement))
        self.assertIn(1, _statement_values(select_statement))
        self.assertNotIn(2, _statement_values(select_statement))

        updates = _update_statements(db)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].table.name, "proposal_participants")
        self.assertIn(outdated_snapshot.proposal_participant_id, _statement_values(updates[0]))
        self.assertNotIn(current_snapshot.proposal_participant_id, _statement_values(updates[0]))
        self.assertIn(proposal.proposal_id, _statement_values(updates[0]))
        self.assertEqual(db.commits, 1)
        self.assertIn("residential_id=1", response.headers["location"])
        self.assertIn("sync_filter=all", response.headers["location"])


if __name__ == "__main__":
    unittest.main()
