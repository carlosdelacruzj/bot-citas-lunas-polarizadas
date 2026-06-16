from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appointment_bot.services.database import (
    SCHEMA_VERSION,
    add_client,
    create_run_record,
    get_run,
    get_worker_state,
    init_database,
    list_client_summaries,
    list_runs,
    using_postgres,
)
from appointment_bot.services.database_models import RunRecord
from tests.helpers import database_connection, make_settings


class DatabaseTests(unittest.TestCase):
    def test_postgres_schema_is_initialized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))

            init_database(settings)

            with database_connection(settings) as connection:
                version = connection.execute(
                    "SELECT version FROM schema_version WHERE id = 1"
                ).fetchone()["version"]
                columns = {
                    row["column_name"]
                    for row in connection.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'worker_state'
                        """
                    )
                }
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("owner_token", columns)
            self.assertIsNone(get_worker_state(settings).owner_token)
            self.assertTrue(using_postgres(settings))

    def test_public_client_summary_does_not_expose_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            add_client("client-1", "Test", "12345678", "secret", 10, settings=settings)

            summaries = list_client_summaries(settings)

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].username_masked, "12***8")
            self.assertFalse(hasattr(summaries[0], "password"))

    def test_run_listing_and_detail_are_public_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            create_run_record(
                settings,
                RunRecord(
                    run_id="run-1",
                    client_id=None,
                    status="unavailable",
                    message="No slots",
                    exit_code=0,
                    started_at="2026-06-16T01:00:00",
                    finished_at="2026-06-16T01:00:01",
                    duration_seconds=1.0,
                    reservation_attempted=False,
                    reservation_confirmed=False,
                    details={"dni": "12345678", "sede": "LIMA"},
                    screenshot_path="C:/tmp/evidence.png",
                ),
                ["C:/tmp/evidence.png"],
            )

            runs = list_runs(settings=settings)
            detail = get_run("run-1", settings=settings)

            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].screenshot_path, "evidence.png")
            self.assertIsNotNone(detail)
            self.assertEqual(detail.screenshot_paths, ["evidence.png"])
            self.assertEqual(detail.details, {"sede": "LIMA"})


if __name__ == "__main__":
    unittest.main()
