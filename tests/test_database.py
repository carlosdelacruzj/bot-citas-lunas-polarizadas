from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from appointment_bot.core.models import RunRecord
from appointment_bot.db.common import init_database
from appointment_bot.db.migrations import SCHEMA_VERSION
from appointment_bot.db.orders import (
    claim_service_order,
    cleanup_expired_service_order_claims,
    close_service_order,
    create_service_order,
    get_order_program_listing,
    list_service_order_summaries,
    mark_payment_paid,
    mark_service_order_no_charge,
    record_order_program_listing,
)
from appointment_bot.db.runs import create_run_record, get_run, list_runs
from appointment_bot.db.worker_state import get_worker_state
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
            self.assertIn(("service_orders", "minimum_date"), columns)
            self.assertIn(("service_orders", "allowed_weekdays"), columns)
            self.assertIn(("service_orders", "closure_reason"), columns)
            self.assertIn(("service_orders", "closure_note"), columns)
            self.assertIn(("service_orders", "closed_at"), columns)
            self.assertIn(("order_state", "program_listing"), columns)
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
                require_preflight=False,
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
            self.assertEqual(summaries[0].document_number, "12345678")
            self.assertEqual(summaries[0].document_number_masked, "12***8")
            self.assertFalse(hasattr(summaries[0], "password"))

    def test_no_charge_clears_pending_payment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                applicant_name="Test",
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = %s",
                    (result.order_id,),
                )
            mark_payment_paid(
                result.order_id,
                amount_paid=40,
                amount_agreed=40,
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    UPDATE payments
                    SET status = 'pending', amount_paid = NULL, paid_at = NULL
                    WHERE order_id = %s
                    """,
                    (result.order_id,),
                )

            mark_service_order_no_charge(result.order_id, settings=settings)

            summary = list_service_order_summaries(settings)[0]
            self.assertFalse(summary.charge_required)
            self.assertIsNone(summary.payment_status)
            self.assertIsNone(summary.amount_agreed)

    def test_close_order_with_no_charge_reason_clears_pending_payment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                applicant_name="Test",
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = %s",
                    (result.order_id,),
                )
            mark_payment_paid(
                result.order_id,
                amount_paid=40,
                amount_agreed=40,
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    UPDATE payments
                    SET status = 'pending', amount_paid = NULL, paid_at = NULL
                    WHERE order_id = %s
                    """,
                    (result.order_id,),
                )

            close_service_order(
                result.order_id,
                closure_reason="external_slot",
                closure_note="Lo consiguio por tercero",
                settings=settings,
            )

            summary = list_service_order_summaries(settings)[0]
            self.assertEqual(summary.status, "archived")
            self.assertFalse(summary.charge_required)
            self.assertEqual(summary.closure_reason, "external_slot")
            self.assertEqual(summary.closure_note, "Lo consiguio por tercero")
            self.assertIsNotNone(summary.closed_at)
            self.assertIsNone(summary.payment_status)

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

    def test_program_listing_change_detection_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            details = {
                "program_count": 3,
                "pending_count": 1,
                "decision": "single_pending_selected",
                "rows": [
                    {"expediente": "1", "placa": "ABC123", "status": "PENDIENTE"},
                    {"expediente": "2", "placa": "XYZ999", "status": "ATENDIDO"},
                ],
            }

            self.assertTrue(
                record_order_program_listing(result.order_id, details, settings=settings)
            )
            self.assertFalse(
                record_order_program_listing(result.order_id, details, settings=settings)
            )
            stored = get_order_program_listing(result.order_id, settings=settings)

            self.assertIsNotNone(stored)
            self.assertEqual(stored["details"]["pending_count"], 1)


if __name__ == "__main__":
    unittest.main()
