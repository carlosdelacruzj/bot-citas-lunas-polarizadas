from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.core.program_eligibility import (
    ProgramHistoryUnresolved,
    appointment_identity,
    program_key,
    reservation_program_identity,
)
from appointment_bot.db.common import _connection, _database_url, _settings, init_database


def booked_programs_in_connection(
    connection: Connection, order_id: str, *, require_complete: bool = True
) -> dict[str, dict[str, Any]]:
    records = connection.execute(
        """
        SELECT r.program_expediente, r.appointment_date, r.appointment_hour,
               r.reservation_id, r.reserved_at, r.details_json
        FROM reservations r
        JOIN service_orders history ON history.order_id = r.order_id
        JOIN service_orders current_order
          ON current_order.portal_account_id = history.portal_account_id
        WHERE current_order.order_id = %s AND r.status = 'confirmed'
        ORDER BY r.reserved_at
        """,
        (order_id,),
    ).fetchall()
    booked = {}
    unresolved = []
    for record in records:
        identity = reservation_program_identity(record)
        if not identity:
            unresolved.append(record["reservation_id"])
            continue
        booked[program_key(identity)] = {
            "expediente": identity,
            "eligibility": "booked",
            "eligibility_reason": "Reserva confirmada en nuestro historial.",
            "appointment_source": "reservation_history",
            "appointment_date": record["appointment_date"],
            "appointment_hour": record["appointment_hour"],
            "reservation_id": record["reservation_id"],
            "appointment_checked_at": str(record["reserved_at"]),
        }
    if unresolved and require_complete:
        raise ProgramHistoryUnresolved(unresolved)
    listings = connection.execute(
        """
        SELECT state.program_listing
        FROM order_state state
        JOIN service_orders history ON history.order_id = state.order_id
        JOIN service_orders current_order
          ON current_order.portal_account_id = history.portal_account_id
        WHERE current_order.order_id = %s AND state.program_listing IS NOT NULL
        """,
        (order_id,),
    ).fetchall()
    for record in listings:
        listing = record["program_listing"]
        for row in listing.get("booked_programs", []):
            key = program_key(row.get("expediente"))
            if key and row.get("eligibility") == "booked":
                booked.setdefault(key, row)
    return booked


def reconcile_program_history(
    order_id: str, *, settings: RuntimeSettings, reviewed: list[dict[str, Any]] | None = None,
) -> int:
    """Copy only identity frozen in reservation evidence; never infer from today's listing."""
    with _connection(_database_url(settings)) as connection:
        records = connection.execute(
            """
            SELECT r.reservation_id, r.program_expediente, r.details_json,
                   r.appointment_date, r.appointment_hour
            FROM reservations r
            JOIN service_orders history ON history.order_id = r.order_id
            JOIN service_orders current_order
              ON current_order.portal_account_id = history.portal_account_id
            WHERE current_order.order_id = %s AND r.status = 'confirmed'
            FOR UPDATE OF r
            """, (order_id,),
        ).fetchall()
        updated = 0
        for record in records:
            if program_key(record["program_expediente"]):
                continue
            identity = reservation_program_identity(record)
            evidence: dict[str, Any] = {"source": "reservation_evidence"}
            if not identity and reviewed:
                target = appointment_identity(
                    record["appointment_date"], record["appointment_hour"],
                )
                matches = [row for row in reviewed if (
                    row.get("eligibility") == "booked"
                    and row.get("appointment_source") == "portal"
                    and row.get("appointment_checked_at")
                    and program_key(row.get("expediente"))
                    and target != ("", "")
                    and appointment_identity(
                        row.get("appointment_date"), row.get("appointment_hour"),
                        row.get("appointment_message"),
                    ) == target
                )]
                same_appointment = [item for item in records if appointment_identity(
                    item["appointment_date"], item["appointment_hour"],
                ) == target]
                if len(matches) == 1 and len(same_appointment) == 1:
                    identity = str(matches[0]["expediente"])
                    evidence = {"source": "portal_exact_appointment", "observation": matches[0]}
            if not identity:
                continue
            connection.execute(
                """
                UPDATE reservations SET program_expediente = %s,
                    details_json = COALESCE(details_json, '{}'::jsonb) ||
                        jsonb_build_object('program_identity_evidence', %s::jsonb,
                                           'program_identity_reconciled_at', CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE reservation_id = %s
                """, (identity, Jsonb(evidence), record["reservation_id"]),
            )
            updated += 1
        return updated


def get_booked_programs(
    order_id: str, *, settings: RuntimeSettings | None = None, require_complete: bool = True
) -> dict[str, dict[str, Any]]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return booked_programs_in_connection(
            connection, order_id, require_complete=require_complete,
        )


def bind_eligible_program(
    order_id: str, row: dict[str, Any], *, settings: RuntimeSettings
) -> None:
    key = program_key(row.get("expediente"))
    if not key or row.get("eligibility") != "eligible":
        raise ValueError("El expediente no está verificado para una nueva reserva.")
    with _connection(_database_url(settings)) as connection:
        order = connection.execute(
            "SELECT program_expediente FROM service_orders WHERE order_id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        if order is None:
            raise ValueError("No existe la orden.")
        if order["program_expediente"] and program_key(order["program_expediente"]) != key:
            raise ValueError("No se permite cambiar automáticamente de expediente.")
        if key in booked_programs_in_connection(connection, order_id):
            raise ValueError("El expediente ya tiene cita reservada.")
        connection.execute(
            "UPDATE service_orders SET program_expediente = %s, program_plate = %s "
            "WHERE order_id = %s",
            (str(row["expediente"]), row.get("placa") or None, order_id),
        )


def remember_booked_programs(
    order_id: str, rows: list[dict[str, Any]], *, settings: RuntimeSettings
) -> None:
    observed = [row for row in rows if row.get("eligibility") == "booked"]
    if not observed:
        return
    with _connection(_database_url(settings)) as connection:
        current = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        if current is None:
            raise ValueError("No existe el estado de la orden.")
        listing = dict(current["program_listing"] or {})
        booked = {
            program_key(row.get("expediente")): row
            for row in listing.get("booked_programs", [])
        }
        for row in observed:
            key = program_key(row.get("expediente"))
            if not key:
                raise ValueError("No se puede guardar una cita sin expediente exacto.")
            booked.setdefault(key, dict(row))
        listing["booked_programs"] = list(booked.values())
        connection.execute(
            "UPDATE order_state SET program_listing = %s WHERE order_id = %s",
            (Jsonb(listing), order_id),
        )
