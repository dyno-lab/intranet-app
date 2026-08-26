from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes.ui import _build_new_list_dashboard  # noqa: E402


class _Result:
    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []

    def all(self):
        return self._rows


class NewListDashboardBatchingTests(unittest.TestCase):
    def test_proposal_lookup_batches_more_than_sql_server_parameter_limit(self):
        participant_rows = [
            (
                SimpleNamespace(participant_id=participant_id),
                1,
                "Residencial de prueba",
            )
            for participant_id in range(1, 2502)
        ]

        db = MagicMock()
        db.execute.side_effect = [
            _Result(participant_rows),
            _Result(),
            _Result(),
            _Result(),
        ]

        dashboard = _build_new_list_dashboard(
            db=db,
            current_user=SimpleNamespace(user_id=1),
            is_admin_supervisor=True,
            selected_residential_id=None,
        )

        self.assertEqual(db.execute.call_count, 4)

        proposal_statements = [
            call.args[0]
            for call in db.execute.call_args_list[1:]
        ]
        batch_sizes = []
        for statement in proposal_statements:
            parameter_values = list(statement.compile().params.values())
            participant_ids = next(
                value
                for value in parameter_values
                if isinstance(value, list)
            )
            batch_sizes.append(len(participant_ids))

        self.assertEqual(batch_sizes, [1000, 1000, 501])
        self.assertEqual(dashboard["totals"]["registered_count"], 2501)
        self.assertEqual(dashboard["totals"]["assigned_count"], 0)
        self.assertEqual(dashboard["totals"]["pending_sync_count"], 0)


if __name__ == "__main__":
    unittest.main()
