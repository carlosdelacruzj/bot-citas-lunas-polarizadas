from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from appointment_bot.domain import RunReport
from appointment_bot.services.client_transitions import (
    client_can_submit,
    reconcile_pending_submission,
)
from appointment_bot.services.database import (
    add_client,
    client_reservation_pending,
    mark_client_submission_pending,
    set_client_active,
)
from tests.helpers import make_settings


class ClientTransitionTests(unittest.TestCase):
    def test_paused_client_cannot_submit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            add_client("client-1", "Test", "user", "password", 1, settings=settings)

            self.assertTrue(client_can_submit("client-1", settings))

            set_client_active("client-1", False, settings=settings)

            self.assertFalse(client_can_submit("client-1", settings))

    def test_old_pending_submission_is_cleared_after_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(make_settings(Path(directory)), error_backoff_seconds=60)
            add_client("client-1", "Test", "user", "password", 1, settings=settings)
            mark_client_submission_pending("client-1", settings=settings)
            old = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
            with closing(sqlite3.connect(settings.database_path)) as connection:
                with connection:
                    connection.execute(
                        "UPDATE client_state SET last_run_at = ? WHERE client_id = ?",
                        (old, "client-1"),
                    )

            reconciled = reconcile_pending_submission(
                "client-1",
                RunReport(status="unavailable", message="No slots", exit_code=0),
                settings,
            )

            self.assertTrue(reconciled)
            self.assertFalse(client_reservation_pending("client-1", settings=settings))

    def test_recent_pending_submission_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(make_settings(Path(directory)), error_backoff_seconds=60)
            add_client("client-1", "Test", "user", "password", 1, settings=settings)
            mark_client_submission_pending("client-1", settings=settings)

            reconciled = reconcile_pending_submission(
                "client-1",
                RunReport(status="unavailable", message="No slots", exit_code=0),
                settings,
            )

            self.assertFalse(reconciled)
            self.assertTrue(client_reservation_pending("client-1", settings=settings))


if __name__ == "__main__":
    unittest.main()
