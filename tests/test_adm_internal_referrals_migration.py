"""SQL Server integration checks; set FARO_MIGRATION_TEST_DSN to a test server.

The suite creates and removes its own uniquely named, empty test database.
"""
from __future__ import annotations

import os
import unittest
from uuid import uuid4

from app.db.adm_internal_referrals_schema import ADM_INTERNAL_REFERRALS_SQL


@unittest.skipUnless(os.environ.get("FARO_MIGRATION_TEST_DSN"), "SQL Server test DSN not set")
class ADMInternalReferralsMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pyodbc

        cls.pyodbc = pyodbc
        cls.dsn = os.environ["FARO_MIGRATION_TEST_DSN"]
        cls.database = "Faro_ADM_Test_" + uuid4().hex
        cls.admin = pyodbc.connect(cls.dsn, autocommit=True, timeout=10)
        cursor = cls.admin.cursor()
        cursor.execute(f"CREATE DATABASE [{cls.database}]")
        try:
            cursor.execute(f"USE [{cls.database}]")
            cursor.execute("""
                CREATE TABLE dbo.platform_data_migrations (migration_key VARCHAR(150) PRIMARY KEY);
                CREATE TABLE dbo.proposals (proposal_id INT PRIMARY KEY, code VARCHAR(10));
                CREATE TABLE dbo.activity_codes (
                    activity_code_id INT PRIMARY KEY, code VARCHAR(20), proposal_id INT NULL);
                CREATE TABLE dbo.proposal_activity_codes (proposal_id INT, activity_code_id INT);
                CREATE TABLE dbo.activity_sessions (
                    session_id INT PRIMARY KEY, proposal_id INT, activity_code_id INT);
                CREATE TABLE dbo.adm_service_types (
                    adm_service_type_id INT PRIMARY KEY, proposal_id INT,
                    name NVARCHAR(150), is_active BIT);
                CREATE TABLE dbo.adm_service_type_activity_codes (
                    id INT IDENTITY PRIMARY KEY, adm_service_type_id INT, activity_code_id INT,
                    UNIQUE (adm_service_type_id, activity_code_id));
            """)
            while cursor.nextset():
                pass
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        try:
            cursor = cls.admin.cursor()
            cursor.execute("USE [master]")
            # ODBC may retain idle pooled connections to this suite-owned database.
            cursor.execute(f"ALTER DATABASE [{cls.database}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{cls.database}]")
        finally:
            cls.admin.close()

    def setUp(self):
        self.db = self.pyodbc.connect(self.dsn, autocommit=False, timeout=10)
        self.cursor = self.db.cursor()
        self.cursor.execute(f"USE [{self.database}]")
        self.cursor.executemany("INSERT INTO dbo.proposals VALUES (?, ?)",
                                [(1, "005"), (2, "006"), (3, "007")])
        self.cursor.executemany("INSERT INTO dbo.activity_codes VALUES (?, ?, ?)",
                                [(1, "2.a.3", 1), (2, "3.a.3", 1), (3, "3.a.11", 1),
                                 (4, "3.a.21", 1), (5, "1.a.1", 1)])
        self.cursor.executemany("INSERT INTO dbo.proposal_activity_codes VALUES (?, ?)",
                                [(proposal, code) for proposal in (2, 3) for code in range(1, 6)])
        category = "Servicios consejería, orientación y trabajo social"
        self.cursor.executemany("INSERT INTO dbo.adm_service_types VALUES (?, ?, ?, ?)",
                                [(101, 1, category, True), (201, 2, category, True),
                                 (301, 3, category, True), (102, 1, "Otro servicio", True)])

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def apply(self):
        self.cursor.execute(ADM_INTERNAL_REFERRALS_SQL)
        while self.cursor.nextset():
            pass

    def mappings(self):
        return {tuple(row) for row in self.cursor.execute(
            "SELECT adm_service_type_id, activity_code_id FROM dbo.adm_service_type_activity_codes"
        ).fetchall()}

    def test_assigns_only_four_codes_in_the_two_proposals(self):
        self.apply()
        self.assertEqual(self.mappings(), {(service, code) for service in (101, 201)
                                          for code in (1, 2, 3, 4)})

    def test_second_run_does_not_duplicate_assignments(self):
        self.apply()
        before = self.mappings()
        self.apply()
        self.assertEqual(self.mappings(), before)
        self.assertEqual(self.cursor.execute(
            "SELECT COUNT(*) FROM dbo.platform_data_migrations").fetchval(), 1)

    def test_preserves_existing_classification(self):
        self.cursor.execute("INSERT INTO dbo.adm_service_type_activity_codes VALUES (102, 1)")
        self.apply()
        self.assertIn((102, 1), self.mappings())
        self.assertNotIn((101, 1), self.mappings())
        self.assertEqual(len(self.mappings()), 8)

    def test_later_manual_change_is_not_undone_on_restart(self):
        self.apply()
        self.cursor.execute("DELETE FROM dbo.adm_service_type_activity_codes "
                            "WHERE adm_service_type_id=101 AND activity_code_id=1")
        self.apply()
        self.assertNotIn((101, 1), self.mappings())
        self.assertEqual(len(self.mappings()), 7)

    def test_missing_or_ambiguous_active_category_prevents_partial_repair(self):
        for ambiguous in (False, True):
            with self.subTest(ambiguous=ambiguous):
                self.cursor.execute("SAVE TRANSACTION category_check")
                if ambiguous:
                    self.cursor.execute("INSERT INTO dbo.adm_service_types "
                                        "SELECT 202, proposal_id, name, is_active "
                                        "FROM dbo.adm_service_types WHERE adm_service_type_id=201")
                else:
                    self.cursor.execute("UPDATE dbo.adm_service_types SET is_active=0 "
                                        "WHERE adm_service_type_id=201")
                with self.assertRaises(self.pyodbc.Error):
                    self.apply()
                self.assertEqual(self.mappings(), set())
                self.assertEqual(self.cursor.execute(
                    "SELECT COUNT(*) FROM dbo.platform_data_migrations").fetchval(), 0)
                self.cursor.execute("ROLLBACK TRANSACTION category_check")

    def test_does_not_assign_an_unrelated_proposal_activity(self):
        self.cursor.execute("DELETE FROM dbo.proposal_activity_codes "
                            "WHERE proposal_id=2 AND activity_code_id=4")
        self.apply()
        self.assertNotIn((201, 4), self.mappings())
        self.assertEqual(len(self.mappings()), 7)

    def test_historical_session_can_establish_the_proposal_association(self):
        self.cursor.execute("DELETE FROM dbo.proposal_activity_codes "
                            "WHERE proposal_id=2 AND activity_code_id=4")
        self.cursor.execute("INSERT INTO dbo.activity_sessions VALUES (1, 2, 4)")
        self.apply()
        self.assertIn((201, 4), self.mappings())


if __name__ == "__main__":
    unittest.main()
