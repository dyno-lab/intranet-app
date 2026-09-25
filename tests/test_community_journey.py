"""Exercise the user journey across the real routers with one isolated database."""
import unittest
from datetime import date
from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import test_community_routes as route_fixture
from app.models.community import CPFiscalYear, CPParticipant
from app.models.community_activity import CPActivity, CPADMServiceType, CPFiscalActivity
from app.models.community_fiscal import CPFiscalParticipant, CPFiscalState
from app.models.community_operations import CPActivitySession, CPGradeReport
from app.services.community_fiscal import is_enrolled_on, snapshot_for_participant


class CommunityJourneyTests(unittest.TestCase):
    setUp = route_fixture.CommunityRouteTests.setUp
    tearDown = route_fixture.CommunityRouteTests.tearDown
    token = route_fixture.CommunityRouteTests.token
    login = route_fixture.CommunityRouteTests.login
    participant_data = route_fixture.CommunityRouteTests.participant_data

    def post(self, path, **data):
        response = self.client.post(path, data={"token": self.csrf, **data})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn("error", parse_qs(urlparse(response.headers["location"]).query), response.headers["location"])
        return response

    def test_registration_to_multiyear_reports_preserves_identity_and_history(self):
        self.csrf = self.login()
        self.post("/community/fiscal-years", code="FY24", name="Año de prueba", start_date="2024-01-01", end_date="2024-12-31")
        response = self.post("/community/participants", **self.participant_data(self.csrf, fecha_nacimiento="2010-03-01"))
        record_path = response.headers["location"].split("?")[0]
        with Session(self.engine) as db:
            fiscal_id = db.scalar(select(CPFiscalYear.fiscal_year_id))
            participant = db.scalar(select(CPParticipant))
            pid, original_number = participant.participant_id, participant.expediente_num
        self.post("/community/fiscal-participants/sync", fiscal_year_id=fiscal_id, participant_ids=[pid])
        for program_id in (self.voca_id, self.tanf_id):
            selection = {"fiscal_year_id": fiscal_id, "program_id": program_id}
            self.post(f"{record_path}/memberships", **selection, action="enroll", effective_date="2024-01-01", reason="Inscripción")
            self.post("/community/activities", **selection, fiscal_year_ids=[fiscal_id], code="TALLER", description="Taller de prueba")
            self.post("/community/adm/service-types", **selection, name="Orientación")
            with Session(self.engine) as db:
                activity_id = db.scalar(select(CPActivity.activity_id).where(CPActivity.program_id == program_id))
                type_id = db.scalar(select(CPADMServiceType.adm_service_type_id).where(CPADMServiceType.program_id == program_id))
            self.post(f"/community/adm/service-types/{type_id}/activities", **selection, activity_id=activity_id)
            attendance = self.post("/community/attendance", **selection, activity_id=activity_id, session_date="2024-02-10")
            self.post(attendance.headers["location"].split("?")[0], present_participant_ids=[pid])
        report = self.post("/community/school-grades", fiscal_year_id=fiscal_id, program_id=self.voca_id, report_year=2024, report_month=2)
        self.post(report.headers["location"].split("?")[0] + "/participants", participant_id=pid, grade_level="8", spanish_grade="90", english_grade="80")
        params = {"fiscal_year_id": fiscal_id, "program_ids": [self.voca_id, self.tanf_id], "report_type": "por-programa"}
        result = self.client.get("/community/reports", params=params)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("<strong>1</strong> participantes no duplicados", result.text)
        self.assertIn("<strong>2</strong> participaciones", result.text)
        self.post(f"{record_path}/memberships", fiscal_year_id=fiscal_id, program_id=self.tanf_id, action="discharge", effective_date="2024-03-01", reason="Baja solo TANF")
        with Session(self.engine) as db:
            self.assertTrue(is_enrolled_on(db, pid, self.voca_id, fiscal_id, date(2024, 3, 2)))
            self.assertFalse(is_enrolled_on(db, pid, self.tanf_id, fiscal_id, date(2024, 3, 2)))
        self.post(f"/community/fiscal-years/{fiscal_id}/status", action="close")
        self.post(f"{record_path}/edit", **self.participant_data(self.csrf, nombre="Nombre actual", pueblo="Mayagüez", fecha_nacimiento="2010-03-01"))
        with Session(self.engine) as db:
            self.assertEqual(snapshot_for_participant(db, pid, fiscal_id)["nombre"], "Ana")
            self.assertTrue(db.get(CPFiscalState, fiscal_id).snapshots_frozen)
        for output in ("pdf", "excel"):
            download = self.client.get("/community/reports", params={**params, "output": output})
            self.assertEqual(download.status_code, 200, download.text[:200] if output == "pdf" else "")
            self.assertGreater(len(download.content), 1000)
        self.post("/community/fiscal-years", code="FY25", name="Siguiente año", start_date="2025-01-01", end_date="2025-12-31", copy_from=fiscal_id)
        with Session(self.engine) as db:
            next_id = db.scalar(select(CPFiscalYear.fiscal_year_id).where(CPFiscalYear.code == "FY25"))
            self.assertEqual(db.scalar(select(func.count()).select_from(CPFiscalActivity).where(CPFiscalActivity.fiscal_year_id == next_id)), 2)
            for model in (CPFiscalParticipant, CPActivitySession, CPGradeReport):
                self.assertEqual(db.scalar(select(func.count()).select_from(model).where(model.fiscal_year_id == next_id)), 0)
            self.assertEqual(db.get(CPParticipant, pid).expediente_num, original_number)
        self.post("/community/fiscal-participants/sync", fiscal_year_id=next_id, participant_ids=[pid])
        self.post(f"{record_path}/memberships", fiscal_year_id=next_id, program_id=self.voca_id, action="enroll", effective_date="2025-01-01", reason="Continuidad")
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 1)
            self.assertEqual(snapshot_for_participant(db, pid, next_id)["nombre"], "Nombre actual")
            self.assertEqual(snapshot_for_participant(db, pid, fiscal_id)["nombre"], "Ana")
