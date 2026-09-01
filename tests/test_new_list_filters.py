from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes.ui import _apply_expediente_filter  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.models.residential import Residential  # noqa: E402


class NewListExpedienteFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Residential.__table__.create(self.engine)
        Participant.__table__.create(self.engine)
        now = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(
                insert(Participant),
                [
                    {
                        "expediente_num": "FE-2025-CL-0090",
                        "nombre": "Ana",
                        "apellido_paterno": "Pérez",
                        "is_head_of_household": False,
                        "is_active": True,
                        "created_at": now,
                        "updated_at": now,
                    },
                    {
                        "expediente_num": "FE-2025-CL-0091",
                        "nombre": "Luis",
                        "apellido_paterno": "Rivera",
                        "is_head_of_household": False,
                        "is_active": True,
                        "created_at": now,
                        "updated_at": now,
                    },
                ],
            )

    def tearDown(self):
        self.engine.dispose()

    def test_filter_normalizes_spaces_and_case(self):
        statement = _apply_expediente_filter(
            select(Participant),
            "  fe-2025-cl-0090  ",
        )

        with Session(self.engine) as session:
            matches = session.execute(statement).scalars().all()

        self.assertEqual(
            [participant.expediente_num for participant in matches],
            ["FE-2025-CL-0090"],
        )

    def test_filter_uses_complete_expediente_number(self):
        statement = _apply_expediente_filter(select(Participant), "0090")

        with Session(self.engine) as session:
            matches = session.execute(statement).scalars().all()

        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
