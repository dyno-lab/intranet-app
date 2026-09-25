from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Barrier

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from app.db.community_schema import COMMUNITY_SCHEMA_SQL
from app.models.base import Base
from app.models.residential import Residential
from app.models.user import User
from app.models.community import (
    CPProgram, CPFiscalYear, CPUserAccess, CPUserProgram, CPSequence,
    CPParticipant, CPParticipantProgram,
)
from app.services.community import (
    create_program, create_fiscal_year, create_participant, update_participant,
    associate_participant_programs, _sequence_lock_statement,
)


CP_MODELS = (CPProgram, CPFiscalYear, CPUserAccess, CPUserProgram, CPSequence, CPParticipant, CPParticipantProgram)


class CommunityDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'community.db'}", connect_args={"timeout": 15})

        @event.listens_for(self.engine, "connect")
        def enforce_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine, tables=[Residential.__table__, User.__table__, *[model.__table__ for model in CP_MODELS]])
        self.db = Session(self.engine)
        actor = User(username="community-admin", password_hash="not-a-real-password", role="viewer", is_active=True, created_at=datetime.now(timezone.utc))
        self.db.add(actor)
        self.db.flush()
        self.actor_id = actor.user_id
        self.voca = create_program(self.db, "VOCA", "Programa VOCA")
        self.tanf = create_program(self.db, "TANF-M", "Programa TANF-M")
        self.program_ids = [self.voca.program_id, self.tanf.program_id]
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def fields(self, **changes):
        values = {"nombre": " Ana María ", "inicial": "L", "apellido_paterno": "Rivera", "apellido_materno": "Soto", "genero": "f", "fecha_nacimiento": "2000-05-12", "telefono": "(787)-555-0100", "email": "ana@example.com", "direccion_fisica": "Calle Uno", "pueblo": "San Juan", "is_head_of_household": True}
        values.update(changes)
        return values

    def create(self, **changes):
        arguments = dict(actor_user_id=self.actor_id, exp_year=2026, program_ids=self.program_ids, fields=self.fields())
        arguments.update(changes)
        return create_participant(self.db, **arguments)

    def test_unique_participant_has_multiple_stable_program_records(self):
        participant = self.create()
        self.db.commit()
        self.assertEqual(participant.expediente_num, "CP-2026-0001")
        self.assertEqual(participant.exp_seq4, "0001")
        self.assertEqual(participant.nombre, "Ana María")
        self.assertEqual(participant.genero, "F")
        self.assertEqual(participant.fecha_nacimiento, date(2000, 5, 12))
        records = self.db.scalars(select(CPParticipantProgram.record_number)).all()
        self.assertCountEqual(records, ["CP-2026-VOCA-0001", "CP-2026-TANF-M-0001"])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 1)
        create_fiscal_year(self.db, "2027", "Año fiscal 2027", date(2026, 7, 1), date(2027, 6, 30))
        self.db.commit()
        self.assertEqual(participant.expediente_num, "CP-2026-0001")
        self.assertCountEqual(self.db.scalars(select(CPParticipantProgram.record_number)).all(), records)

    def test_sequence_is_shared_across_programs_and_independent_per_record_year(self):
        first = self.create(program_ids=[self.program_ids[0]])
        second = self.create(program_ids=[self.program_ids[1]])
        next_year = self.create(exp_year=2027)
        self.db.commit()
        self.assertEqual([first.expediente_num, second.expediente_num, next_year.expediente_num], ["CP-2026-0001", "CP-2026-0002", "CP-2027-0001"])

    def test_later_program_association_preserves_original_record_and_demographics(self):
        participant = self.create(program_ids=[self.program_ids[0]])
        participant_id = participant.participant_id
        self.db.commit()
        original_values = {column.name: getattr(participant, column.name) for column in CPParticipant.__table__.columns}
        original_link = self.db.get(CPParticipantProgram, (participant_id, self.program_ids[0]))
        original_audit = (original_link.created_at, original_link.created_by_user_id, original_link.record_number)
        create_fiscal_year(self.db, "2027", "Año fiscal 2027", date(2027, 1, 1), date(2027, 12, 31))
        # Even a later creation in another year must not affect this association.
        self.create(exp_year=2027, program_ids=[self.program_ids[0]])
        self.db.commit()
        returned = associate_participant_programs(
            self.db, participant_id=participant_id, actor_user_id=self.actor_id,
            program_ids=[self.program_ids[1]],
        )
        self.db.commit()
        self.assertEqual(returned.participant_id, participant_id)
        self.assertEqual({column.name: getattr(returned, column.name) for column in CPParticipant.__table__.columns}, original_values)
        new_link = self.db.get(CPParticipantProgram, (participant_id, self.program_ids[1]))
        self.assertEqual(new_link.record_number, "CP-2026-TANF-M-0001")
        self.assertEqual((original_link.created_at, original_link.created_by_user_id, original_link.record_number), original_audit)
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 1)
        self.assertEqual(self.db.get(CPSequence, 2027).last_value, 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 2)

    def test_repeated_association_is_idempotent_and_keeps_prior_links(self):
        participant = self.create(program_ids=[self.program_ids[0]])
        self.db.commit()
        for _ in range(2):
            associate_participant_programs(
                self.db, participant_id=participant.participant_id, actor_user_id=self.actor_id,
                program_ids=[self.program_ids[0], self.program_ids[1], self.program_ids[1]],
            )
            self.db.commit()
        links = self.db.scalars(select(CPParticipantProgram).where(CPParticipantProgram.participant_id == participant.participant_id)).all()
        self.assertCountEqual([link.record_number for link in links], ["CP-2026-VOCA-0001", "CP-2026-TANF-M-0001"])
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 1)

    def test_association_rollback_preserves_existing_record_and_links(self):
        participant = self.create(program_ids=[self.program_ids[0]])
        participant_id = participant.participant_id
        self.db.commit()
        associate_participant_programs(
            self.db, participant_id=participant_id, actor_user_id=self.actor_id,
            program_ids=[self.program_ids[1]],
        )
        self.db.rollback()
        self.assertIsNone(self.db.get(CPParticipantProgram, (participant_id, self.program_ids[1])))
        self.assertEqual(self.db.get(CPParticipantProgram, (participant_id, self.program_ids[0])).record_number, "CP-2026-VOCA-0001")
        self.assertEqual(self.db.get(CPParticipant, participant_id).nombre, "Ana María")
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 1)

    def test_missing_record_or_invalid_program_association_adds_nothing(self):
        participant = self.create(program_ids=[self.program_ids[0]])
        participant_id = participant.participant_id
        self.db.commit()
        for record_id, program_ids in (
            (999999, [self.program_ids[1]]),
            (participant_id, [self.program_ids[1], 999999]),
            (participant_id, [self.program_ids[1], True]),
        ):
            with self.subTest(record_id=record_id, program_ids=program_ids), self.assertRaises(ValueError):
                associate_participant_programs(self.db, participant_id=record_id, actor_user_id=self.actor_id, program_ids=program_ids)
            self.assertIsNone(self.db.get(CPParticipantProgram, (participant_id, self.program_ids[1])))
        self.tanf.is_active = False
        self.db.commit()
        with self.assertRaises(ValueError):
            associate_participant_programs(self.db, participant_id=participant_id, actor_user_id=self.actor_id, program_ids=[self.program_ids[1]])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipantProgram)), 1)
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 1)

    def test_services_do_not_commit_and_rollback_reverts_entire_creation(self):
        self.create()
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipantProgram)), 0)
        self.assertIsNone(self.db.get(CPSequence, 2026))
        self.assertEqual(self.create().expediente_num, "CP-2026-0001")

    def test_edit_personal_data_preserves_record_identity_and_program_links(self):
        participant = self.create()
        participant_id = participant.participant_id
        self.db.commit()
        identity = (participant.expediente_num, participant.exp_year, participant.exp_sequence, participant.created_by_user_id, participant.created_at)
        links_before = self.db.execute(select(
            CPParticipantProgram.program_id, CPParticipantProgram.record_number,
            CPParticipantProgram.created_by_user_id, CPParticipantProgram.created_at,
        ).where(CPParticipantProgram.participant_id == participant_id)).all()
        result = update_participant(self.db, participant_id=participant_id, fields={
            "direccion_fisica": " Calle Nueva 123 ", "email": " actualizado@example.com ",
        })
        self.db.commit()
        self.assertEqual(result.participant_id, participant_id)
        self.assertEqual((result.direccion_fisica, result.email), ("Calle Nueva 123", "actualizado@example.com"))
        self.assertEqual((result.nombre, result.fecha_nacimiento, result.telefono), ("Ana María", date(2000, 5, 12), "(787)-555-0100"))
        self.assertEqual((result.expediente_num, result.exp_year, result.exp_sequence, result.created_by_user_id, result.created_at), identity)
        links_after = self.db.execute(select(
            CPParticipantProgram.program_id, CPParticipantProgram.record_number,
            CPParticipantProgram.created_by_user_id, CPParticipantProgram.created_at,
        ).where(CPParticipantProgram.participant_id == participant_id)).all()
        self.assertCountEqual(links_after, links_before)
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 1)

    def test_edit_rejects_invalid_or_protected_fields_without_partial_change(self):
        participant = self.create()
        participant_id = participant.participant_id
        self.db.commit()
        original = {column.name: getattr(participant, column.name) for column in CPParticipant.__table__.columns}
        for changes in (
            {"email": "invalid"}, {"nombre": " "}, {"genero": "invalid"},
            {"fecha_nacimiento": "not-a-date"}, {"inicial": "x" * 13},
            {"primera_vez": "otro"}, {"exp_year": 2027}, {"exp_sequence": 9999},
            {"expediente_num": "CP-2027-9999"}, {"program_ids": []},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                update_participant(self.db, participant_id=participant_id, fields={"direccion_fisica": "No debe guardarse", **changes})
            self.db.commit()
            self.assertEqual({column.name: getattr(participant, column.name) for column in CPParticipant.__table__.columns}, original)
        with self.assertRaises(ValueError):
            update_participant(self.db, participant_id=999999, fields={"email": "valido@example.com"})

    def test_edit_uses_shared_normalization_and_does_not_commit(self):
        participant = self.create()
        participant_id = participant.participant_id
        self.db.commit()
        update_participant(self.db, participant_id=participant_id, fields={
            "inicial": " R ", "genero": " f ", "primera_vez": " no ",
            "vca": " si ", "fecha_nacimiento": "1999-03-04", "is_head_of_household": False,
        })
        self.assertEqual((participant.inicial, participant.genero, participant.primera_vez, participant.vca), ("R", "F", "NO", "SI"))
        self.assertEqual(participant.fecha_nacimiento, date(1999, 3, 4))
        self.assertFalse(participant.is_head_of_household)
        self.db.rollback()
        self.assertEqual((participant.inicial, participant.fecha_nacimiento, participant.is_head_of_household), ("L", date(2000, 5, 12), True))

    def test_invalid_actor_constraint_rolls_back_allocated_number(self):
        with self.assertRaises(IntegrityError):
            self.create(actor_user_id=999999)
        self.db.rollback()
        self.assertIsNone(self.db.get(CPSequence, 2026))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipantProgram)), 0)

    def test_program_code_preserves_case_but_rejects_case_variant_duplicate(self):
        program = create_program(self.db, "ICCa", "Programa ICCa")
        self.assertEqual(program.code, "ICCa")
        with self.assertRaises(ValueError):
            create_program(self.db, "ICCA", "Duplicado")
        participant = self.create(program_ids=[program.program_id])
        self.assertEqual(self.db.scalar(select(CPParticipantProgram.record_number).where(CPParticipantProgram.participant_id == participant.participant_id)), "CP-2026-ICCa-0001")

    def test_fiscal_dates_are_configurable_and_invalid_ranges_are_rejected(self):
        fiscal = create_fiscal_year(self.db, "FY26-27", "Período configurado", "2026-08-15", "2027-09-20")
        self.assertEqual((fiscal.start_date, fiscal.end_date), (date(2026, 8, 15), date(2027, 9, 20)))
        with self.assertRaises(ValueError):
            create_fiscal_year(self.db, "INVALID", "Fechas invertidas", date(2027, 1, 1), date(2026, 1, 1))

    def test_invalid_or_inactive_program_creates_no_record(self):
        for ids in ([999999], [True]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.create(program_ids=ids)
        self.voca.is_active = False
        self.db.commit()
        with self.assertRaises(ValueError):
            self.create()
        self.assertIsNone(self.db.get(CPSequence, 2026))

    def test_duplicate_program_ids_produce_one_association(self):
        self.create(program_ids=[self.program_ids[0], self.program_ids[0]])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipantProgram)), 1)

    def test_validation_rejects_invalid_fields_before_allocating(self):
        invalid_fields = [
            {"nombre": " "}, {"inicial": "x" * 13}, {"genero": ""},
            {"telefono": "123"}, {"email": "missing-at"},
            {"fecha_nacimiento": "2026-02-30"}, {"fecha_nacimiento": "9999-01-01"},
            {"is_head_of_household": "false"}, {"expediente_num": "CP-2026-9999"},
        ]
        for changes in invalid_fields:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.create(fields=self.fields(**changes))
        self.assertIsNone(self.db.get(CPSequence, 2026))

    def test_four_digit_sequence_exhaustion_does_not_overflow_record_format(self):
        self.db.add(CPSequence(exp_year=2026, last_value=9999))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "agotó"):
            self.create()
        self.db.rollback()
        self.assertEqual(self.db.get(CPSequence, 2026).last_value, 9999)

    def test_database_enforces_unique_sequence_even_outside_service(self):
        self.create()
        self.db.commit()
        self.db.add(CPParticipant(exp_year=2026, exp_sequence=1, expediente_num="CP-2026-ALTERED", nombre="Otra", apellido_paterno="Persona", genero="F", created_by_user_id=self.actor_id))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_community_roles_are_independent_of_faro_and_multi_program(self):
        self.db.add(CPUserAccess(user_id=self.actor_id, role="admin"))
        self.db.add_all([CPUserProgram(user_id=self.actor_id, program_id=program_id) for program_id in self.program_ids])
        self.db.commit()
        self.assertEqual(self.db.get(User, self.actor_id).role, "viewer")
        self.assertEqual(self.db.get(CPUserAccess, self.actor_id).role, "admin")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPUserProgram)), 2)

    def test_sqlite_concurrent_creations_get_distinct_numbers(self):
        # Exercises actual concurrent SQLite transactions, not SQL Server locks.
        barrier = Barrier(4)

        def create_concurrently(_):
            with Session(self.engine) as session:
                barrier.wait(timeout=10)
                participant = create_participant(session, actor_user_id=self.actor_id, exp_year=2028, program_ids=self.program_ids, fields=self.fields())
                number = participant.expediente_num
                session.commit()
                return number

        with ThreadPoolExecutor(max_workers=4) as executor:
            numbers = list(executor.map(create_concurrently, range(4)))
        self.assertCountEqual(numbers, ["CP-2028-0001", "CP-2028-0002", "CP-2028-0003", "CP-2028-0004"])

    def test_mssql_lock_compiles_and_schema_is_additive(self):
        statement = str(_sequence_lock_statement(2026).compile(dialect=mssql.dialect()))
        self.assertIn("WITH (UPDLOCK, HOLDLOCK)", statement)
        for model in CP_MODELS:
            ddl = str(CreateTable(model.__table__).compile(dialect=mssql.dialect()))
            self.assertIn(f"CREATE TABLE {model.__tablename__}", ddl)
            self.assertIn(f"IF OBJECT_ID(N'dbo.{model.__tablename__}', N'U') IS NULL", COMMUNITY_SCHEMA_SQL)
            for foreign_key in model.__table__.foreign_keys:
                self.assertTrue(foreign_key.target_fullname.startswith(("cp_", "users.")))
        self.assertNotIn("DROP TABLE", COMMUNITY_SCHEMA_SQL)
        self.assertNotIn("DELETE FROM", COMMUNITY_SCHEMA_SQL)


if __name__ == "__main__":
    unittest.main()
