from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from appointment_bot.core.models import RunRecord
from appointment_bot.db.reservation_repository import (
    PostgresReservationRepository,
    ReservationOrderState,
)
from appointment_bot.services.application.confirm_reservation import (
    ConfirmReservation,
    ConfirmReservationRequest,
    record_run_outcome,
)
from appointment_bot.services.application.create_service_order import create_service_order
from tests.helpers import database_connection, make_settings


class FakeReservationRepository:
    def __init__(self, order: ReservationOrderState | None) -> None:
        self.order = order
        self.calls: list[tuple[str, object, dict[str, Any]]] = []

    def get_order(self, connection, order_id: str) -> ReservationOrderState | None:
        self.calls.append(("get_order", connection, {"order_id": order_id}))
        return self.order

    def save_reservation(self, connection, **values) -> str:
        self.calls.append(("save_reservation", connection, values))
        return "reservation-order-1-run-1"

    def ensure_pending_payment(self, connection, **values) -> None:
        self.calls.append(("ensure_pending_payment", connection, values))

    def update_order_after_confirmation(self, connection, **values) -> None:
        self.calls.append(("update_order_after_confirmation", connection, values))


class FailingReservationRepository(PostgresReservationRepository):
    def ensure_pending_payment(self, connection, **values) -> None:
        super().ensure_pending_payment(connection, **values)
        raise RuntimeError("forced failure after reservation and payment")


