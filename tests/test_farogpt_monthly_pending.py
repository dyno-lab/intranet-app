"""FaroGPT monthly pending counts preserve the source roster and access rules."""
import json
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import event, select

from tests import test_monthly_attendance as fixtures
from app.models.monthly_attendance import AttendanceMonth, AttendanceMonthEvent, AttendanceMonthResidential
from app.models.proposal import Proposal
from app.services import farogpt_monthly_pending as service
from app.services.monthly_attendance import change_months, configure_month


class FaroGPTMonthlyPendingTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.MonthlyAttendanceTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db, self.actor = self.f.db, self.f.fixture.actor
        self.proposal = self.f.fixture.proposal
        self.a, self.b = self.f.fixture.a, self.f.fixture.b
        self.today = date(2026, 11, 14)

    def build(self, **changes):
        args = dict(proposal_ids=[self.proposal.proposal_id], months=[9], year=2026,
                    residential_id=None, today=self.today)
        actor = changes.pop('user', self.actor)
        return service.build(self.db, actor, **{**args, **changes})

    def metrics(self, result):
        return {m['key']: m['value'] for m in result['metrics']}

    def test_absent_period_includes_zero_activity_without_writes(self):
        statements = []
        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(self.f.fixture.engine, 'before_cursor_execute', capture)
        try:
            result = self.build()
        finally:
            event.remove(self.f.fixture.engine, 'before_cursor_execute', capture)
        self.assertEqual(self.metrics(result), {'pending': 2, 'residentials': 2, 'unconfirmed': 2, 'review': 0, 'overdue': 2})
        self.assertEqual({row[0] for row in result['tables'][0]['rows']}, {self.a.name, self.b.name})
        zero = next(row for row in result['tables'][0]['rows'] if row[0] == self.b.name)
        self.assertEqual(zero[5:7], [0, 0])
        self.assertEqual(set(statements), {'SELECT'})
        for model in (AttendanceMonth, AttendanceMonthResidential, AttendanceMonthEvent):
            self.assertEqual(self.db.scalars(select(model)).all(), [])
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_confirmed_and_explicit_no_activity_are_not_pending(self):
        self.f.confirm()
        result = self.build()
        self.assertEqual(self.metrics(result)['pending'], 1)
        self.assertEqual(result['tables'][0]['rows'][0][0], self.b.name)
        self.f.user._active_residential_id = self.b.residential_id
        self.f.confirm(no_activity=True, note='Private reason not for chat')
        completed = self.build()
        self.assertEqual(self.metrics(completed)['pending'], 0)
        self.assertEqual(completed['tables'][0]['rows'], [])
        self.assertNotIn('Private reason', json.dumps(completed))

    def test_changed_confirmation_returns_review_and_source_urls(self):
        self.f.confirm()
        change_months(self.db, self.actor,
            [(self.proposal.proposal_id, self.a.residential_id, date(2026, 9, 10))],
            reason='Private correction', today=self.today)
        self.db.commit()
        result = self.build()
        self.assertEqual(self.metrics(result)['review'], 1)
        self.assertEqual(self.metrics(result)['pending'], 2)
        changed = next(row for row in result['tables'][0]['rows'] if row[0] == self.a.name)
        self.assertEqual(changed[3], 'Requiere nueva confirmación')
        params = parse_qs(urlsplit(changed[-1]['url']).query)
        self.assertEqual(params, {'proposal_id': [str(self.proposal.proposal_id)], 'year': ['2026'], 'month': ['9']})
        serialized = json.dumps(result)
        for private in ('Private correction', 'Usuario MH', 'fingerprint', 'confirmed_by_user_id'):
            self.assertNotIn(private, serialized)

    def test_configured_roster_and_due_date_are_reused(self):
        configure_month(self.db, self.actor, proposal_id=self.proposal.proposal_id, year=2026, month=9,
            due_on=date(2026, 12, 1), residential_ids=[self.a.residential_id], revision=0,
            reason='Only first residential is required', today=self.today)
        self.db.commit()
        result = self.build()
        self.assertEqual(self.metrics(result)['pending'], 1)
        self.assertEqual(self.metrics(result)['overdue'], 0)
        self.assertEqual(result['tables'][0]['rows'][0][4], '01/12/2026')
        self.assertEqual(self.metrics(self.build(residential_id=self.b.residential_id))['pending'], 0)

    def test_snapshot_changes_require_confirmation_without_a_new_tracking_event(self):
        self.f.confirm()
        before = len(self.db.scalars(select(AttendanceMonthEvent)).all())
        self.f.fixture.session.hours = 2
        self.db.commit()
        result = self.build(residential_id=self.a.residential_id)
        self.assertEqual((self.metrics(result)['pending'], self.metrics(result)['review']), (1, 1))
        self.assertEqual(len(self.db.scalars(select(AttendanceMonthEvent)).all()), before)

    def test_multiple_months_and_proposals_count_obligations_not_residential_sum(self):
        second = Proposal(code='FG-MONTH-2', name='Otra propuesta', is_active=True)
        self.db.add(second)
        self.db.commit()
        result = self.build(proposal_ids=[self.proposal.proposal_id, second.proposal_id, second.proposal_id], months=[9, 10, 10])
        metrics = self.metrics(result)
        self.assertEqual((metrics['pending'], metrics['residentials']), (8, 2))
        self.assertEqual(len(result['tables'][0]['rows']), 8)
        self.assertEqual(len(result['source_links']), 4)

    def test_global_filter_and_scoped_supervisor_never_widen_access(self):
        scoped = SimpleNamespace(role='supervisor', _active_residential_id=self.b.residential_id)
        result = self.build(user=scoped)
        self.assertEqual(self.metrics(result)['pending'], 1)
        self.assertEqual({row[0] for row in result['tables'][0]['rows']}, {self.b.name})
        global_filtered = self.build(residential_id=self.b.residential_id)
        self.assertEqual(result['tables'], global_filtered['tables'])
        self.assertIn('propuesta y el mes completos', global_filtered['note'])
        with self.assertRaises(HTTPException) as caught:
            self.build(user=scoped, residential_id=self.a.residential_id)
        self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(HTTPException):
            self.build(residential_id=99999)

    def test_roles_and_invalid_periods_are_rejected(self):
        for role in ('user', 'viewer', ''):
            with self.subTest(role=role), self.assertRaises(HTTPException) as caught:
                self.build(user=SimpleNamespace(role=role, _active_residential_id=self.a.residential_id))
            self.assertEqual(caught.exception.status_code, 403)
        for args in ({'months': []}, {'months': [13]}, {'months': [0]}, {'year': 1999}):
            with self.subTest(args=args), self.assertRaises(HTTPException) as caught:
                self.build(**args)
            self.assertEqual(caught.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()
