"""Community alerts keep program scope, independent roles and durable personal reads."""
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.community import CPParticipant, CPUserAccess
from app.models.community_alerts import CPAnnouncement, CPAnnouncementProgram, CPAnnouncementRead, CPAnnouncementRole
from app.services.community import create_fiscal_year, create_participant
from app.services.community_fiscal import sync_participants, set_snapshot_freeze, set_fiscal_status

from tests import test_community_routes as fixture


class CommunityAlertTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token

    def publish(self, token, **changes):
        data = dict(token=token, title='Aviso de prueba', message='Información para el equipo.\nSegunda línea.',
                    starts_on=date.today().isoformat(), ends_on='', role_scope='all', program_scope='all')
        data.update(changes)
        return self.client.post('/community/alerts/manage', data=data)

    def notice_id(self):
        with Session(self.engine) as db:
            return db.scalar(select(func.max(CPAnnouncement.announcement_id)))

    def participant(self, db, name, programs):
        return create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=programs,
            fields=dict(fecha_solicitud='2026-01-15', procedencia_solicitud='Autoreferido',
                        nombre=name, apellido_paterno='Prueba', genero='F'))

    def fiscal_seed(self):
        with Session(self.engine) as db:
            year = create_fiscal_year(db, '2026-27', 'Año fiscal 2026–2027', date(2026, 7, 1), date(2027, 6, 30))
            changed = self.participant(db, 'Actualizable', [self.voca_id])
            unassigned = self.participant(db, 'SinAsignacion', [self.voca_id, self.tanf_id])
            self.participant(db, 'ReservadoICP', [self.icp_id])
            sync_participants(db, year.fiscal_year_id, [changed.participant_id], actor_user_id=self.admin_id)
            changed.telefono = '787-555-0123'
            db.commit()
            return year.fiscal_year_id, changed.participant_id, unassigned.participant_id

    def test_alert_page_and_summary_are_available_to_every_community_role(self):
        for user_id in (self.admin_id, self.user_id, self.viewer_id):
            self.login(user_id)
            page = self.client.get('/community/alerts')
            self.assertEqual(page.status_code, 200)
            self.assertIn('Alertas', page.text)
            summary = self.client.get('/community/alerts/summary')
            self.assertEqual(summary.status_code, 200)
            self.assertEqual(summary.json()['attention_count'], 0)

    def test_dialog_feed_keeps_categories_and_program_permissions(self):
        self.fiscal_seed()
        self.publish(self.login(), title='Aviso general')
        self.publish(self.login(), title='Aviso reservado ICP', program_scope='selected', program_ids=[str(self.icp_id)])
        self.login(self.user_id)
        response = self.client.get('/community/alerts/feed')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        data = response.json()
        self.assertEqual([item['type'] for item in data['items']], ['task', 'task', 'announcement'])
        self.assertEqual(data['attention_count'], 3)
        self.assertEqual(data['attention_count'], sum(item['unread'] for item in data['items']))
        self.assertNotIn('ICP', response.text)
        tasks = [item for item in data['items'] if item['type'] == 'task']
        self.assertEqual([item['pending_count'] for item in tasks], [1, 1])
        for item in tasks:
            for group in item['groups']:
                self.assertEqual(self.client.get(group['url']).status_code, 200)
        previous_key = data['context_key']
        self.login(self.user_id, program=str(self.voca_id))
        selected = self.client.get('/community/alerts/feed').json()
        self.assertNotEqual(selected['context_key'], previous_key)
        self.assertNotIn('TANF', str(selected))

    def test_dialog_read_uses_community_csrf_and_personal_receipt(self):
        self.publish(self.login())
        aid = self.notice_id()
        self.login(self.viewer_id)
        feed = self.client.get('/community/alerts/feed')
        self.assertEqual(feed.status_code, 200)
        path = f'/community/alerts/notices/{aid}/read'
        self.assertEqual(self.client.post(path, data={'token': 'invalid'}, headers={'Accept': 'application/json'}).status_code, 403)
        response = self.client.post(path, data={'token': feed.json()['csrf_token']}, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'read': True})
        refreshed = self.client.get('/community/alerts/feed').json()
        self.assertFalse(refreshed['items'][0]['unread'])
        self.assertEqual(refreshed['attention_count'], 0)
        self.login()
        self.assertTrue(self.client.get('/community/alerts/feed').json()['items'][0]['unread'])

    def test_publish_commits_unicode_dates_and_targets(self):
        token = self.login()
        result = self.publish(token, title='Reunión de orientación', message='Información: mañana a las 9:00.\nÁrea de Comunidad.',
            ends_on=date.today().isoformat(), role_scope='selected', roles=['user', 'viewer'],
            program_scope='selected', program_ids=[str(self.voca_id)])
        self.assertEqual(result.status_code, 303, result.text)
        with Session(self.engine) as db:
            row = db.get(CPAnnouncement, self.notice_id())
            self.assertEqual(row.title, 'Reunión de orientación')
            self.assertIn('\nÁrea', row.message)
            self.assertEqual(row.ends_on, date.today())
            self.assertEqual(row.created_by_user_id, self.admin_id)
            self.assertIsNotNone(row.created_at)
            self.assertEqual(set(db.scalars(select(CPAnnouncementRole.role))), {'user', 'viewer'})
            self.assertEqual(list(db.scalars(select(CPAnnouncementProgram.program_id))), [self.voca_id])
        managed = self.client.get('/community/alerts/manage')
        self.assertEqual(managed.status_code, 200)
        self.assertIn('Reunión de orientación', managed.text)
        self.assertIn('Consulta', managed.text)

    def test_only_community_admin_can_publish_and_withdraw(self):
        token = self.login()
        self.publish(token)
        notice_id = self.notice_id()
        for user_id in (self.viewer_id, self.user_id):
            token = self.login(user_id)
            self.assertEqual(self.client.get('/community/alerts/manage').status_code, 403)
            self.assertEqual(self.publish(token).status_code, 403)
            self.assertEqual(self.client.post(f'/community/alerts/manage/{notice_id}/withdraw', data={'token': token}).status_code, 403)
        with Session(self.engine) as db:
            db.get(CPUserAccess, self.admin_id).role = 'supervisor'
            db.commit()
        token = self.login()
        self.assertEqual(self.client.get('/community/alerts').status_code, 200)
        self.assertEqual(self.publish(token).status_code, 403)
        self.assertEqual(self.client.get('/community/alerts/manage').status_code, 403)

    def test_access_requires_community_permission_and_enabled_feature(self):
        self.client.get(f'/_test/session/{self.denied_id}')
        self.assertEqual(self.client.get('/community/alerts/summary').status_code, 403)
        self.assertEqual(self.client.get('/community/alerts/feed').status_code, 403)
        self.login()
        with patch.object(settings, 'COMMUNITY_ENABLED', False):
            self.assertEqual(self.client.get('/community/alerts').status_code, 404)
            self.assertEqual(self.client.get('/community/alerts/feed').status_code, 404)

    def test_csrf_required_for_all_mutations(self):
        token = self.login()
        self.assertEqual(self.publish('incorrect-token').status_code, 403)
        self.publish(token)
        aid = self.notice_id()
        for path in (f'/community/alerts/notices/{aid}/read', f'/community/alerts/manage/{aid}/withdraw'):
            self.assertEqual(self.client.post(path, data={'token': 'incorrect-token'}).status_code, 403)
        with Session(self.engine) as db:
            self.assertTrue(db.get(CPAnnouncement, aid).is_active)
            self.assertEqual(db.scalar(select(func.count()).select_from(CPAnnouncementRead)), 0)

    def test_invalid_publication_keeps_form_values_and_writes_nothing(self):
        token = self.login()
        for changes in (dict(title=' '), dict(message='x'*4001), dict(ends_on='2000-01-01'),
                        dict(starts_on='invalid'), dict(role_scope='selected'),
                        dict(role_scope='selected', roles=['faro_admin']),
                        dict(program_scope='selected', program_ids=['999999']),
                        dict(program_scope='selected', program_ids=['not-a-number'])):
            with self.subTest(changes=changes):
                result = self.publish(token, **changes)
                self.assertEqual(result.status_code, 422, result.text)
                self.assertEqual(result.context['values']['message'], changes.get('message', 'Información para el equipo.\nSegunda línea.'))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPAnnouncement)), 0)

    def test_notice_visibility_respects_program_role_and_selected_program(self):
        token = self.login()
        self.publish(token, title='Solo ICP', program_scope='selected', program_ids=[str(self.icp_id)])
        hidden_program = self.notice_id()
        self.publish(token, title='Solo administradores CP', role_scope='selected', roles=['admin'])
        hidden_role = self.notice_id()
        self.publish(token, title='Solo TANF', program_scope='selected', program_ids=[str(self.tanf_id)])
        tanf_notice = self.notice_id()
        self.publish(token, title='Aviso general')
        user_token = self.login(self.user_id)
        page = self.client.get('/community/alerts?view=notices')
        self.assertIn('Solo TANF', page.text)
        self.assertIn('Aviso general', page.text)
        feed = self.client.get('/community/alerts/feed')
        self.assertNotIn('Solo ICP', feed.text)
        self.assertNotIn('Solo administradores CP', feed.text)
        for aid in (hidden_program, hidden_role):
            self.assertEqual(self.client.get(f'/community/alerts/notices/{aid}').status_code, 404)
            self.assertEqual(self.client.post(f'/community/alerts/notices/{aid}/read', data={'token': user_token}).status_code, 404)
        self.login(self.viewer_id)  # Faro admin still cannot see CP-admin-only notice.
        self.assertEqual(self.client.get(f'/community/alerts/notices/{hidden_role}').status_code, 404)
        self.assertNotIn('Solo administradores CP', self.client.get('/community/alerts/feed').text)
        self.login(self.user_id, program=str(self.voca_id))
        self.assertEqual(self.client.get(f'/community/alerts/notices/{tanf_notice}').status_code, 404)
        self.assertEqual(self.client.get(f'/community/alerts?program_id={self.tanf_id}').status_code, 403)
        self.assertIn('Aviso general', self.client.get('/community/alerts?view=notices').text)

    def test_future_expired_and_withdrawn_notices_are_not_visible(self):
        token = self.login()
        today = date.today()
        for changes in (dict(starts_on=(today+timedelta(days=1)).isoformat()),
                        dict(starts_on=(today-timedelta(days=2)).isoformat(), ends_on=(today-timedelta(days=1)).isoformat())):
            self.assertEqual(self.publish(token, **changes).status_code, 303)
            self.assertEqual(self.client.get(f'/community/alerts/notices/{self.notice_id()}').status_code, 404)
        self.publish(token)
        aid = self.notice_id()
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 1)
        self.assertEqual(self.client.post(f'/community/alerts/manage/{aid}/withdraw', data={'token': token}).status_code, 303)
        self.assertEqual(self.client.get(f'/community/alerts/notices/{aid}').status_code, 404)
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 0)
        self.assertEqual(self.client.get('/community/alerts/feed').json()['items'], [])
        with Session(self.engine) as db:
            notice = db.get(CPAnnouncement, aid)
            self.assertFalse(notice.is_active)
            self.assertEqual(notice.withdrawn_by_user_id, self.admin_id)
            self.assertIsNotNone(notice.withdrawn_at)

    def test_personal_read_is_explicit_idempotent_and_persists_for_viewer(self):
        self.publish(self.login())
        aid = self.notice_id()
        token = self.login(self.viewer_id)
        self.client.get(f'/community/alerts/notices/{aid}')
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 1)
        for _ in range(2):
            response = self.client.post(f'/community/alerts/notices/{aid}/read', data={'token': token, 'user_id': self.admin_id})
            self.assertEqual(response.status_code, 303)
        self.login(self.viewer_id)
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 0)
        self.assertIn('Leído', self.client.get(f'/community/alerts/notices/{aid}').text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPAnnouncementRead)), 1)
            self.assertIsNotNone(db.get(CPAnnouncementRead, (aid, self.viewer_id)).read_at)
            self.assertIsNone(db.get(CPAnnouncementRead, (aid, self.admin_id)))
        self.login()
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 1)

    def test_notice_content_is_escaped(self):
        self.publish(self.login(), title='<script>bad()</script>', message='<img src=x onerror=bad()>')
        for path in ('/community/alerts?view=notices', '/community/alerts/manage',
                     f'/community/alerts/notices/{self.notice_id()}'):
            result = self.client.get(path)
            self.assertEqual(result.status_code, 200)
            self.assertIn('&lt;script&gt;', result.text)
            self.assertNotIn('<script>bad()', result.text)
            self.assertNotIn('<img src=x', result.text)

    def test_automatic_tasks_are_scoped_grouped_and_link_to_accessible_records(self):
        fy, changed, unassigned = self.fiscal_seed()
        self.login(self.user_id)
        page = self.client.get('/community/alerts')
        tasks = page.context['items']
        self.assertEqual(len(tasks), 3)  # VOCA sync + unassigned in VOCA and TANF.
        self.assertEqual(sum(t['count'] for t in tasks), 3)
        for task in tasks:
            self.assertIsNone(task['review_url'])
            detail = self.client.get(task['url'])
            self.assertEqual(detail.status_code, 200)
            self.assertNotIn('ReservadoICP', detail.text)
            for row in detail.context['rows']:
                self.assertEqual(self.client.get(f'/community/participants/{row.participant_id}').status_code, 200)
        self.assertEqual(self.client.get(f'/community/alerts/pending?kind=unassigned&program_id={self.icp_id}').status_code, 403)
        self.assertEqual(len(self.client.get(f'/community/alerts?fiscal_year_id={fy}').context['items']), 1)
        self.login()
        for task in self.client.get('/community/alerts').context['items']:
            review = self.client.get(task['review_url'])
            self.assertEqual(review.status_code, 200, task['review_url'])
            self.assertIn(f'id="{task["review_url"].split("#")[1]}"', review.text)

    def test_reading_notice_keeps_tasks_and_fixing_records_removes_them(self):
        fy, changed, unassigned = self.fiscal_seed()
        token = self.login(self.admin_id, program=str(self.voca_id))
        self.publish(token)
        aid = self.notice_id()
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 3)
        self.client.post(f'/community/alerts/notices/{aid}/read', data={'token': token})
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 2)
        urls = [item['url'] for item in self.client.get('/community/alerts').context['items']]
        with Session(self.engine) as db:
            sync_participants(db, fy, [changed, unassigned], actor_user_id=self.admin_id)
            db.commit()
        self.assertEqual(self.client.get('/community/alerts/summary').json()['attention_count'], 0)
        for url in urls:
            self.assertIn('Este pendiente ya no está presente', self.client.get(url).text)

    def test_closed_and_frozen_years_do_not_produce_sync_or_unassigned_tasks(self):
        fy, changed, _ = self.fiscal_seed()
        self.login(program=str(self.voca_id))
        with Session(self.engine) as db:
            set_snapshot_freeze(db, fy, frozen=True, actor_user_id=self.admin_id)
            db.commit()
        tasks = self.client.get('/community/alerts').context['items']
        self.assertEqual([task['kind'] for task in tasks], ['unassigned'])
        self.assertNotIn(changed, tasks[0]['participant_ids'])
        with Session(self.engine) as db:
            set_snapshot_freeze(db, fy, frozen=False, actor_user_id=self.admin_id)
            set_fiscal_status(db, fy, closed=True, actor_user_id=self.admin_id)
            db.commit()
        self.assertEqual([task['kind'] for task in self.client.get('/community/alerts').context['items']], ['unassigned'])

    def test_filters_accept_blank_values_and_reject_invalid_requests(self):
        self.login(self.user_id)
        self.assertEqual(self.client.get('/community/alerts?view=pending&program_id=&fiscal_year_id=').status_code, 200)
        for query in ('view=unknown', 'program_id=invalid', 'fiscal_year_id=999999', 'page=0'):
            self.assertEqual(self.client.get('/community/alerts?'+query).status_code, 422)
        for query in ('kind=unknown', 'kind=sync', 'kind=unassigned&fiscal_year_id=1'):
            self.assertEqual(self.client.get(f'/community/alerts/pending?program_id={self.voca_id}&{query}').status_code, 422)

    def test_notice_pagination_is_bounded(self):
        token = self.login()
        for i in range(21):
            self.assertEqual(self.publish(token, title=f'Aviso {i:02}').status_code, 303)
        first = self.client.get('/community/alerts?view=notices')
        second = self.client.get('/community/alerts?view=notices&page=2')
        self.assertEqual(len(first.context['items']), 20)
        self.assertEqual(len(second.context['items']), 1)
        self.assertEqual(first.context['total'], 21)
        self.assertEqual(len(self.client.get('/community/alerts/manage?page=2').context['managed_notices']), 1)
        self.assertEqual(first.headers['cache-control'], 'no-store')

    def test_notifications_use_faro_dialog_and_header_location(self):
        from tests.test_community_home import PageLinks
        self.login()
        for path in ('/community', '/community/participants', '/community/alerts'):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            header = page.text.split('<header class="cp-shell-header">')[1].split('</header>')[0]
            self.assertIn('id="community-notification-bell"', header)
            self.assertIn('aria-haspopup="dialog"', header)
            self.assertIn('class="faro-notifications"', page.text)
            self.assertIn('/static/css/notifications.css', page.text)
            self.assertIn('data-auto-open="true"' if path == '/community' else 'data-auto-open="false"', page.text)
            self.assertNotIn('home-alerts-title', page.text)
            self.assertNotIn('/community/alerts', [href for href, _ in PageLinks(page.text).section_menus[0]])


if __name__ == '__main__':
    unittest.main()
