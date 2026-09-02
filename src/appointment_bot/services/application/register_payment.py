from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from psycopg import Connection

from appointment_bot.config import Settings, load_settings
from appointment_bot.core.service_packages import validate_integral_payment_totals
from appointment_bot.db.payment_repository import (
    PaymentState,
    PostgresPaymentRepository,
)
from appointment_bot.db.remote_control_audit import (
    record_remote_control_audit_in_connection,
)
from appointment_bot.db.unit_of_work import postgres_unit_of_work
from appointment_bot.db.whatsapp_automation import enqueue_whatsapp_automation_job

UnitOfWorkFactory = Callable[
    [Settings, Connection | None],
    AbstractContextManager[Connection],
]


class PaymentRepository(Protocol):
    def lock_state(self, connection: Connection, order_id: str) -> PaymentState: ...

    def save_payment(
        self,
        connection: Connection,
        *,
        order_id: str,
        status: str,
        amount_agreed: Decimal,
        amount_paid: Decimal,
        occurred_at: str,
    ) -> str: ...

    def record_receipt(
        self,
        connection: Connection,
        *,
        payment_id: str,
        order_id: str,
        amount: Decimal,
        received_at: str,
        source: str,
        actor: str,
    ) -> None: ...

    def mark_order_paid(
        self,
        connection: Connection,
        *,
        order_id: str,
        occurred_at: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RegisterPaymentRequest:
    order_id: str
    amount_paid: str | float | int | Decimal
    amount_agreed: str | float | int | Decimal | None = None
    actor: str = "internal"
    complete: bool = True
    allow_difference: bool = False
    difference_reason: str | None = None
    expected_payment_status: str | None = None
    expected_amount_agreed: str | float | int | Decimal | None = None
    expected_amount_paid: str | float | int | Decimal | None = None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class RegisterPayment:
    def __init__(
        self,
        *,
        repository: PaymentRepository | None = None,
        unit_of_work_factory: UnitOfWorkFactory = postgres_unit_of_work,
        post_payment_enqueuer=enqueue_whatsapp_automation_job,
        audit_recorder=record_remote_control_audit_in_connection,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository or PostgresPaymentRepository()
        self._unit_of_work_factory = unit_of_work_factory
        self._post_payment_enqueuer = post_payment_enqueuer
        self._audit_recorder = audit_recorder
        self._clock = clock or _utc_now

    def execute(
        self,
        request: RegisterPaymentRequest,
        *,
        settings: Settings | None = None,
        connection_override: Connection | None = None,
    ) -> str:
        paid = _decimal_or_none(request.amount_paid)
        agreed = _decimal_or_none(request.amount_agreed)
        if paid is None or paid <= 0:
            raise ValueError("amount_paid must be a valid positive amount.")
        normalized_reason = (request.difference_reason or "").strip()
        if request.complete:
            if agreed is None:
                agreed = paid
            if agreed < 0:
                raise ValueError("amount_agreed must be a valid non-negative amount.")
            if paid < agreed and (not request.allow_difference or not normalized_reason):
                raise ValueError(
                    "A lower final payment requires allow_difference=true and difference_reason."
                )

        resolved_settings = settings or load_settings(require_login=False)
        occurred_at = self._clock()
        with self._unit_of_work_factory(resolved_settings, connection_override) as connection:
            current = self._repository.lock_state(connection, request.order_id)
            _validate_payment_snapshot(current, request)
            if current.order_status != "reserved_payment_pending":
                raise ValueError("Service order is no longer pending payment.")
            if current.payment_status not in {None, "pending"}:
                raise ValueError("Payment is no longer pending.")

            effective_agreed = agreed if agreed is not None else current.amount_agreed
            if not request.complete and (effective_agreed is None or effective_agreed <= 0):
                raise ValueError("amount_agreed must be a valid positive amount.")
            if effective_agreed is None:
                raise ValueError("amount_agreed must be a valid amount.")
            if not request.complete and paid >= effective_agreed:
                raise ValueError(
                    "A partial payment must remain below amount_agreed; use payment/paid instead."
                )

            previous_paid = current.amount_paid or Decimal("0")
            validate_integral_payment_totals(
                current.service_package,
                amount_agreed=effective_agreed,
                amount_paid=paid,
                complete=request.complete,
            )
            if paid < previous_paid:
                payment_kind = "complete" if request.complete else "partial"
                raise ValueError(
                    f"A {payment_kind} payment cannot reduce the accumulated amount paid."
                )

            status = "paid" if request.complete else "pending"
            source = "payment_complete" if request.complete else "payment_partial"
            payment_id = self._repository.save_payment(
                connection,
                order_id=request.order_id,
                status=status,
                amount_agreed=effective_agreed,
                amount_paid=paid,
                occurred_at=occurred_at,
            )
            self._repository.record_receipt(
                connection,
                payment_id=payment_id,
                order_id=request.order_id,
                amount=paid - previous_paid,
                received_at=occurred_at,
                source=source,
                actor=request.actor,
            )

            if request.complete:
                self._repository.mark_order_paid(
                    connection,
                    order_id=request.order_id,
                    occurred_at=occurred_at,
                )
                self._post_payment_enqueuer(
                    request.order_id,
                    "post_payment_followup",
                    settings=resolved_settings,
                    _connection_override=connection,
                )
                detail = (
                    f"amount_agreed={effective_agreed}; amount_paid={paid}; "
                    f"difference_allowed={str(paid < effective_agreed).lower()}; "
                    f"difference_reason={normalized_reason or 'none'}; "
                    "post_payment=queued"
                )
                action = "payment_paid"
            else:
                detail = (
                    f"amount_agreed={effective_agreed}; amount_paid={paid}; "
                    "payment_status=pending; post_payment=not_queued"
                )
                action = "payment_partial"

            return self._audit_recorder(
                connection,
                actor=request.actor,
                action=action,
                status="applied",
                target_type="service_order",
                target_id=request.order_id,
                detail=detail,
            )


_DEFAULT_USE_CASE = RegisterPayment()


def mark_payment_paid(
    order_id: str,
    *,
    amount_paid: str | float | int,
    amount_agreed: str | float | int | None = None,
    actor: str = "internal",
    allow_difference: bool = False,
    difference_reason: str | None = None,
    expected_payment_status: str | None = None,
    expected_amount_agreed: str | float | int | None = None,
    expected_amount_paid: str | float | int | None = None,
    settings: Settings | None = None,
) -> str:
    return _DEFAULT_USE_CASE.execute(
        RegisterPaymentRequest(
            order_id=order_id,
            amount_paid=amount_paid,
            amount_agreed=amount_agreed,
            actor=actor,
            complete=True,
            allow_difference=allow_difference,
            difference_reason=difference_reason,
            expected_payment_status=expected_payment_status,
            expected_amount_agreed=expected_amount_agreed,
            expected_amount_paid=expected_amount_paid,
        ),
        settings=settings,
    )


def record_partial_payment(
    order_id: str,
    *,
    amount_paid: str | float | int,
    amount_agreed: str | float | int | None = None,
    actor: str = "internal",
    expected_payment_status: str | None = None,
    expected_amount_agreed: str | float | int | None = None,
    expected_amount_paid: str | float | int | None = None,
    settings: Settings | None = None,
) -> str:
    return _DEFAULT_USE_CASE.execute(
        RegisterPaymentRequest(
            order_id=order_id,
            amount_paid=amount_paid,
            amount_agreed=amount_agreed,
            actor=actor,
            complete=False,
            expected_payment_status=expected_payment_status,
            expected_amount_agreed=expected_amount_agreed,
            expected_amount_paid=expected_amount_paid,
        ),
        settings=settings,
    )


def _validate_payment_snapshot(
    current: PaymentState,
    request: RegisterPaymentRequest,
) -> None:
    if (
        request.expected_payment_status is not None
        and current.payment_status != request.expected_payment_status
    ):
        raise ValueError("Payment changed since it was reviewed.")
    for field, expected in (
        ("amount_agreed", request.expected_amount_agreed),
        ("amount_paid", request.expected_amount_paid),
    ):
        if expected is None:
            continue
        normalized_expected = _decimal_or_none(expected)
        if normalized_expected is None:
            raise ValueError("Expected payment amounts must be valid numbers.")
        current_value = getattr(current, field)
        if field == "amount_paid" and current_value is None:
            current_value = Decimal("0")
        if current_value != normalized_expected:
            raise ValueError("Payment amounts changed since they were reviewed.")


def _decimal_or_none(
    value: str | float | int | Decimal | None,
) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None
