"""Home navigation and real program counts honor Community's access scope."""
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from tests import test_community_routes as fixture
from app.models.community import CPUserAccess
from app.services.community import create_participant, create_program


class PageLinks(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.links, self.ids = [], set()
        self.section_menus = []
        self.in_section_menu = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'nav' and attrs.get('aria-label') == 'Secciones de Comunidad':
            self.section_menus.append([])
            self.in_section_menu = True
        if tag == 'a' and 'href' in attrs:
            self.links.append(attrs['href'])
            if self.in_section_menu:
                self.section_menus[-1].append((attrs['href'], attrs.get('aria-current')))
        if 'id' in attrs:
            self.ids.add(attrs['id'])

    def handle_endtag(self, tag):
        if tag == 'nav':
            self.in_section_menu = False


class CommunityHomeTests(unittest.TestCase):
    setUp = fixture.CommunityRouteTests.setUp
    tearDown = fixture.CommunityRouteTests.tearDown
    login = fixture.CommunityRouteTests.login
    token = fixture.CommunityRouteTests.token

    def seed(self):
        with Session(self.engine) as db:
            retired = create_program(db, 'OLD', 'Programa inactivo')
            for name, programs in [('Compartida', [self.voca_id, self.tanf_id]),
                                   ('VOCA', [self.voca_id]), ('ICP', [self.icp_id]),
                                   ('Inactivo', [retired.program_id])]:
                create_participant(db, actor_user_id=self.admin_id, exp_year=2026,
                    program_ids=programs, fields={'fecha_solicitud': '2026-01-15',
                        'procedencia_solicitud': 'Autoreferido', 'nombre': name,
                        'apellido_paterno': 'Prueba', 'genero': 'F'})
            retired.is_active = False
            db.commit()

    def test_counts_deduplicate_people_and_exclude_inactive_and_unassigned_programs(self):
        self.seed()
        for user_id, total, counts in [
            (self.admin_id, 3, {self.voca_id: 2, self.tanf_id: 1, self.icp_id: 1}),
            (self.user_id, 2, {self.voca_id: 2, self.tanf_id: 1}),
        ]:
            with self.subTest(user=user_id):
                self.login(user_id)
                page = self.client.get('/community')
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context['participant_count'], total)
                self.assertEqual(page.context['program_counts'], counts)
                self.assertNotIn('Programa inactivo', page.text)
                if user_id == self.user_id:
                    self.assertNotIn('Programa ICP', page.text)

    def test_context_form_updates_counts_without_exposing_other_programs(self):
        self.seed()
        self.login(self.user_id)
        page = self.client.get('/community')
        response = self.client.post('/community/context', data={
            'token': self.token(page), 'program': self.tanf_id})
        self.assertEqual(response.status_code, 303)
        selected = self.client.get(response.headers['location'])
        self.assertEqual(selected.context['participant_count'], 1)
        self.assertEqual(selected.context['program_counts'], {self.tanf_id: 1})
        links = PageLinks(selected.text).links
        self.assertIn(f'/community/participants?program_id={self.tanf_id}#participants-table-card', links)
        self.assertNotIn(f'/community/participants?program_id={self.voca_id}#participants-table-card', links)
        self.assertEqual(self.client.post('/community/context', data={
            'token': self.token(selected), 'program': self.icp_id}).status_code, 403)

    def test_empty_home_displays_zero_and_available_programs(self):
        self.login()
        page = self.client.get('/community')
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['participant_count'], 0)
        self.assertEqual(page.context['program_counts'], {})
        for program_id in [self.voca_id, self.tanf_id, self.icp_id]:
            self.assertIn(f'/community/participants?program_id={program_id}#participants-table-card', PageLinks(page.text).links)

    def test_visible_links_and_fragment_targets_resolve_for_every_role(self):
        for role, user_id in [('admin', self.admin_id), ('supervisor', self.admin_id),
                              ('user', self.user_id), ('viewer', self.viewer_id)]:
            with Session(self.engine) as db:
                db.get(CPUserAccess, user_id).role = role
                db.commit()
            self.login(user_id)
            page = self.client.get('/community')
            self.assertEqual(page.status_code, 200)
            links = PageLinks(page.text).links
            for path in ['/community/attendance', '/community/school-grades', '/community/reports']:
                self.assertIn(path, links)
            self.assertEqual('/community/participants/new#participant-register-card' in links, role != 'viewer')
            self.assertEqual('/community/programs' in links, role == 'admin')
            self.assertEqual('/community/fiscal-participants' in links, role in ('admin', 'supervisor'))
            for link in set(links):
                with self.subTest(role=role, link=link):
                    url = urlsplit(link)
                    target = self.client.get(url.path or '/community', params=url.query)
                    self.assertEqual(target.status_code, 200, link)
                    if url.fragment:
                        self.assertIn(url.fragment, PageLinks(target.text).ids, link)
            if role == 'viewer':
                self.assertIn('community-viewer.js', page.text)

    def test_sections_keep_the_same_navigation_and_mark_the_current_section(self):
        sections = ['/community', '/community/participants', '/community/attendance',
                    '/community/school-grades', '/community/reports']
        for role, user_id in [('admin', self.admin_id), ('supervisor', self.admin_id),
                              ('user', self.user_id), ('viewer', self.viewer_id)]:
            with Session(self.engine) as db:
                db.get(CPUserAccess, user_id).role = role
                db.commit()
            self.login(user_id)
            pages = [(path, path) for path in sections]
            if role != 'viewer':
                pages.append(('/community/participants/new', '/community/participants'))
            if role in ('admin', 'supervisor'):
                pages.append(('/community/fiscal-participants', None))
            if role == 'admin':
                pages.append(('/community/programs', None))
            for path, active in pages:
                with self.subTest(role=role, path=path):
                    page = self.client.get(path)
                    self.assertEqual(page.status_code, 200)
                    parsed = PageLinks(page.text)
                    self.assertEqual(len(parsed.section_menus), 1)
                    self.assertEqual(parsed.section_menus[0], [
                        (href, 'page' if href == active else None) for href in sections])
                    self.assertEqual('/community/programs' in parsed.links, role == 'admin')
                    self.assertEqual('/community/fiscal-participants' in parsed.links,
                                     role in ('admin', 'supervisor'))
                    self.assertIn('#community-main', parsed.links)
                    self.assertIn('community-main', parsed.ids)


if __name__ == '__main__':
    unittest.main()
