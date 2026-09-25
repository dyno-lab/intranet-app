from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "community-identity-test-session-secret")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import community_identity
from app.core.config import settings
from app.models.base import Base
from app.models.community import CPParticipant, CPParticipantProgram, CPProgram, CPUserAccess, CPUserProgram
from app.models.community_identity import CPIdentityReview
from app.models.participant import Participant
from app.models.platform_permission import PlatformPermission
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential
from app.services.community_identity import (
    BasicIdentity, confirm_identity_review, find_identity_candidates, has_identity_link,
    has_identity_review, identity_similarity, normalize_identity_name, pending_identity_review,
)


class IdentityFixture:
    def setup_database(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'identity.db'}")
        self.statements = []

        @event.listens_for(self.engine, "connect")
        def sqlite_connection(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        @event.listens_for(self.engine, "before_cursor_execute")
        def capture_sql(connection, cursor, statement, parameters, context, executemany):
            self.statements.append(statement)

        models = (Residential, User, UserResidential, PlatformPermission, UserPlatformPermission,
                  Participant, CPProgram, CPUserAccess, CPUserProgram, CPParticipant,
                  CPParticipantProgram, CPIdentityReview)
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in models])
        self.flag = patch.object(settings, "COMMUNITY_ENABLED", True)
        self.flag.start()
        with Session(self.engine) as db:
            home = Residential(code="RES", name="Residencial privado", municipality="Ponce", rq_code="RQ")
            another = Residential(code="OTHER", name="Otro residencial", municipality="Ponce", rq_code="RQ2")
            db.add_all([home, another])
            db.flush()
            self.residential_id, self.other_residential_id = home.residential_id, another.residential_id
            cp_user = User(username="community-only", password_hash="test", role="viewer", is_active=True)
            faro_user = User(username="faro-only", password_hash="test", role="user", is_active=True)
            denied = User(username="denied", password_hash="test", role="user", is_active=True)
            db.add_all([cp_user, faro_user, denied])
            db.flush()
            self.cp_user_id, self.faro_user_id, self.denied_user_id = cp_user.user_id, faro_user.user_id, denied.user_id
            cp_permission = PlatformPermission(key="access_community", name="Comunidad")
            faro_permission = PlatformPermission(key="access_faro", name="Faro")
            db.add_all([cp_permission, faro_permission])
            db.flush()
            db.add_all([UserPlatformPermission(user_id=self.cp_user_id, permission_id=cp_permission.permission_id),
                        UserPlatformPermission(user_id=self.faro_user_id, permission_id=faro_permission.permission_id),
                        UserResidential(user_id=self.faro_user_id, residential_id=self.residential_id),
                        CPUserAccess(user_id=self.cp_user_id, role="user")])
            program = CPProgram(code="VOCA", code_key="VOCA", name="VOCA")
            other_program = CPProgram(code="TANF-M", code_key="TANF-M", name="TANF-M")
            db.add_all([program, other_program])
            db.flush()
            self.program_id, self.other_program_id = program.program_id, other_program.program_id
            db.add(CPUserProgram(user_id=self.cp_user_id, program_id=self.program_id))
            cp = self.add_cp(db)
            faro = self.add_faro(db)
            self.cp_id, self.faro_id = cp.participant_id, faro.participant_id
            db.commit()

    def add_cp(self, db, sequence=1, program_id=None, **changes):
        values = dict(expediente_num=f"CP-2026-{sequence:04d}", exp_year=2026, exp_sequence=sequence,
                      nombre="José", apellido_paterno="Rivera", apellido_materno="López", genero="M",
                      fecha_nacimiento=date(2000, 5, 12), created_by_user_id=self.cp_user_id,
                      direccion_fisica="DIRECCION-CP-PRIVADA", telefono="(787)-555-0100", email="privado@example.com")
        values.update(changes)
        participant = CPParticipant(**values)
        db.add(participant)
        db.flush()
        target_program = program_id or self.program_id
        db.add(CPParticipantProgram(participant_id=participant.participant_id, program_id=target_program,
                                    record_number=f"CP-2026-TEST-{sequence:04d}", created_by_user_id=self.cp_user_id))
        db.flush()
        return participant

    def add_faro(self, db, sequence=1, **changes):
        values = dict(expediente_num=f"FE-2026-RES-{sequence:04d}", residential_id=self.residential_id,
                      nombre="  JOSE  ", apellido_paterno="rivera", apellido_materno="Lopez", genero="M",
                      fecha_nacimiento=date(2000, 5, 12), edificio="EDIFICIO-PRIVADO", apart="APARTAMENTO-PRIVADO")
        values.update(changes)
        participant = Participant(**values)
        db.add(participant)
        db.flush()
        return participant

    def teardown_database(self):
        self.flag.stop()
        self.engine.dispose()
        self.temp.cleanup()


