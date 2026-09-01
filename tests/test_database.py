from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from psycopg.errors import CheckViolation, ForeignKeyViolation, RaiseException

from appointment_bot.core.models import RunRecord
from appointment_bot.db.common import _INITIALIZED_URLS, init_database
from appointment_bot.db.migrations import SCHEMA_VERSION
from appointment_bot.db.orders import (
    claim_service_order,
    cleanup_expired_service_order_claims,
    close_service_order,
    get_order_program_listing,
    list_service_order_summaries,
    mark_order_done,
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
from appointment_bot.services.application.create_service_order import create_service_order
from appointment_bot.services.application.register_payment import (
    mark_payment_paid,
    record_partial_payment,
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

    def test_schema_72_migrates_integral_and_receipt_constraints_to_74(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            init_database(settings)
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            integral_result = create_service_order(
                document_number="87654321",
                password="secret",
                service_package="integral",
                reservation_price=Decimal("160.00"),
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = %s",
                    (result.order_id,),
                )
            record_partial_payment(
                result.order_id,
                amount_paid=20,
                amount_agreed=50,
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "DROP TRIGGER trg_payment_receipts_validate_insert "
                    "ON payment_receipts"
                )
                connection.execute(
                    "DROP TRIGGER trg_payment_receipts_immutable ON payment_receipts"
                )
                connection.execute(
                    "DROP INDEX idx_payment_receipts_correction_original"
                )
                connection.execute("DROP INDEX idx_payment_receipts_payment_order")
                connection.execute("DROP INDEX idx_payment_receipts_order_received")
                connection.execute(
                    """
                    ALTER TABLE payment_receipts
                    DROP CONSTRAINT fk_payment_receipts_correction_original,
                    DROP CONSTRAINT fk_payment_receipts_payment_order,
                    DROP CONSTRAINT uq_payment_receipts_identity_payment_order,
                    DROP CONSTRAINT ck_payment_receipts_movement,
                    DROP COLUMN corrects_receipt_id,
                    DROP COLUMN correction_reason,
                    ADD CONSTRAINT payment_receipts_payment_id_fkey
                        FOREIGN KEY (payment_id) REFERENCES payments(payment_id)
                        ON DELETE CASCADE,
                    ADD CONSTRAINT payment_receipts_order_id_fkey
                        FOREIGN KEY (order_id) REFERENCES service_orders(order_id)
                        ON DELETE CASCADE,
                    ADD CONSTRAINT payment_receipts_amount_check CHECK (amount > 0)
                    """
                )
                connection.execute(
                    "ALTER TABLE payments DROP CONSTRAINT uq_payments_payment_order"
                )
                connection.execute(
                    "ALTER TABLE service_orders "
                    "DROP CONSTRAINT ck_service_orders_integral_terms"
                )
                connection.execute(
                    """
                    UPDATE service_orders
                    SET service_type = 'custom', status = 'paid'
                    WHERE order_id = %s
                    """,
                    (integral_result.order_id,),
                )
                connection.execute("UPDATE schema_version SET version = 72 WHERE id = 1")
            _INITIALIZED_URLS.discard(settings.database_url)

            init_database(settings)

            with database_connection(settings) as connection:
                version = connection.execute(
                    "SELECT version FROM schema_version WHERE id = 1"
                ).fetchone()["version"]
                constraints = {
                    row["conname"]: bool(row["convalidated"])
                    for row in connection.execute(
                        """
                        SELECT conname, convalidated
                        FROM pg_constraint
                        WHERE connamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = current_schema()
                        )
                        """
                    )
                }
                indexes = {
                    row["indexname"]
                    for row in connection.execute(
                        "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
                    )
                }
                triggers = {
                    row["tgname"]
                    for row in connection.execute(
                        """
                        SELECT trigger.tgname
                        FROM pg_trigger trigger
                        JOIN pg_class relation ON relation.oid = trigger.tgrelid
                        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
                        WHERE namespace.nspname = current_schema()
                          AND relation.relname = 'payment_receipts'
                          AND NOT trigger.tgisinternal
                        """
                    )
                }
                columns = {
                    row["column_name"]
                    for row in connection.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'payment_receipts'
                        """
                    )
                }
                migrated_receipt = connection.execute(
                    """
                    SELECT amount, corrects_receipt_id, correction_reason
                    FROM payment_receipts WHERE order_id = %s
                    """,
                    (result.order_id,),
                ).fetchone()
                migrated_integral = connection.execute(
                    "SELECT service_type FROM service_orders WHERE order_id = %s",
                    (integral_result.order_id,),
                ).fetchone()
            self.assertEqual(version, 74)
            for constraint_name in (
                "ck_service_orders_integral_terms",
                "uq_payments_payment_order",
                "uq_payment_receipts_identity_payment_order",
                "fk_payment_receipts_payment_order",
                "fk_payment_receipts_correction_original",
                "ck_payment_receipts_movement",
            ):
                self.assertTrue(constraints.get(constraint_name), constraint_name)
            for index_name in (
                "idx_payment_receipts_received",
                "idx_payment_receipts_order_received",
                "idx_payment_receipts_payment_order",
                "idx_payment_receipts_correction_original",
            ):
                self.assertIn(index_name, indexes)
            self.assertEqual(
                triggers,
                {
                    "trg_payment_receipts_validate_insert",
                    "trg_payment_receipts_immutable",
                },
            )
            self.assertIn("corrects_receipt_id", columns)
            self.assertIn("correction_reason", columns)
            self.assertEqual(migrated_receipt["amount"], Decimal("20.00"))
            self.assertIsNone(migrated_receipt["corrects_receipt_id"])
            self.assertIsNone(migrated_receipt["correction_reason"])
            self.assertEqual(migrated_integral["service_type"], "standard")

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

    def test_payment_receipts_are_idempotent_across_partial_and_full_payment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = %s",
                    (result.order_id,),
                )

            record_partial_payment(
                result.order_id,
                amount_paid=20,
                amount_agreed=50,
                settings=settings,
            )
            record_partial_payment(
                result.order_id,
                amount_paid=20,
                amount_agreed=50,
                settings=settings,
            )
            with self.assertRaisesRegex(ValueError, "cannot reduce"):
                record_partial_payment(
                    result.order_id,
                    amount_paid=10,
                    amount_agreed=50,
                    settings=settings,
                )
            mark_payment_paid(
                result.order_id,
                amount_paid=50,
                amount_agreed=50,
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
            self.assertEqual(payment["amount_agreed"], Decimal("50.00"))
            self.assertEqual(payment["amount_paid"], Decimal("50.00"))
            self.assertEqual(receipts["count"], 2)
            self.assertEqual(receipts["amount"], Decimal("50.00"))

    def test_payment_receipts_enforce_order_ownership_and_immutable_corrections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            orders = [
                create_service_order(
                    document_number=document_number,
                    password="secret",
                    settings=settings,
                )
                for document_number in ("12345678", "87654321")
            ]
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = ANY(%s)",
                    ([order.order_id for order in orders],),
                )
            for order, amount in zip(orders, (20, 10), strict=True):
                record_partial_payment(
                    order.order_id,
                    amount_paid=amount,
                    amount_agreed=50,
                    settings=settings,
                )

            with database_connection(settings) as connection:
                first = connection.execute(
                    """
                    SELECT receipt_id, payment_id, order_id
                    FROM payment_receipts
                    WHERE order_id = %s
                    """,
                    (orders[0].order_id,),
                ).fetchone()
            with database_connection(settings) as connection:
                with self.assertRaises(ForeignKeyViolation):
                    connection.execute(
                        """
                        INSERT INTO payment_receipts (
                            receipt_id, payment_id, order_id, amount, received_at,
                            source, actor, created_at
                        ) VALUES (
                            'receipt-wrong-order', %s, %s, 1, CURRENT_TIMESTAMP,
                            'payment_partial', 'test', CURRENT_TIMESTAMP
                        )
                        """,
                        (first["payment_id"], orders[1].order_id),
                    )
                connection.rollback()
            for statement in (
                "UPDATE payment_receipts SET amount = 19 WHERE receipt_id = %s",
                "DELETE FROM payment_receipts WHERE receipt_id = %s",
            ):
                with self.subTest(statement=statement), database_connection(settings) as connection:
                    with self.assertRaises(RaiseException):
                        connection.execute(statement, (first["receipt_id"],))
                    connection.rollback()
            with database_connection(settings) as connection:
                with self.assertRaises(ForeignKeyViolation):
                    connection.execute(
                        "DELETE FROM payments WHERE payment_id = %s",
                        (first["payment_id"],),
                    )
                connection.rollback()

            with database_connection(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO payment_receipts (
                        receipt_id, payment_id, order_id, amount, received_at,
                        source, actor, corrects_receipt_id, correction_reason, created_at
                    ) VALUES (
                        'receipt-correction-1', %s, %s, -5, CURRENT_TIMESTAMP,
                        'payment_correction', 'finance-owner', %s,
                        'Corrección explícita de importe', CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        first["payment_id"],
                        first["order_id"],
                        first["receipt_id"],
                    ),
                )
            with database_connection(settings) as connection:
                with self.assertRaises(RaiseException):
                    connection.execute(
                        """
                        INSERT INTO payment_receipts (
                            receipt_id, payment_id, order_id, amount, received_at,
                            source, actor, corrects_receipt_id,
                            correction_reason, created_at
                        ) VALUES (
                            'receipt-correction-too-large', %s, %s, -16,
                            CURRENT_TIMESTAMP, 'payment_correction', 'finance-owner',
                            %s, 'Excede el recibo original', CURRENT_TIMESTAMP
                        )
                        """,
                        (
                            first["payment_id"],
                            first["order_id"],
                            first["receipt_id"],
                        ),
                    )
                connection.rollback()
            with database_connection(settings) as connection:
                total = connection.execute(
                    """
                    SELECT COUNT(*) AS count, SUM(amount) AS amount
                    FROM payment_receipts WHERE order_id = %s
                    """,
                    (orders[0].order_id,),
                ).fetchone()
            self.assertEqual(total["count"], 2)
            self.assertEqual(total["amount"], Decimal("15.00"))

    def test_integral_creation_is_idempotent_and_records_fixed_amounts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            for _ in range(2):
                result = create_service_order(
                    document_number="12345678",
                    password="secret",
                    service_package="integral",
                    reservation_price=Decimal("160.00"),
                    actor="api:sha256:testactor",
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
                    SELECT COUNT(*) AS count, SUM(amount) AS amount, MAX(actor) AS actor
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
            self.assertEqual(receipt["actor"], "api:sha256:testactor")
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
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, status, amount_agreed, currency,
                        created_at, updated_at
                    ) VALUES (
                        'payment-no-charge-action', %s, 'pending', 50, 'PEN',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """,
                    (result.order_id,),
                )
            mark_service_order_no_charge(result.order_id, settings=settings)

            summary = list_service_order_summaries(settings)[0]
            self.assertFalse(summary.charge_required)
            self.assertIsNone(summary.payment_status)
            self.assertIsNone(summary.amount_agreed)

    def test_no_charge_rejects_orders_with_immutable_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    "UPDATE service_orders SET status = 'reserved_payment_pending' "
                    "WHERE order_id = %s",
                    (result.order_id,),
                )
            record_partial_payment(
                result.order_id,
                amount_paid=20,
                amount_agreed=50,
                settings=settings,
            )

            with self.assertRaisesRegex(ValueError, "recibos de caja inmutables"):
                mark_service_order_no_charge(result.order_id, settings=settings)
            with self.assertRaisesRegex(ValueError, "recibos de caja inmutables"):
                close_service_order(
                    result.order_id,
                    closure_reason="client_withdrew",
                    settings=settings,
                )

            with database_connection(settings) as connection:
                row = connection.execute(
                    """
                    SELECT so.status AS order_status, so.charge_required,
                           p.status AS payment_status, p.amount_paid,
                           COUNT(receipt.receipt_id) AS receipt_count
                    FROM service_orders so
                    JOIN payments p ON p.order_id = so.order_id
                    JOIN payment_receipts receipt ON receipt.order_id = so.order_id
                    WHERE so.order_id = %s
                    GROUP BY so.status, so.charge_required, p.status, p.amount_paid
                    """,
                    (result.order_id,),
                ).fetchone()
            self.assertEqual(row["order_status"], "reserved_payment_pending")
            self.assertTrue(row["charge_required"])
            self.assertEqual(row["payment_status"], "pending")
            self.assertEqual(row["amount_paid"], Decimal("20.00"))
            self.assertEqual(row["receipt_count"], 1)

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
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, status, amount_agreed, currency,
                        created_at, updated_at
                    ) VALUES (
                        'payment-no-charge-close', %s, 'pending', 50, 'PEN',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
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
