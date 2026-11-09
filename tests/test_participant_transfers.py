import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

for key, value in {"DB_SERVER": "test-server", "DB_NAME": "test-db", "DB_USER": "test-user",
                   "DB_PASSWORD": "test-password", "SESSION_SECRET": "local-test-secret"}.items():
    os.environ.setdefault(key, value)

from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.residential import Residential
from app.models.user import User
from app.models.participant import Participant
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.employee import Employee
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant_transfer import ParticipantTransfer, ParticipantResidentialNumber
from app.models.adm_service_type import ADMServiceType
from app.models.adm_service_type_activity_code import ADMServiceTypeActivityCode
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.services.proposal_participant_sync import get_proposal_participant_update_values
from app.services.participant_residency import session_snapshot_join, eligible_on_date, monthly_participants
from app.services.participant_transfers import transfer_participant, require_available_number


class ParticipantTransferTests(unittest.TestCase):
    models = (Residential, User, Participant, Person, Proposal, ProposalParticipant, Employee,
              ActivityCode, ActivitySession, Attendance, ParticipantTransfer, ParticipantResidentialNumber,
              ADMServiceType, ADMServiceTypeActivityCode, CatalogType, CatalogOption,
              VCAColumn, VCAColumnActivityCode)

    def make_engine(self):
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def connect(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())
        return engine

    def setUp(self):
        self.engine = self.make_engine()
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in self.models])
        self.db = Session(self.engine)
        self.a = Residential(code="A", name="Origen", municipality="Ponce", rq_code="A")
        self.b = Residential(code="B", name="Destino", municipality="Guayama", rq_code="B")
        self.actor = User(username="admin", password_hash="test", role="admin")
        self.proposal = Proposal(code="005", name="Misma propuesta", is_active=True)
        self.employee = Employee(full_name="Empleado")
        self.code = ActivityCode(code="2.b.5")
        self.db.add_all([self.a, self.b, self.actor, self.proposal, self.employee, self.code])
        self.db.flush()
        self.participant = Participant(residential_id=self.a.residential_id, nombre="Ana", apellido_paterno="Prueba",
                                       expediente_num="FE-2026-A-0001", exp_year=2026, exp_seq4="0001",
                                       exp_employee_initials="A", edificio="1", apart="2", genero="F",
                                       is_active=True, estatus="Activo")
        self.other = Participant(residential_id=self.b.residential_id, nombre="Otra", apellido_paterno="Persona",
                                 expediente_num="FE-2026-B-0001", exp_year=2026, exp_seq4="0001")
        self.db.add_all([self.participant, self.other]); self.db.flush()
        self.person = Person(legacy_participant_id=self.participant.participant_id, nombre="Ana", apellido_paterno="Prueba")
        self.db.add(self.person); self.db.flush()
        self.old = ProposalParticipant(person_id=self.person.person_id, proposal_id=self.proposal.proposal_id,
                                       residential_id=self.a.residential_id,
                                       **get_proposal_participant_update_values(self.participant))
        self.db.add(self.old); self.db.flush()
        self.session = self.make_session(self.a.residential_id, date(2026, 9, 10))
        self.attendance = Attendance(participant_id=self.participant.participant_id,
                                     proposal_participant_id=self.old.proposal_participant_id,
                                     session_id=self.session.session_id, attended=True)
        self.db.add(self.attendance); self.db.commit()

    def tearDown(self):
        self.db.close(); self.engine.dispose()

    def make_session(self, residential_id, day):
        session = ActivitySession(residential_id=residential_id, session_date=day,
                                  control_number=f"TEST-{residential_id}-{day.isoformat()}",
                                  proposal_id=self.proposal.proposal_id, employee_id=self.employee.employee_id,
                                  activity_code_id=self.code.activity_code_id)
        self.db.add(session); self.db.flush()
        return session

    def move(self, **overrides):
        values = dict(participant_id=self.participant.participant_id, destination_id=self.b.residential_id,
                      effective_date=date(2026, 10, 1), reason="Mudanza", edificio="4", apart="20",
                      actor=self.actor, expected_residential_id=self.a.residential_id)
        values.update(overrides)
        return transfer_participant(self.db, **values)

    def test_transfer_preserves_old_attendance_and_creates_new_stay_for_same_person(self):
        old_id, attendance_id = self.old.proposal_participant_id, self.attendance.attendance_id
        audit = self.move(); self.db.commit()
        current = self.db.scalar(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None)))
        self.assertEqual(self.db.get(Attendance, attendance_id).proposal_participant_id, old_id)
        self.assertEqual(self.old.residential_id, self.a.residential_id)
        self.assertEqual(self.old.expediente_num, "FE-2026-A-0001")
        self.assertEqual(self.old.apart, "2")
        self.assertEqual(self.old.valid_until, date(2026, 10, 1))
        self.assertEqual(current.person_id, self.person.person_id)
        self.assertEqual(current.proposal_id, self.proposal.proposal_id)
        self.assertEqual(current.residential_id, self.b.residential_id)
        self.assertEqual(current.expediente_num, "FE-2026-B-0002")
        self.assertEqual(current.apart, "20")
        self.assertEqual(audit.old_expediente_num, "FE-2026-A-0001")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Person)), 1)
        self.assertFalse(eligible_on_date(self.old, date(2026, 10, 1)))
        self.assertTrue(eligible_on_date(current, date(2026, 10, 1)))
        self.assertFalse(eligible_on_date(current, date(2026, 9, 30)))

    def test_report_join_does_not_multiply_old_or_new_attendance(self):
        self.move(); self.db.flush()
        current = self.db.scalar(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None)))
        new_session = self.make_session(self.b.residential_id, date(2026, 10, 2))
        self.db.add(Attendance(participant_id=self.participant.participant_id,
                               proposal_participant_id=current.proposal_participant_id,
                               session_id=new_session.session_id, attended=True)); self.db.flush()
        rows = self.db.execute(select(ActivitySession.residential_id, ProposalParticipant.expediente_num)
                               .select_from(Attendance).join(ActivitySession)
                               .join(Participant, Participant.participant_id == Attendance.participant_id)
                               .join(Person, Person.legacy_participant_id == Participant.participant_id)
                               .outerjoin(ProposalParticipant, session_snapshot_join())).all()
        self.assertCountEqual(rows, [(self.a.residential_id, "FE-2026-A-0001"),
                                     (self.b.residential_id, "FE-2026-B-0002")])

    def test_old_number_is_reserved_and_return_reuses_own_number(self):
        self.move(); self.db.flush()
        with self.assertRaises(HTTPException):
            require_available_number(self.db, self.a.residential_id, "0001")
        with self.assertRaises(HTTPException):
            require_available_number(self.db, self.a.residential_id, " 0001 ", expediente_num="FE-2027-A-0001")
        audit = self.move(destination_id=self.a.residential_id, expected_residential_id=self.b.residential_id,
                          effective_date=date(2026, 11, 1))
        self.assertEqual(audit.new_expediente_num, "FE-2026-A-0001")

    def test_conflicting_attendance_or_stale_origin_rejects_without_rewriting_history(self):
        for values in ({"effective_date": date(2026, 9, 10)},
                       {"expected_residential_id": self.b.residential_id},
                       {"effective_date": date(2099, 1, 1)}):
            with self.subTest(values=values), self.assertRaises(HTTPException):
                self.move(**values)
            self.db.rollback()
            self.assertEqual(self.participant.residential_id, self.a.residential_id)
            self.assertIsNone(self.old.valid_until)

    def test_regular_user_and_viewer_cannot_transfer(self):
        for role in ("user", "viewer"):
            self.actor.role = role
            with self.assertRaises(HTTPException):
                self.move()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ParticipantTransfer)), 0)

    def test_monthly_reports_keep_origin_and_do_not_backdate_destination(self):
        self.move(); self.db.flush()
        def eligible(residential, month):
            report = SimpleNamespace(proposal_id=self.proposal.proposal_id,
                                     residential_id=residential.residential_id, report_year=2026, report_month=month)
            return monthly_participants(self.db, report, self.participant.participant_id)
        self.assertEqual(eligible(self.a, 9)[0].expediente_num, "FE-2026-A-0001")
        self.assertEqual(eligible(self.b, 10)[0].expediente_num, "FE-2026-B-0002")
        self.assertEqual(eligible(self.a, 10), [])
        self.assertEqual(eligible(self.b, 9), [])
        self.move(destination_id=self.a.residential_id, expected_residential_id=self.b.residential_id,
                  effective_date=date(2026, 11, 1))
        self.assertEqual(len(eligible(self.a, 9)), 1)
        self.assertEqual(len(eligible(self.a, 11)), 1)
        self.assertEqual(eligible(self.a, 10), [])

    def test_session_date_cannot_cross_the_transfer_date(self):
        from app.services.participant_residency import require_session_stay_compatibility
        self.move(); self.db.flush()
        with self.assertRaises(HTTPException):
            require_session_stay_compatibility(self.db, self.session, date(2026, 10, 2), self.proposal.proposal_id)
        require_session_stay_compatibility(self.db, self.session, date(2026, 9, 12), self.proposal.proposal_id)

    def test_geographic_totals_count_each_served_town_but_one_person(self):
        from app.api.routes.institutional_reports import _aggregate_unique_people
        result = _aggregate_unique_people([(1, None, None, False, "Ponce"),
                                          (1, None, None, False, "Guayama"),
                                          (1, None, None, False, "Ponce")], date(2026, 11, 1))
        self.assertEqual(result[0], 1)
        self.assertEqual(result[4], 2)
        self.assertEqual(result[5], {"Guayama": 1, "Ponce": 1, "No informado": 0})

    def test_preview_does_not_write_and_changed_number_requires_new_confirmation(self):
        from app.services.participant_transfers import preview_transfer
        values = dict(participant_id=self.participant.participant_id, destination_id=self.b.residential_id,
                      effective_date=date(2026, 10, 1), reason="Mudanza", edificio="4", apart="20",
                      actor=self.actor, expected_residential_id=self.a.residential_id)
        preview = preview_transfer(self.db, **values)
        self.assertEqual(preview["expediente_num"], "FE-2026-B-0002")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ParticipantTransfer)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ParticipantResidentialNumber)), 0)
        self.assertIsNone(self.old.valid_until)
        with self.assertRaises(HTTPException):
            self.move(expected_expediente_num="FE-2026-B-9999")
        self.assertIsNone(self.old.valid_until)

    def test_multiple_proposals_and_inactive_enrollment_are_preserved(self):
        proposal = Proposal(code="006", name="Segunda", is_active=True)
        self.db.add(proposal); self.db.flush()
        second = ProposalParticipant(person_id=self.person.person_id, proposal_id=proposal.proposal_id,
            residential_id=self.a.residential_id, **get_proposal_participant_update_values(self.participant))
        second.is_active = False
        second.estatus = "Inactivo"
        self.db.add(second); self.db.flush()
        self.move(); self.db.flush()
        current = self.db.scalars(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None))
                                  .order_by(ProposalParticipant.proposal_id)).all()
        self.assertEqual([row.proposal_id for row in current], [self.proposal.proposal_id, proposal.proposal_id])
        self.assertFalse(current[1].is_active)
        self.assertEqual(current[1].estatus, "Inactivo")
        self.assertTrue(all(row.person_id == self.person.person_id for row in current))

    def test_rollback_reverts_the_entire_transfer(self):
        self.move(); self.db.rollback()
        self.assertEqual(self.participant.residential_id, self.a.residential_id)
        self.assertIsNone(self.old.valid_until)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProposalParticipant)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ParticipantTransfer)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ParticipantResidentialNumber)), 0)

    def test_admin_cannot_sync_or_remove_historical_enrollment(self):
        from app.api.routes import admin
        self.move(); self.db.commit()
        old_name = self.old.nombre
        self.participant.nombre = "Nombre nuevo"; self.db.commit()
        kwargs = dict(request=SimpleNamespace(session={}), proposal_id=self.proposal.proposal_id,
                      residential_id=None, status_filter="all", q=None, only_available=1,
                      db=self.db, current_user=self.actor)
        response = admin.admin_sync_proposal_participant(self.old.proposal_participant_id, **kwargs)
        self.assertEqual(response.status_code, 303)
        self.db.refresh(self.old)
        self.assertEqual(self.old.nombre, old_name)
        for record in self.db.scalars(select(ProposalParticipant)).all():
            response = admin.admin_remove_participant_from_proposal(record.proposal_participant_id, **kwargs)
            self.assertEqual(response.status_code, 303)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(ProposalParticipant)), 2)

    def test_old_and_new_attendance_rosters_respect_effective_date(self):
        from app.api.routes.ui import _load_session_proposal_participants
        self.move(); self.db.flush()
        roster = _load_session_proposal_participants(self.db, self.session, self.actor)
        self.assertEqual([r["proposal_participant"].proposal_participant_id for r in roster],
                         [self.old.proposal_participant_id])
        after_origin = self.make_session(self.a.residential_id, date(2026, 10, 2))
        after_destination = self.make_session(self.b.residential_id, date(2026, 10, 2))
        self.assertEqual(_load_session_proposal_participants(self.db, after_origin, self.actor), [])
        self.assertEqual(len(_load_session_proposal_participants(self.db, after_destination, self.actor)), 1)

    def test_adm_keeps_past_totals_and_counts_one_person_across_both_stays(self):
        from app.api.routes.institutional_reports import _faro_adm_summary, _faro_attendance_count
        service = ADMServiceType(proposal_id=self.proposal.proposal_id, name="Orientación", is_active=True)
        self.db.add(service); self.db.flush()
        self.db.add(ADMServiceTypeActivityCode(adm_service_type_id=service.adm_service_type_id,
                                               activity_code_id=self.code.activity_code_id)); self.db.flush()
        filters = dict(proposal_ids=[self.proposal.proposal_id], year=2026,
                       start_date=date(2026, 9, 1), end_date=date(2026, 9, 30))
        before = _faro_adm_summary(self.db, **filters, reference_date=date(2026, 9, 30))
        self.move(); self.db.flush()
        self.assertEqual(_faro_adm_summary(self.db, **filters, reference_date=date(2026, 9, 30)), before)
        current = self.db.scalar(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None)))
        new_session = self.make_session(self.b.residential_id, date(2026, 10, 2))
        self.db.add(Attendance(participant_id=self.participant.participant_id,
            proposal_participant_id=current.proposal_participant_id, session_id=new_session.session_id,
            attended=True)); self.db.flush()
        filters["end_date"] = date(2026, 10, 31)
        result = _faro_adm_summary(self.db, **filters, reference_date=date(2026, 10, 31))
        self.assertEqual(result["summary"]["services"], 2)
        self.assertEqual(result["summary"]["duplicates"], 2)
        self.assertEqual(result["summary"]["unique_participants"], 1)
        self.assertEqual(_faro_attendance_count(self.db, **filters), 2)

    def test_vca_global_keeps_services_in_each_residential_without_duplicating_people(self):
        from app.api.routes import reports
        from tests.test_proposal_report_participant_snapshots import _global_report_context
        self.participant.vca = self.old.vca = "SI"
        column = VCAColumn(proposal_id=self.proposal.proposal_id, name="Orientación", is_active=True)
        self.db.add(column); self.db.flush()
        self.db.add(VCAColumnActivityCode(vca_column_id=column.vca_column_id, activity_code_id=self.code.activity_code_id))
        self.db.commit()
        self.move(); self.db.flush()
        current = self.db.scalar(select(ProposalParticipant).where(ProposalParticipant.valid_until.is_(None)))
        new_session = self.make_session(self.b.residential_id, date(2026, 10, 2))
        self.db.add(Attendance(participant_id=self.participant.participant_id,
            proposal_participant_id=current.proposal_participant_id, session_id=new_session.session_id, attended=True))
        self.db.flush()
        with _global_report_context():
            context = reports._build_vca_context(self.db, self.actor, self.proposal.proposal_id, 10, 2026, None,
                period_type="custom", start_date=date(2026, 9, 1), end_date=date(2026, 10, 31))
        self.assertEqual(context["total_people"], 1)
        self.assertEqual({row["residential_name"]: row["column_values"][column.vca_column_id]
                          for row in context["rows"]}, {"Origen": 1, "Destino": 1})
        self.assertEqual(context["vca_summary"]["total"]["served"], 1)
        self.assertEqual(context["vca_summary"]["total"]["services"][column.vca_column_id], 2)
