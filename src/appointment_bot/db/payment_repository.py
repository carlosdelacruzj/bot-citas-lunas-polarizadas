from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from psycopg import Connection

from appointment_bot.db.common import _id_from_value


@dataclass(frozen=True, slots=True)
class PaymentState:
    order_status: str
    service_package: str
    payment_status: str | None
    amount_agreed: Decimal | None
    amount_paid: Decimal | None


class PostgresPaymentRepository:
    def lock_state(self, connection: Connection, order_id: str) -> PaymentState:
        order = connection.execute(
            """
            SELECT status, service_package
            FROM service_orders
            WHERE order_id = %s
            FOR UPDATE
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            raise ValueError(f"Service order not found: {order_id}")
        payment = connection.execute(
            """
            SELECT status, amount_agreed, amount_paid
            FROM payments
            WHERE payment_id = %s
            FOR UPDATE
            """,
            (_id_from_value("payment", order_id),),
        ).fetchone()
        return PaymentState(
            order_status=str(order["status"]),
            service_package=str(order["service_package"]),
            payment_status=str(payment["status"]) if payment is not None else None,
            amount_agreed=payment["amount_agreed"] if payment is not None else None,
            amount_paid=payment["amount_paid"] if payment is not None else None,
        )

    def save_payment(
        self,
        connection: Connection,
        *,
        order_id: str,
        status: str,
        amount_agreed: Decimal,
        amount_paid: Decimal,
        occurred_at: str,
    ) -> str:
        payment_id = _id_from_value("payment", order_id)
        paid_at = occurred_at if status == "paid" else None
        connection.execute(
            """
            INSERT INTO payments (
                payment_id, order_id, status, amount_agreed, amount_paid,
                currency, paid_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'PEN', %s, %s, %s)
            ON CONFLICT(payment_id) DO UPDATE SET
                status = excluded.status,
                amount_agreed = excluded.amount_agreed,
                amount_paid = excluded.amount_paid,
                paid_at = excluded.paid_at,
                updated_at = excluded.updated_at
            """,
            (
                payment_id,
                order_id,
                status,
                amount_agreed,
                amount_paid,
                paid_at,
                occurred_at,
                occurred_at,
            ),
        )
        return payment_id

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
    ) -> None:
        if amount <= 0:
            return
        connection.execute(
            """
            INSERT INTO payment_receipts (
                receipt_id, payment_id, order_id, amount, received_at,
                source, actor, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                _id_from_value(
                    "receipt",
                    f"{order_id}:{source}:{received_at}:{amount}",
                ),
                payment_id,
                order_id,
                amount,
                received_at,
                source,
                actor,
                received_at,
            ),
        )

    def mark_order_paid(
        self,
        connection: Connection,
        *,
        order_id: str,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            UPDATE service_orders
            SET status = 'paid',
                charge_required = true,
                closure_reason = 'completed_by_us',
                closed_at = COALESCE(closed_at, %s),
                updated_at = %s
            WHERE order_id = %s
            """,
            (occurred_at, occurred_at, order_id),
        )
