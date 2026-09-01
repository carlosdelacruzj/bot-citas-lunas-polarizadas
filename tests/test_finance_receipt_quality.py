from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from appointment_bot.db.common import _INITIALIZED_URLS, init_database
from appointment_bot.db.finance import finance_data_quality, finance_month_summary
from appointment_bot.db.monthly_dashboard_v2 import monthly_dashboard_summary_v2
from appointment_bot.db.orders import create_service_order
from tests.helpers import database_connection, make_settings


class FinanceReceiptQualityTests(unittest.TestCase):
    def test_fresh_database_reports_native_receipt_dates_as_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            init_database(settings)
            order = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, status, amount_agreed, amount_paid,
                        currency, paid_at, created_at, updated_at
                    ) VALUES (
                        'payment-exact', %s, 'paid', 50, 50, 'PEN',
                        '2026-08-31T14:48:00-05:00',
                        '2026-08-31T14:48:00-05:00',
                        '2026-08-31T14:48:00-05:00'
                    )
                    """,
                    (order.order_id,),
                )
                connection.execute(
                    """
                    INSERT INTO payment_receipts (
                        receipt_id, payment_id, order_id, amount, received_at,
                        source, actor, created_at
                    ) VALUES (
                        'receipt-exact', 'payment-exact', %s, 50,
                        '2026-08-31T14:48:00-05:00', 'payment_complete',
                        'test', '2026-08-31T14:48:00-05:00'
                    )
                    """,
                    (order.order_id,),
                )

            summary = finance_month_summary(date(2026, 8, 1), date(2026, 9, 1), settings=settings)
            quality = finance_data_quality(
                date(2026, 8, 1),
                date(2026, 9, 1),
                settings=settings,
            )["receipt_date_quality"]
            monthly = monthly_dashboard_summary_v2(
                date(2026, 8, 1),
                date(2026, 9, 1),
                date(2026, 7, 1),
                settings=settings,
            )

            self.assertEqual(summary["revenue_collected"], 50.0)
            self.assertEqual(summary["receipt_date_quality"], quality)
            self.assertEqual(quality["status"], "exact")
            self.assertTrue(quality["comparison_conclusive"])
            self.assertIsNone(quality["exact_since"])
            self.assertEqual(quality["exact_receipt_count"], 1)
            self.assertEqual(quality["inferred_receipt_count"], 0)
            self.assertTrue(
                monthly["period_metrics"]["receipt_date_quality"]["comparison_conclusive"]
            )

    def test_isolated_schema_70_restore_backfills_inferred_dates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            init_database(settings)
            orders = [
                create_service_order(
                    document_number=document_number,
                    password="secret",
                    settings=settings,
                )
                for document_number in ("12345678", "87654321")
            ]
            paid_at = datetime(2026, 8, 15, 16, 30, tzinfo=UTC)
            pending_updated_at = datetime(2026, 8, 20, 20, 0, tzinfo=UTC)
            with database_connection(settings) as connection:
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, status, amount_agreed, amount_paid,
                        currency, paid_at, created_at, updated_at
                    ) VALUES
                        ('legacy-paid', %s, 'paid', 50, 50, 'PEN', %s, %s, %s),
                        ('legacy-partial', %s, 'pending', 50, 20, 'PEN', NULL, %s, %s)
                    """,
                    (
                        orders[0].order_id,
                        paid_at,
                        paid_at,
                        paid_at,
                        orders[1].order_id,
                        pending_updated_at,
                        pending_updated_at,
                    ),
                )
                connection.execute("DROP TABLE payment_receipts")
                connection.execute(
                    "ALTER TABLE payments DROP CONSTRAINT uq_payments_payment_order"
                )
                connection.execute(
                    """
                    ALTER TABLE service_orders
                    DROP CONSTRAINT ck_service_orders_integral_terms,
                    DROP COLUMN service_package CASCADE,
                    DROP COLUMN official_fee_amount CASCADE,
                    DROP COLUMN initial_payment_amount CASCADE
                    """
                )
                connection.execute("UPDATE schema_version SET version = 70 WHERE id = 1")
            _INITIALIZED_URLS.discard(settings.database_url)

            init_database(settings)

            with database_connection(settings) as connection:
                receipts = connection.execute(
                    """
                    SELECT payment_id, amount, received_at, source, created_at
                    FROM payment_receipts
                    ORDER BY payment_id
                    """
                ).fetchall()
                version = connection.execute(
                    "SELECT version FROM schema_version WHERE id = 1"
                ).fetchone()["version"]
            quality = finance_data_quality(
                date(2026, 8, 1),
                date(2026, 9, 1),
                settings=settings,
            )["receipt_date_quality"]

            self.assertEqual(version, 74)
            self.assertEqual(len(receipts), 2)
            self.assertEqual({row["source"] for row in receipts}, {"historical_backfill"})
            self.assertEqual(sum((row["amount"] for row in receipts), Decimal("0")), Decimal("70"))
            self.assertEqual(
                {row["payment_id"]: row["received_at"] for row in receipts},
                {"legacy-paid": paid_at, "legacy-partial": pending_updated_at},
            )
            self.assertEqual(len({row["created_at"] for row in receipts}), 1)
            self.assertEqual(quality["status"], "inferred")
            self.assertFalse(quality["comparison_conclusive"])
            self.assertEqual(quality["inferred_payment_count"], 2)
            self.assertEqual(quality["inferred_receipt_count"], 2)
            self.assertEqual(quality["inferred_amount"], 70.0)
            self.assertIsNotNone(quality["exact_since"])


if __name__ == "__main__":
    unittest.main()