class CommunityIdentityDomainTests(IdentityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_database()
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.teardown_database()

    def test_normalizes_accents_case_and_whitespace(self):
        self.assertEqual(normalize_identity_name("  JOSÉ   María "), "jose maria")
        self.assertEqual([row.participant_id for row in find_identity_candidates(self.db, "community", self.cp_id)], [self.faro_id])
        self.assertEqual([row.participant_id for row in find_identity_candidates(self.db, "faro", self.faro_id)], [self.cp_id])

    def test_approximate_names_require_exact_birth_date_and_base_names(self):
        first = BasicIdentity(1, "CP", "Jose", "Rivera", "Lopez", date(2000, 5, 12))
        typo = BasicIdentity(2, "FE", "Josee", "Rivear", "Lopezz", date(2000, 5, 12))
        self.assertIsNotNone(identity_similarity(first, typo))
        self.assertIsNone(identity_similarity(first, BasicIdentity(2, "FE", "Jose", "Rivera", "Lopez", date(2000, 5, 13))))
        self.assertIsNone(identity_similarity(first, BasicIdentity(2, "FE", "", "Rivera", "Lopez", date(2000, 5, 12))))
        self.assertIsNone(identity_similarity(first, BasicIdentity(2, "FE", "Jose", "", "Lopez", date(2000, 5, 12))))
        self.assertIsNone(identity_similarity(first, BasicIdentity(2, "FE", "Jose", "Rivera", "Lopez", None)))

    def test_candidates_expose_only_basic_identity_fields(self):
        candidate = find_identity_candidates(self.db, "faro", self.faro_id)[0]
        self.assertEqual(set(asdict(candidate)), {"participant_id", "expediente_num", "nombre", "apellido_paterno", "apellido_materno", "fecha_nacimiento"})
        self.assertNotIn("DIRECCION-CP-PRIVADA", str(candidate))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPIdentityReview)), 0)

    def test_yes_links_both_views_without_merging_or_modifying_records(self):
        review = confirm_identity_review(self.db, source_module="community", participant_id=self.cp_id,
                                         candidate_id=self.faro_id, is_same_person=True, actor_user_id=self.cp_user_id)
        self.db.commit()
        self.assertTrue(has_identity_link(self.db, "community", self.cp_id))
        self.assertTrue(has_identity_link(self.db, "faro", self.faro_id))
        self.assertEqual(review.reviewed_from, "community")
        self.assertEqual(review.reviewed_by_user_id, self.cp_user_id)
        self.assertEqual(self.db.get(CPParticipant, self.cp_id).direccion_fisica, "DIRECCION-CP-PRIVADA")
        self.assertEqual(self.db.get(Participant, self.faro_id).edificio, "EDIFICIO-PRIVADO")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Participant)), 1)
        self.assertEqual(find_identity_candidates(self.db, "community", self.cp_id), [])

    def test_no_is_audited_and_not_repeated_from_either_module(self):
        review = confirm_identity_review(self.db, source_module="faro", participant_id=self.faro_id,
                                         candidate_id=self.cp_id, is_same_person=False, actor_user_id=self.faro_user_id)
        self.db.commit()
        self.assertFalse(review.is_same_person)
        self.assertTrue(has_identity_review(self.db, "faro", self.faro_id))
        self.assertFalse(has_identity_link(self.db, "faro", self.faro_id))
        self.assertEqual(find_identity_candidates(self.db, "community", self.cp_id), [])
        self.assertEqual(find_identity_candidates(self.db, "faro", self.faro_id), [])

    def test_post_revalidates_identity_after_data_changes(self):
        self.assertTrue(pending_identity_review(self.db, "community", self.cp_id))
        self.db.get(Participant, self.faro_id).fecha_nacimiento = date(2001, 1, 1)
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "datos actuales"):
            confirm_identity_review(self.db, source_module="community", participant_id=self.cp_id,
                                     candidate_id=self.faro_id, is_same_person=True, actor_user_id=self.cp_user_id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPIdentityReview)), 0)

    def test_one_to_one_database_constraint_protects_confirmed_identity(self):
        confirm_identity_review(self.db, source_module="community", participant_id=self.cp_id,
                                 candidate_id=self.faro_id, is_same_person=True, actor_user_id=self.cp_user_id)
        second = self.add_cp(self.db, sequence=2)
        second_id = second.participant_id
        self.db.commit()
        self.assertEqual(find_identity_candidates(self.db, "community", second_id), [])
        with self.assertRaises(IntegrityError):
            self.db.add(CPIdentityReview(cp_participant_id=second_id, faro_participant_id=self.faro_id,
                                         is_same_person=True, reviewed_from="community", reviewed_by_user_id=self.cp_user_id))
            self.db.flush()
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPIdentityReview)), 1)

    def test_disabled_feature_performs_no_database_queries(self):
        self.statements.clear()
        with patch.object(settings, "COMMUNITY_ENABLED", False):
            self.assertEqual(find_identity_candidates(self.db, "faro", self.faro_id), [])
            self.assertFalse(has_identity_link(self.db, "faro", self.faro_id))
            self.assertFalse(has_identity_review(self.db, "faro", self.faro_id))
            self.assertFalse(pending_identity_review(self.db, "faro", self.faro_id))
        self.assertEqual(self.statements, [])


