from __future__ import annotations

import unittest
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape


class UiNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        environment = Environment(
            loader=FileSystemLoader("app/templates"),
            autoescape=select_autoescape(["html"]),
        )
        cls.template = environment.get_template("ui/_base.html")

    def test_authenticated_users_can_return_home_without_logging_out(self):
        for role in ("admin", "supervisor", "user"):
            with self.subTest(role=role):
                request = SimpleNamespace(
                    url=SimpleNamespace(path="/ui/new-list"),
                    session={},
                )
                current_user = SimpleNamespace(
                    username=f"{role}@csifpr.org",
                    role=role,
                )

                rendered = self.template.render(
                    request=request,
                    current_user=current_user,
                    msg=None,
                )

                self.assertEqual(rendered.count('href="/home"'), 2)
                self.assertEqual(rendered.count("Volver a Home"), 2)
                self.assertEqual(rendered.count('action="/logout"'), 2)
                self.assertEqual(rendered.count("Cerrar sesión"), 2)


if __name__ == "__main__":
    unittest.main()
