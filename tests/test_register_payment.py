from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from appointment_bot.db.payment_repository import PaymentState
from appointment_bot.services.application.create_service_order import create_service_order
from appointment_bot.services.application.register_payment import (
    RegisterPayment,
    RegisterPaymentRequest,
)
from tests.helpers import database_connection, make_settings


class FakePaymentRepository:
    def __init__(self, state: PaymentState) -> None:
        self.state = state
        self.calls: list[tuple[str, object, dict[str, Any]]] = []

    def lock_state(self, connection, order_id: str) -> PaymentState:
        self.calls.append(("lock_state", connection, {"order_id": order_id}))
        return self.state

    def save_payment(self, connection, **values) -> str:
        self.calls.append(("save_payment", connection, values))
        return "payment-order-1"

    def record_receipt(self, connection, **values) -> None:
        self.calls.append(("record_receipt", connection, values))

    def mark_order_paid(self, connection, **values) -> None:
        self.calls.append(("mark_order_paid", connection, values))


class RegisterPaymentUseCaseTests(unittest.TestCase):
    def test_partial_payment_stays_in_one_transaction_without_post_payment_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            connection = object()
            repository = FakePaymentRepository(
                PaymentState(
                    order_status="reserved_payment_pending",
                    service_package="standard",
                    payment_status="pending",
                    amount_agreed=Decimal("50.00"),
                    amount_paid=Decimal("10.00"),
                )
            )
            observed: dict[str, Any] = {"enqueued": False}

            @contextmanager
            def unit_of_work(received_settings, connection_override):
                observed["uow"] = (received_settings, connection_override)
                yield connection

            def enqueue(*args, **kwargs):
                observed["enqueued"] = True

            def audit(received_connection, **values):
                observed["audit"] = (received_connection, values)
                return "audit-partial"

            use_case = RegisterPayment(
                repository=repository,
                unit_of_work_factory=unit_of_work,
                post_payment_enqueuer=enqueue,
                audit_recorder=audit,
                clock=lambda: "2026-09-01T12:00:00.000000+00:00",
            )

            audit_id = use_case.execute(
                RegisterPaymentRequest(
                    order_id="order-1",
                    amount_paid=20,
                    complete=False,
                    actor="operator-1",
                ),
                settings=settings,
            )

            self.assertEqual(audit_id, "audit-partial")
            self.assertEqual(observed["uow"], (settings, None))
            self.assertFalse(observed["enqueued"])
            self.assertEqual(
                [call[0] for call in repository.calls],
                ["lock_state", "save_payment", "record_receipt"],
            )
            self.assertTrue(all(call[1] is connection for call in repository.calls))
            saved = repository.calls[1][2]
            self.assertEqual(saved["status"], "pending")
            self.assertEqual(saved["amount_agreed"], Decimal("50.00"))
            self.assertEqual(saved["amount_paid"], Decimal("20.00"))
            receipt = repository.calls[2][2]
            self.assertEqual(receipt["amount"], Decimal("10.00"))
            self.assertEqual(receipt["source"], "payment_partial")
            self.assertIs(observed["audit"][0], connection)
            self.assertEqual(observed["audit"][1]["action"], "payment_partial")

    def test_complete_payment_rolls_back_when_post_payment_enqueue_fails(self) -> None:
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

            def fail_enqueue(*args, **kwargs):
                raise RuntimeError("forced post-payment enqueue failure")

            use_case = RegisterPayment(post_payment_enqueuer=fail_enqueue)
            with self.assertRaisesRegex(RuntimeError, "forced post-payment"):
                use_case.execute(
                    RegisterPaymentRequest(
                        order_id=result.order_id,
                        amount_paid=50,
                        amount_agreed=50,
                        actor="operator-1",
                    ),
                    settings=settings,
                )

            with database_connection(settings) as connection:
                order = connection.execute(
                    "SELECT status FROM service_orders WHERE order_id = %s",
                    (result.order_id,),
                ).fetchone()
                counts = {
                    table: connection.execute(
                        f"SELECT COUNT(*) AS total FROM {table} WHERE order_id = %s",
                        (result.order_id,),
                    ).fetchone()["total"]
                    for table in (
                        "payments",
                        "payment_receipts",
                        "whatsapp_automation_jobs",
                    )
                }
                audit_count = connection.execute(
                    "SELECT COUNT(*) AS total FROM remote_control_audit WHERE target_id = %s",
                    (result.order_id,),
                ).fetchone()["total"]

            self.assertEqual(order["status"], "reserved_payment_pending")
            self.assertEqual(counts, {table: 0 for table in counts})
            self.assertEqual(audit_count, 0)


if __name__ == "__main__":
    unittest.main()