class CommunityIdentityRouteTests(IdentityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_database()
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="community-identity-route-secret")
        self.app.mount("/static", StaticFiles(directory="app/static"), name="static")
        self.app.include_router(community_identity.router)

        @self.app.get("/_test/session/{user_id}")
        def login(user_id: int, request: Request):
            request.session.clear()
            request.session.update(user_id=user_id, session_version=1, community_program_context="all")
            return {"ok": True}

        def database():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.client = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        self.teardown_database()

    def page(self, module="community", participant_id=None):
        if module == "community":
            return f"/community/participants/{participant_id or self.cp_id}/identity"
        return f"/ui/new-list/{participant_id or self.faro_id}/community-identity"

    def login(self, module="community"):
        self.client.get(f"/_test/session/{self.cp_user_id if module == 'community' else self.faro_user_id}")
        response = self.client.get(self.page(module))
        self.assertEqual(response.status_code, 200, response.text)
        return re.search(r'name="token" value="([^"]+)"', response.text).group(1)

    def test_cp_only_user_can_review_basic_faro_identity_and_confirm(self):
        token = self.login()
        page = self.client.get(self.page())
        self.assertIn("FE-2026-RES-0001", page.text)
        for private in ("EDIFICIO-PRIVADO", "APARTAMENTO-PRIVADO", "Residencial privado"):
            self.assertNotIn(private, page.text)
        response = self.client.post(self.page(), data={"token": token, "candidate_id": self.faro_id, "decision": "yes"})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(response.headers["location"].startswith(f"/community/participants/{self.cp_id}?"))
        with Session(self.engine) as db:
            self.assertTrue(has_identity_link(db, "faro", self.faro_id))

    def test_faro_only_user_can_review_basic_cp_identity_and_reject(self):
        token = self.login("faro")
        page = self.client.get(self.page("faro"))
        self.assertIn("CP-2026-0001", page.text)
        for private in ("DIRECCION-CP-PRIVADA", "privado@example.com", "(787)-555-0100", "TANF-M"):
            self.assertNotIn(private, page.text)
        response = self.client.post(self.page("faro"), data={"token": token, "candidate_id": self.cp_id, "decision": "no"})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("No hay coincidencias pendientes", self.client.get(response.headers["location"]).text)
        with Session(self.engine) as db:
            self.assertFalse(db.scalar(select(CPIdentityReview)).is_same_person)

    def test_source_permissions_and_viewer_roles_are_enforced(self):
        self.login()
        self.assertEqual(self.client.get(self.page("faro")).status_code, 403)
        with Session(self.engine) as db:
            db.get(CPUserAccess, self.cp_user_id).role = "viewer"
            db.commit()
        self.assertEqual(self.client.get(self.page()).status_code, 403)
        self.client.get(f"/_test/session/{self.denied_user_id}")
        self.assertEqual(self.client.get(self.page()).status_code, 403)
        self.assertEqual(self.client.get(self.page("faro")).status_code, 403)

    def test_source_record_must_belong_to_assigned_program_or_residential(self):
        with Session(self.engine) as db:
            other_cp = self.add_cp(db, sequence=2, program_id=self.other_program_id)
            other_faro = self.add_faro(db, sequence=2, residential_id=self.other_residential_id)
            other_cp_id, other_faro_id = other_cp.participant_id, other_faro.participant_id
            db.commit()
        self.login()
        self.assertEqual(self.client.get(self.page(participant_id=other_cp_id)).status_code, 404)
        self.login("faro")
        self.assertEqual(self.client.get(self.page("faro", other_faro_id)).status_code, 404)

    def test_invalid_csrf_and_forged_candidate_cannot_create_link(self):
        token = self.login()
        self.assertEqual(self.client.post(self.page(), data={"token": "wrong", "candidate_id": self.faro_id, "decision": "yes"}).status_code, 403)
        response = self.client.post(self.page(), data={"token": token, "candidate_id": 9999, "decision": "yes"})
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPIdentityReview)), 0)

    def test_disabled_route_does_not_query_cp_tables(self):
        self.login("faro")
        self.statements.clear()
        with patch.object(settings, "COMMUNITY_ENABLED", False):
            self.assertEqual(self.client.get(self.page("faro")).status_code, 404)
        self.assertFalse(any("cp_" in sql.lower() for sql in self.statements))


if __name__ == "__main__":
    unittest.main()