class ConfirmReservationUseCaseTests(unittest.TestCase):
    def test_confirmed_reservation_coordinates_evidence_payment_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            connection = object()
            repository = FakeReservationRepository(
                ReservationOrderState(
                    charge_required=True,
                    reservation_price=Decimal("70.00"),
                    program_expediente="EXP-OLD",
                    program_plate=None,
                )
            )
            observed: dict[str, Any] = {}

            @contextmanager
            def unit_of_work(received_settings, connection_override):
                observed["uow"] = (received_settings, connection_override)
                yield connection

            def archive(order_id: str, values: list[object]):
                observed["archive"] = (order_id, values)
                return Path("C:/evidence/confirmed.png")

            use_case = ConfirmReservation(
                repository=repository,
                unit_of_work_factory=unit_of_work,
                evidence_archiver=archive,
                clock=lambda: "2026-09-01T22:00:00.000000+00:00",
            )
            report = SimpleNamespace(
                run_id="run-1",
                reservation_confirmed=True,
                details={
                    "fecha": "25/09/2026 09:00",
                    "sede": "LIMA",
                    "cupos": "1",
                    "program_plate": "ABC123",
                    "captcha_solution_sent": "never-persist",
                },
                screenshot_path="C:/screenshots/primary.png",
                screenshot_paths=["C:/screenshots/secondary.png"],
            )

            persisted = use_case.execute(
                ConfirmReservationRequest(order_id="order-1", report=report),
                settings=settings,
            )

            self.assertTrue(persisted)
            self.assertEqual(observed["uow"], (settings, None))
            self.assertEqual(observed["archive"][0], "order-1")
            self.assertEqual(
                observed["archive"][1],
                ["C:/screenshots/secondary.png", "C:/screenshots/primary.png"],
            )
            self.assertEqual(
                [call[0] for call in repository.calls],
                [
                    "get_order",
                    "save_reservation",
                    "ensure_pending_payment",
                    "update_order_after_confirmation",
                ],
            )
            self.assertTrue(all(call[1] is connection for call in repository.calls))
            saved = repository.calls[1][2]
            self.assertEqual(saved["status"], "confirmed")
            self.assertEqual(saved["appointment_date"], "25/09/2026")
            self.assertEqual(saved["appointment_hour"], "09:00")
            self.assertEqual(saved["program_expediente"], "EXP-OLD")
            self.assertEqual(saved["program_plate"], "ABC123")
            self.assertEqual(saved["evidence_path"], "C:\\evidence\\confirmed.png")
            self.assertNotIn("captcha_solution_sent", saved["details"])
            payment = repository.calls[2][2]
            self.assertEqual(payment["amount_agreed"], Decimal("70.00"))
            self.assertFalse(repository.calls[3][2]["no_charge"])

    def test_confirmed_no_charge_reservation_archives_without_payment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            repository = FakeReservationRepository(
                ReservationOrderState(
                    charge_required=False,
                    reservation_price=Decimal("50.00"),
                    program_expediente=None,
                    program_plate=None,
                )
            )
            use_case = ConfirmReservation(
                repository=repository,
                evidence_archiver=lambda order_id, values: None,
            )
            report = SimpleNamespace(
                run_id=None,
                reservation_confirmed=True,
                details={},
                screenshot_path=None,
                screenshot_paths=[],
            )

            use_case.execute(
                ConfirmReservationRequest(order_id="order-1", report=report),
                settings=settings,
            )

            self.assertEqual(
                [call[0] for call in repository.calls],
                ["get_order", "save_reservation", "update_order_after_confirmation"],
            )
            self.assertTrue(repository.calls[2][2]["no_charge"])

    def test_run_and_confirmation_share_one_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                reservation_price=Decimal("50.00"),
                settings=settings,
            )
            details = {"fecha": "25/09/2026", "hora": "09:00", "sede": "LIMA"}
            record = RunRecord(
                run_id="run-confirmed-1",
                order_id=result.order_id,
                status="completed",
                message="Reserva confirmada",
                exit_code=0,
                started_at="2026-09-01T22:00:00+00:00",
                finished_at="2026-09-01T22:00:01+00:00",
                duration_seconds=1.0,
                reservation_attempted=True,
                reservation_confirmed=True,
                details=details,
                screenshot_path=None,
            )
            report = SimpleNamespace(
                run_id=record.run_id,
                reservation_confirmed=True,
                details=details,
                screenshot_path=None,
                screenshot_paths=[],
            )

            record_run_outcome(
                settings,
                record,
                [],
                report=report,
                person_name="Cliente",
                include_reservation=True,
            )

            with database_connection(settings) as connection:
                row = connection.execute(
                    """
                    SELECT r.run_id, reservation.status AS reservation_status,
                           payment.status AS payment_status,
                           payment.amount_agreed, orders.status AS order_status
                    FROM runs r
                    JOIN reservations reservation
                      ON reservation.run_id = r.run_id
                     AND reservation.order_id = r.order_id
                    JOIN payments payment
                      ON payment.reservation_id = reservation.reservation_id
                     AND payment.order_id = reservation.order_id
                    JOIN service_orders orders ON orders.order_id = reservation.order_id
                    WHERE r.run_id = %s
                    """,
                    (record.run_id,),
                ).fetchone()

            self.assertEqual(row["reservation_status"], "confirmed")
            self.assertEqual(row["payment_status"], "pending")
            self.assertEqual(row["amount_agreed"], Decimal("50.00"))
            self.assertEqual(row["order_status"], "reserved_payment_pending")

    def test_confirmation_rolls_back_when_payment_persistence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="12345678",
                password="secret",
                settings=settings,
            )
            report = SimpleNamespace(
                run_id=None,
                reservation_confirmed=True,
                details={"fecha": "25/09/2026", "hora": "09:00"},
                screenshot_path=None,
                screenshot_paths=[],
            )
            use_case = ConfirmReservation(repository=FailingReservationRepository())

            with self.assertRaisesRegex(RuntimeError, "forced failure"):
                use_case.execute(
                    ConfirmReservationRequest(order_id=result.order_id, report=report),
                    settings=settings,
                )

            with database_connection(settings) as connection:
                order = connection.execute(
                    "SELECT status FROM service_orders WHERE order_id = %s",
                    (result.order_id,),
                ).fetchone()
                reservation_count = connection.execute(
                    "SELECT COUNT(*) AS total FROM reservations WHERE order_id = %s",
                    (result.order_id,),
                ).fetchone()["total"]
                payment_count = connection.execute(
                    "SELECT COUNT(*) AS total FROM payments WHERE order_id = %s",
                    (result.order_id,),
                ).fetchone()["total"]

            self.assertEqual(order["status"], "paused")
            self.assertEqual(reservation_count, 0)
            self.assertEqual(payment_count, 0)


if __name__ == "__main__":
    unittest.main()
