"""Run against a disposable SQL Server database only; never the application database."""
import os
import unittest
from uuid import uuid4
from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import URL
from tests import test_data_validation as validation
from tests import test_participant_transfers as transfers
from app.models.base import Base
from app.models.data_validation import DataValidationIssue,DataValidationEvent
from app.models.attendance import Attendance
from app.db.data_validation_schema import DATA_VALIDATION_SQL
from app.services import data_validation as service

TRACKING=(DataValidationIssue,DataValidationEvent)


@unittest.skipUnless(os.environ.get('FARO_MIGRATION_TEST_DSN'),'SQL Server test DSN not set')
class DataValidationSQLServer(validation.DataValidationTests):
    class fixture_class(transfers.ParticipantTransferTests):
        models=transfers.ParticipantTransferTests.models+TRACKING
        def make_engine(self):
            engine=create_engine(URL.create('mssql+pyodbc',query={'odbc_connect':self.dsn}))
            @event.listens_for(engine,'connect')
            def database(connection,_):connection.cursor().execute(f'USE [{self.database}]')
            Base.metadata.drop_all(engine,tables=[model.__table__ for model in self.models])
            return engine

    @classmethod
    def setUpClass(cls):
        import pyodbc
        cls.database='Faro_Validation_Test_'+uuid4().hex
        cls.admin=pyodbc.connect(os.environ['FARO_MIGRATION_TEST_DSN'],autocommit=True,timeout=10)
        cls.admin.execute(f'CREATE DATABASE [{cls.database}]')
        cls.fixture_class.dsn=os.environ['FARO_MIGRATION_TEST_DSN'];cls.fixture_class.database=cls.database

    @classmethod
    def tearDownClass(cls):
        try:
            cls.admin.execute('USE [master]')
            cls.admin.execute(f'ALTER DATABASE [{cls.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            cls.admin.execute(f'DROP DATABASE [{cls.database}]')
        finally:cls.admin.close()

    def test_additive_migration_repeat_preserves_sources_and_audit(self):
        self.db.commit()
        Base.metadata.drop_all(self.f.engine,tables=[m.__table__ for m in TRACKING])
        with self.f.engine.begin() as conn:
            conn.exec_driver_sql(DATA_VALIDATION_SQL);conn.exec_driver_sql(DATA_VALIDATION_SQL)
        service.mutate(self.db,self.user,'revalidate',self.filters);self.db.commit()
        count=len(self.db.scalars(select(DataValidationEvent)).all())
        with self.f.engine.begin() as conn:conn.exec_driver_sql(DATA_VALIDATION_SQL)
        self.db.expire_all()
        self.assertEqual(len(self.db.scalars(select(DataValidationEvent)).all()),count)
        self.assertEqual(len(self.db.scalars(select(Attendance)).all()),1)

    def test_concurrent_assignment_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from types import SimpleNamespace
        from datetime import date
        from sqlalchemy.orm import Session
        from fastapi import HTTPException
        issue=self.issue('hours');actor=SimpleNamespace(user_id=self.user.user_id,username='Prueba',role='admin')
        self.db.commit();barrier=Barrier(2)
        def worker():
            with Session(self.f.engine) as db:
                barrier.wait(timeout=10)
                try:
                    service.mutate(db,actor,'assign',self.filters,targets=[issue['token']],
                        assignee='residential',due_on=date(2026,11,18),note='Asignación concurrente')
                    db.commit();return 200
                except HTTPException as error:
                    db.rollback();return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(sorted(statuses),[200,409])
        self.db.expire_all()
        self.assertEqual(len(self.db.scalars(select(DataValidationEvent).where(DataValidationEvent.kind=='assigned')).all()),1)
