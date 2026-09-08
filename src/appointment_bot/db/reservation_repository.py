from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.db.common import _id_from_value


@dataclass(frozen=True, slots=True)
class ReservationOrderState:
    charge_required: bool
    reservation_price: Decimal
    program_expediente: str | None
    program_plate: str | None


class PostgresReservationRepository:
    def get_order(
        self,
        connection: Connection,
        order_id: str,
    ) -> ReservationOrderState | None:
        row = connection.execute(
            """
            SELECT charge_required, reservation_price,
                   program_expediente, program_plate
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        return ReservationOrderState(
            charge_required=bool(row["charge_required"]),
            reservation_price=row["reservation_price"],
            program_expediente=row["program_expediente"],
            program_plate=row["program_plate"],
        )

    def save_reservation(
        self,
        connection: Connection,
        *,
        order_id: str,
        run_id: str | None,
        status: str,
        site: str | None,
        appointment_date: str | None,
        appointment_day: object | None,
        appointment_hour: str | None,
        slots: str | None,
        evidence_path: object | None,
        details: dict[str, Any] | None,
        program_expediente: str | None,
        program_plate: str | None,
        occurred_at: str,
    ) -> str:
        reservation_id = _id_from_value(
            "reservation",
            f"{order_id}-{run_id or occurred_at}",
        )
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, order_id, run_id, status, site, appointment_date,
                appointment_day, appointment_hour, slots, evidence_path, details_json,
                program_expediente, program_plate, reserved_at, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(reservation_id) DO UPDATE SET
                status = excluded.status,
                appointment_date = COALESCE(
                    excluded.appointment_date, reservations.appointment_date
                ),
                appointment_day = COALESCE(
                    excluded.appointment_day, reservations.appointment_day
                ),
                appointment_hour = COALESCE(
                    excluded.appointment_hour, reservations.appointment_hour
                ),
                evidence_path = excluded.evidence_path,
                details_json = excluded.details_json,
                program_expediente = COALESCE(
                    excluded.program_expediente, reservations.program_expediente
                ),
                program_plate = COALESCE(
                    excluded.program_plate, reservations.program_plate
                ),
                updated_at = excluded.updated_at
            """,
            (
                reservation_id,
                order_id,
                run_id,
                status,
                site,
                appointment_date,
                appointment_day,
                appointment_hour,
                slots,
                evidence_path,
                Jsonb(details) if details else None,
                program_expediente,
                program_plate,
                occurred_at,
                occurred_at,
                occurred_at,
            ),
        )
        return reservation_id

    def ensure_pending_payment(
        self,
        connection: Connection,
        *,
        order_id: str,
        reservation_id: str,
        amount_agreed: Decimal,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO payments (
                payment_id, order_id, reservation_id, status, amount_agreed,
                currency, created_at, updated_at
            )
            VALUES (%s, %s, %s, 'pending', %s, 'PEN', %s, %s)
            ON CONFLICT(payment_id) DO UPDATE SET
                reservation_id = COALESCE(
                    payments.reservation_id, excluded.reservation_id
                ),
                amount_agreed = excluded.amount_agreed,
                updated_at = excluded.updated_at
            """,
            (
                _id_from_value("payment", order_id),
                order_id,
                reservation_id,
                amount_agreed,
                occurred_at,
                occurred_at,
            ),
        )

    def update_order_after_confirmation(
        self,
        connection: Connection,
        *,
        order_id: str,
        no_charge: bool,
        program_expediente: str | None,
        program_plate: str | None,
        occurred_at: str,
    ) -> None:
        connection.execute(
            """
            UPDATE service_orders
            SET status = CASE
                    WHEN status = 'paid' THEN 'paid'
                    ELSE %s
                END,
                program_expediente = COALESCE(program_expediente, %s),
                program_plate = COALESCE(program_plate, %s),
                updated_at = %s
            WHERE order_id = %s
            """,
            (
                "archived" if no_charge else "reserved_payment_pending",
                program_expediente,
                program_plate,
                occurred_at,
                order_id,
            ),
        )
