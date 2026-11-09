"""Real SQL Server checks in an isolated, suite-owned database, never the configured app DB."""
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from tests import test_participant_transfers as fixtures
from app.db.participant_transfers_schema import PARTICIPANT_TRANSFERS_SQL


@unittest.skipUnless(os.environ.get("FARO_MIGRATION_TEST_DSN"), "SQL Server test DSN not set")
class SQLServerTransferTests(fixtures.ParticipantTransferTests):
    @classmethod
    def setUpClass(cls):
        import pyodbc
        cls.dsn = os.environ["FARO_MIGRATION_TEST_DSN"]
        cls.database = "Faro_Transfer_Test_" + uuid4().hex
        cls.admin = pyodbc.connect(cls.dsn, autocommit=True, timeout=10)
        cls.admin.execute(f"CREATE DATABASE [{cls.database}]")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.admin.execute("USE [master]")
            cls.admin.execute(f"ALTER DATABASE [{cls.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cls.admin.execute(f"DROP DATABASE [{cls.database}]")
        finally:
            cls.admin.close()

    def make_engine(self):
        engine = create_engine(URL.create("mssql+pyodbc", query={"odbc_connect": self.dsn}))
        from sqlalchemy import event
        @event.listens_for(engine, "connect")
        def select_database(connection, _):
            connection.cursor().execute(f"USE [{self.database}]")
        fixtures.Base.metadata.drop_all(engine, tables=[m.__table__ for m in self.models])
        return engine

    def test_migration_replaces_legacy_constraint_and_is_repeatable_after_transfer(self):
        self.db.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("""
                DROP TABLE dbo.participant_transfers;
                DROP TABLE dbo.participant_residential_numbers;
                DROP INDEX UX_proposal_participants_current_person ON dbo.proposal_participants;
                ALTER TABLE dbo.proposal_participants DROP COLUMN valid_from, valid_until;
                ALTER TABLE dbo.proposal_participants ADD CONSTRAINT UQ_proposal_participants_proposal_person
                    UNIQUE (proposal_id, person_id);
            """)
            connection.exec_driver_sql(PARTICIPANT_TRANSFERS_SQL)
            connection.exec_driver_sql(PARTICIPANT_TRANSFERS_SQL)
        self.move(); self.db.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PARTICIPANT_TRANSFERS_SQL)
            self.assertEqual(connection.exec_driver_sql("SELECT COUNT(*) FROM dbo.proposal_participants").scalar(), 2)
            self.assertEqual(connection.exec_driver_sql("SELECT COUNT(*) FROM dbo.attendance").scalar(), 1)

    def test_transfer_with_driver_nocount_preserves_history(self):
        from sqlalchemy import text
        self.db.execute(text("SET NOCOUNT ON"))
        self.move(); self.db.commit()
        self.assertEqual(self.participant.expediente_num, "FE-2026-B-0002")

    def test_restart_constraints_and_backfill_keep_both_stays(self):
        from app.db.schema import (PHASE7_PERSONS_PROPOSAL_PARTICIPANTS_CONSTRAINTS_SQL,
                                   PHASE7_PERSONS_PROPOSAL_PARTICIPANTS_BACKFILL_SQL)
        self.move(); self.db.commit()
        old_id = self.old.proposal_participant_id
        self.db.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql(PHASE7_PERSONS_PROPOSAL_PARTICIPANTS_CONSTRAINTS_SQL)
            connection.exec_driver_sql(PHASE7_PERSONS_PROPOSAL_PARTICIPANTS_BACKFILL_SQL)
            self.assertEqual(connection.exec_driver_sql("SELECT COUNT(*) FROM dbo.proposal_participants").scalar(), 2)
            self.assertEqual(connection.exec_driver_sql("SELECT proposal_participant_id FROM dbo.attendance").scalar(), old_id)

    def test_simultaneous_transfers_allocate_distinct_destination_numbers(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from types import SimpleNamespace
        from datetime import date
        from sqlalchemy import select, text
        from sqlalchemy.orm import Session
        from app.services.participant_transfers import transfer_participant
        second = fixtures.Participant(residential_id=self.a.residential_id, nombre="Segunda", apellido_paterno="Prueba",
                                      expediente_num="FE-2026-A-0002", exp_year=2026, exp_seq4="0002", is_active=True)
        self.db.add(second); self.db.flush()
        person = fixtures.Person(legacy_participant_id=second.participant_id, nombre="Segunda", apellido_paterno="Prueba")
        self.db.add(person); self.db.flush()
        self.db.add(fixtures.ProposalParticipant(person_id=person.person_id, proposal_id=self.proposal.proposal_id,
            residential_id=self.a.residential_id, **fixtures.get_proposal_participant_update_values(second)))
        self.db.commit()
        ids = [self.participant.participant_id, second.participant_id]
        origin, destination, actor_id = self.a.residential_id, self.b.residential_id, self.actor.user_id
        self.db.commit()
        barrier = Barrier(2)
        def move(participant_id):
            with Session(self.engine, autoflush=False) as db:
                db.execute(text("SET LOCK_TIMEOUT 10000"))
                barrier.wait(timeout=10)
                audit = transfer_participant(db, participant_id=participant_id, destination_id=destination,
                    expected_residential_id=origin, effective_date=date(2026, 10, 1), reason="Mudanza",
                    edificio="4", apart="20", actor=SimpleNamespace(role="admin", user_id=actor_id))
                number = audit.new_expediente_num
                db.commit()
                return number
        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(move, ids))
        self.assertEqual(set(numbers), {"FE-2026-B-0002", "FE-2026-B-0003"})
