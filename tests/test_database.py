from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from psycopg.errors import CheckViolation

from appointment_bot.core.models import RunRecord
from appointment_bot.db.common import _INITIALIZED_URLS, init_database
from appointment_bot.db.migrations import SCHEMA_VERSION
from appointment_bot.db.orders import (
    claim_service_order,
    cleanup_expired_service_order_claims,
    close_service_order,
    create_service_order,
    get_order_program_listing,
    list_service_order_summaries,
    mark_order_done,
    mark_payment_paid,
    mark_service_order_no_charge,
    record_order_program_listing,
)
from appointment_bot.db.reservations import _record_reservation_for_order
from appointment_bot.db.runs import create_run_record, get_run, list_runs
from appointment_bot.db.worker_state import (
    acquire_worker_lease,
    get_worker_state,
    release_worker_lease,
    renew_worker_lease,
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

    def test_schema_72_migrates_integral_constraint_to_73(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            init_database(settings)
            with database_connection(settings) as connection:
                connection.execute(
                    "ALTER TABLE service_orders "
                    "DROP CONSTRAINT ck_service_orders_integral_terms"
                )
                connection.execute("UPDATE schema_version SET version = 72 WHERE id = 1")
            _INITIALIZED_URLS.discard(settings.database_url)

            init_database(settings)

            with database_connection(settings) as connection:
                version = connection.execute(
                    "SELECT version FROM schema_version WHERE id = 1"
                ).fetchone()["version"]
                constraint = connection.execute(
                    """
                    SELECT convalidated
                    FROM pg_constraint
                    WHERE connamespace = (
                        SELECT oid FROM pg_namespace WHERE nspname = current_schema()
                    ) AND conname = 'ck_service_orders_integral_terms'
                    """
                ).fetchone()
            self.assertEqual(version, 73)
            self.assertIsNotNone(constraint)
            self.assertTrue(constraint["convalidated"])

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

    def test_worker_lease_never_has_two_database_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            init_database(settings)
            try:
                self.assertTrue(
                    acquire_worker_lease("owner-one", lease_seconds=300, settings=settings)
                )
                self.assertFalse(
                    acquire_worker_lease("owner-two", lease_seconds=300, settings=settings)
                )
                self.assertTrue(
                    renew_worker_lease("owner-one", lease_seconds=300, settings=settings)
                )
                with database_connection(settings) as connection:
                    connection.execute(
                        "UPDATE worker_state SET lease_expires_at = CURRENT_TIMESTAMP - "
                        "INTERVAL '1 second' WHERE id = 1"
                    )
                self.assertFalse(
                    renew_worker_lease("owner-one", lease_seconds=300, settings=settings)
                )
                self.assertTrue(
                    acquire_worker_lease("owner-two", lease_seconds=300, settings=settings)
                )
                release_worker_lease("owner-one", settings=settings)
                self.assertEqual(get_worker_state(settings).owner_token, "owner-two")
            finally:
                release_worker_lease("owner-one", settings=settings)
                release_worker_lease("owner-two", settings=settings)

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

    def test_integral_creation_is_idempotent_and_records_fixed_amounts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            for _ in range(2):
                result = create_service_order(
                    document_number="12345678",
                    password="secret",
                    service_package="integral",
                    reservation_price=Decimal("160.00"),
                    settings=settings,
                )

            with database_connection(settings) as connection:
                order = connection.execute(
                    """
                    SELECT charge_required, service_type, reservation_price,
                           official_fee_amount, initial_payment_amount
                    FROM service_orders
                    WHERE order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
                payment = connection.execute(
                    """
                    SELECT status, amount_agreed, amount_paid
                    FROM payments
                    WHERE order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
                receipt = connection.execute(
                    """
                    SELECT COUNT(*) AS count, SUM(amount) AS amount
                    FROM payment_receipts
                    WHERE order_id = %s AND source = 'integral_initial_payment'
                    """,
                    (result.order_id,),
                ).fetchone()
                fee = connection.execute(
                    """
                    SELECT COUNT(*) AS count, SUM(amount_pen) AS amount
                    FROM finance_entries
                    WHERE order_id = %s AND category_code = 'government_fee'
                      AND status = 'active'
                    """,
                    (result.order_id,),
                ).fetchone()

            self.assertTrue(order["charge_required"])
            self.assertEqual(order["service_type"], "standard")
            self.assertEqual(order["reservation_price"], Decimal("160.00"))
            self.assertEqual(order["official_fee_amount"], Decimal("71.40"))
            self.assertEqual(order["initial_payment_amount"], Decimal("80.00"))
            self.assertEqual(payment["status"], "pending")
            self.assertEqual(payment["amount_agreed"], Decimal("160.00"))
            self.assertEqual(payment["amount_paid"], Decimal("80.00"))
            self.assertEqual(receipt["count"], 1)
            self.assertEqual(receipt["amount"], Decimal("80.00"))
            self.assertEqual(fee["count"], 1)
            self.assertEqual(fee["amount"], Decimal("71.40"))

    def test_integral_terms_are_rejected_by_domain_and_postgres(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with self.assertRaisesRegex(ValueError, "charge_required=true"):
                create_service_order(
                    document_number="12345678",
                    password="secret",
                    charge_required=False,
                    service_package="integral",
                    reservation_price=Decimal("160.00"),
                    settings=settings,
                )
            result = create_service_order(
                document_number="87654321",
                password="secret",
                service_package="integral",
                reservation_price=Decimal("160.00"),
                settings=settings,
            )
            invalid_updates = (
                "UPDATE service_orders SET charge_required = false WHERE order_id = %s",
                "UPDATE service_orders SET reservation_price = 159 WHERE order_id = %s",
                "UPDATE service_orders SET official_fee_amount = 70 WHERE order_id = %s",
                "UPDATE service_orders SET initial_payment_amount = 79 WHERE order_id = %s",
                "UPDATE service_orders SET status = 'archived' WHERE order_id = %s",
            )
            for statement in invalid_updates:
                with self.subTest(statement=statement), database_connection(settings) as connection:
                    with self.assertRaises(CheckViolation):
                        connection.execute(statement, (result.order_id,))
                    connection.rollback()

    def test_integral_reservation_collects_only_balance_and_closes_at_160(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                service_package="integral",
                reservation_price=Decimal("160.00"),
                settings=settings,
            )
            report = SimpleNamespace(
                details={},
                run_id=None,
                reservation_confirmed=True,
                screenshot_path=None,
                screenshot_paths=[],
            )
            _record_reservation_for_order(
                result.order_id,
                report,
                confirmed=True,
                settings=settings,
            )

            summary = list_service_order_summaries(settings)[0]
            self.assertEqual(summary.status, "reserved_payment_pending")
            self.assertEqual(summary.amount_agreed, "160.00")
            self.assertEqual(summary.amount_paid, "80.00")
            with self.assertRaisesRegex(ValueError, "debe acumular S/160.00"):
                mark_payment_paid(
                    result.order_id,
                    amount_paid=150,
                    amount_agreed=160,
                    allow_difference=True,
                    difference_reason="invalid integral discount",
                    settings=settings,
                )
            with patch("appointment_bot.db.order_contacts.enqueue_whatsapp_automation_job"):
                mark_payment_paid(
                    result.order_id,
                    amount_paid=160,
                    amount_agreed=160,
                    settings=settings,
                )

            with database_connection(settings) as connection:
                payment = connection.execute(
                    """
                    SELECT status, amount_agreed, amount_paid
                    FROM payments WHERE order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
                receipts = connection.execute(
                    """
                    SELECT COUNT(*) AS count, SUM(amount) AS amount
                    FROM payment_receipts WHERE order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
            self.assertEqual(payment["status"], "paid")
            self.assertEqual(payment["amount_agreed"], Decimal("160.00"))
            self.assertEqual(payment["amount_paid"], Decimal("160.00"))
            self.assertEqual(receipts["count"], 2)
            self.assertEqual(receipts["amount"], Decimal("160.00"))

    def test_integral_correction_and_no_charge_close_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                service_package="integral",
                reservation_price=Decimal("160.00"),
                settings=settings,
            )
            with self.assertRaisesRegex(ValueError, "corrección contable auditada"):
                create_service_order(
                    document_number="12345678",
                    password="secret",
                    service_package="standard",
                    reservation_price=Decimal("50.00"),
                    settings=settings,
                )
            with self.assertRaisesRegex(ValueError, "no puede convertirse en sin cobro"):
                mark_service_order_no_charge(result.order_id, settings=settings)
            with self.assertRaisesRegex(ValueError, "no puede cerrarse sin cobro"):
                close_service_order(
                    result.order_id,
                    closure_reason="client_withdrew",
                    settings=settings,
                )
            with self.assertRaisesRegex(ValueError, "debe acumular S/160.00"):
                close_service_order(
                    result.order_id,
                    closure_reason="completed_by_us",
                    settings=settings,
                )
            with self.assertRaisesRegex(ValueError, "no puede archivarse"):
                mark_order_done(result.order_id, status="completed", settings=settings)

            close_service_order(
                result.order_id,
                closure_reason="uncollectible",
                closure_note="Saldo pendiente no recuperable",
                settings=settings,
            )
            with database_connection(settings) as connection:
                row = connection.execute(
                    """
                    SELECT so.status AS order_status, so.closure_reason,
                           p.status AS payment_status, p.amount_paid,
                           (SELECT COUNT(*) FROM payment_receipts pr
                            WHERE pr.order_id = so.order_id) AS receipt_count,
                           (SELECT COUNT(*) FROM finance_entries fe
                            WHERE fe.order_id = so.order_id
                              AND fe.category_code = 'government_fee'
                              AND fe.status = 'active') AS fee_count
                    FROM service_orders so
                    JOIN payments p ON p.order_id = so.order_id
                    WHERE so.order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
            self.assertEqual(row["order_status"], "archived")
            self.assertEqual(row["closure_reason"], "uncollectible")
            self.assertEqual(row["payment_status"], "written_off")
            self.assertEqual(row["amount_paid"], Decimal("80.00"))
            self.assertEqual(row["receipt_count"], 1)
            self.assertEqual(row["fee_count"], 1)

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
