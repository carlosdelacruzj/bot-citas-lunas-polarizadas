from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appointment_bot.services.database_migrations import SCHEMA_VERSION
from appointment_bot.services.database_models import RunRecord
from appointment_bot.services.postgres_database import (
    claim_service_order,
    cleanup_expired_service_order_claims,
    create_run_record,
    create_service_order,
    get_run,
    get_worker_state,
    init_database,
    list_runs,
    list_service_order_summaries,
)
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
                    (row["table_name"], row["column_name"])
                    for row in connection.execute(
                        """
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                        """
                    )
                }
                tables = {
                    row["table_name"]
                    for row in connection.execute(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = current_schema()
                        """
                    )
                }
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn(("worker_state", "owner_token"), columns)
            self.assertIn(("worker_state", "current_order_id"), columns)
            self.assertNotIn(("service_orders", "active"), columns)
            self.assertNotIn(("portal_accounts", "provider"), columns)
            self.assertNotIn(("applicants", "document_type"), columns)
            self.assertNotIn("reservation_rules", tables)
            self.assertIsNone(get_worker_state(settings).owner_token)

    def test_expired_order_claims_are_cleaned_and_reclaimable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            self.assertTrue(
                claim_service_order(
                    result.order_id,
                    owner_token="expired-owner",
                    lease_seconds=60,
                    settings=settings,
                )
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET lease_expires_at = CURRENT_TIMESTAMP - "
                    "INTERVAL '1 second' WHERE order_id = %s",
                    (result.order_id,),
                )

            self.assertEqual(cleanup_expired_service_order_claims(settings), 1)
            self.assertTrue(
                claim_service_order(
                    result.order_id,
                    owner_token="new-owner",
                    lease_seconds=60,
                    settings=settings,
                )
            )

    def test_public_service_order_summary_does_not_expose_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            create_service_order(
                document_number="12345678",
                password="secret",
                priority=10,
                applicant_name="Test",
                settings=settings,
            )

            summaries = list_service_order_summaries(settings)

            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0].document_number_masked, "12***8")
            self.assertFalse(hasattr(summaries[0], "password"))

    def test_run_listing_and_detail_are_public_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            create_run_record(
                settings,
                RunRecord(
                    run_id="run-1",
                    order_id=None,
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
