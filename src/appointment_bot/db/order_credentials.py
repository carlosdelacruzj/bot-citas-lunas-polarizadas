from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date
from typing import Any

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.documents import normalize_document_type
from appointment_bot.core.models import (
    ServiceOrderCreateResult,
    ServiceOrderRuntime,
)
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.common import (
    _connection,
    _credential_cipher,
    _database_url,
    _id_from_value,
    _now,
    _parse_allowed_weekdays,
    _parse_maximum_reservation_date,
    _parse_minimum_reservation_date,
    _settings,
    init_database,
)
from appointment_bot.db.order_contacts import _optional_clean_text, _upsert_contact


def create_service_order(
    *,
    document_number: str,
    password: str,
    document_type: str = "dni",
    priority: int = 0,
    contact_whatsapp: str | None = None,
    contact_name: str | None = None,
    contact_source: str | None = None,
    applicant_name: str | None = None,
    charge_required: bool = True,
    minimum_reservation_hour: int | None = None,
    minimum_reservation_date: str | date | None = None,
    maximum_reservation_date: str | date | None = None,
    allowed_weekdays: Iterable[int] | None = None,
    parent_order_id: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    settings: Settings | None = None,
) -> ServiceOrderCreateResult:
    settings = _settings(settings)
    init_database(settings)
    document_number = document_number.strip()
    if not document_number:
        raise ValueError("document_number is required.")
    if not password:
        raise ValueError("password is required.")
    document_type = normalize_document_type(document_type)
    if priority < 0:
        raise ValueError("priority must be non-negative.")
    if minimum_reservation_hour is not None and not 0 <= minimum_reservation_hour <= 23:
        raise ValueError("minimum_reservation_hour must be between 0 and 23.")
    parsed_minimum_date = _parse_minimum_reservation_date(minimum_reservation_date)
    parsed_maximum_date = _parse_maximum_reservation_date(maximum_reservation_date)
    if (
        parsed_minimum_date is not None
        and parsed_maximum_date is not None
        and parsed_maximum_date < parsed_minimum_date
    ):
        raise ValueError("maximum_reservation_date cannot be before minimum_reservation_date.")
    parsed_allowed_weekdays = _parse_allowed_weekdays(allowed_weekdays)

    now = _now()
    encrypted_password = _credential_cipher(settings).encrypt(password)
    program_expediente = _optional_clean_text(program_expediente)
    program_plate = _optional_clean_text(program_plate)
    applicant_id = _id_from_value("applicant", document_number)
    portal_account_id = _id_from_value("portal", document_number)
    parent_order_id = _optional_clean_text(parent_order_id)
    base_order_id = _id_from_value("order", document_number)
    program_key = program_expediente or program_plate
    order_id = (
        _id_from_value("order", f"{document_number}:{program_key}")
        if program_key
        else base_order_id
    )
    if program_key and parent_order_id is None:
        parent_order_id = base_order_id
    contact_id = None
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO applicants (
                applicant_id, document_number, full_name, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(document_number) DO UPDATE SET
                full_name = COALESCE(NULLIF(excluded.full_name, ''), applicants.full_name),
                updated_at = excluded.updated_at
            """,
            (applicant_id, document_number, applicant_name or document_number, now, now),
        )
        applicant_id = str(
            connection.execute(
                """
                SELECT applicant_id
                FROM applicants
                WHERE document_number = %s
                """,
                (document_number,),
            ).fetchone()["applicant_id"]
        )
        connection.execute(
            """
            INSERT INTO portal_accounts (
                portal_account_id, applicant_id, username, document_type, password,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(username) DO UPDATE SET
                applicant_id = excluded.applicant_id,
                document_type = excluded.document_type,
                password = excluded.password,
                updated_at = excluded.updated_at
            """,
            (
                portal_account_id,
                applicant_id,
                document_number,
                document_type,
                encrypted_password,
                now,
                now,
            ),
        )
        portal_account_id = str(
            connection.execute(
                """
                SELECT portal_account_id
                FROM portal_accounts
                WHERE username = %s
                """,
                (document_number,),
            ).fetchone()["portal_account_id"]
        )
        if not program_key:
            existing_order = connection.execute(
                """
                SELECT order_id
                FROM service_orders
                WHERE applicant_id = %s
                  AND portal_account_id = %s
                  AND program_expediente IS NULL
                  AND program_plate IS NULL
                ORDER BY created_at
                LIMIT 1
                """,
                (applicant_id, portal_account_id),
            ).fetchone()
            if existing_order is not None:
                order_id = str(existing_order["order_id"])
        if parent_order_id is not None:
            parent_exists = connection.execute(
                "SELECT 1 FROM service_orders WHERE order_id = %s",
                (parent_order_id,),
            ).fetchone()
            if parent_exists is None:
                if parent_order_id == base_order_id:
                    parent_order_id = None
                else:
                    raise ValueError(f"No existe la orden padre: {parent_order_id}")
        connection.execute(
            """
            INSERT INTO service_orders (
                order_id, applicant_id, portal_account_id, priority, charge_required,
                minimum_hour, minimum_date, maximum_date, allowed_weekdays,
                parent_order_id, program_expediente, program_plate,
                status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ready', %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                applicant_id = excluded.applicant_id,
                portal_account_id = excluded.portal_account_id,
                priority = excluded.priority,
                charge_required = excluded.charge_required,
                minimum_hour = COALESCE(excluded.minimum_hour, service_orders.minimum_hour),
                minimum_date = COALESCE(excluded.minimum_date, service_orders.minimum_date),
                maximum_date = COALESCE(excluded.maximum_date, service_orders.maximum_date),
                allowed_weekdays = COALESCE(
                    excluded.allowed_weekdays,
                    service_orders.allowed_weekdays
                ),
                parent_order_id = COALESCE(
                    excluded.parent_order_id,
                    service_orders.parent_order_id
                ),
                program_expediente = COALESCE(
                    excluded.program_expediente,
                    service_orders.program_expediente
                ),
                program_plate = COALESCE(excluded.program_plate, service_orders.program_plate),
                status = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.status
                    ELSE 'ready'
                END,
                updated_at = excluded.updated_at
            """,
            (
                order_id,
                applicant_id,
                portal_account_id,
                priority,
                charge_required,
                minimum_reservation_hour,
                parsed_minimum_date,
                parsed_maximum_date,
                parsed_allowed_weekdays,
                parent_order_id,
                program_expediente,
                program_plate,
                now,
                now,
            ),
        )
        connection.execute(
            "INSERT INTO order_state (order_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (order_id,),
        )
        if contact_whatsapp or contact_name:
            contact_id = _upsert_contact(
                connection,
                applicant_id=applicant_id,
                phone=contact_whatsapp,
                display_name=contact_name,
                source=contact_source,
                now=now,
            )
    return ServiceOrderCreateResult(
        order_id=order_id,
        applicant_id=applicant_id,
        portal_account_id=portal_account_id,
        contact_id=contact_id,
    )


def update_service_order_document_type(
    order_id: str,
    document_type: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    normalized_type = normalize_document_type(document_type)
    with _connection(_database_url(settings)) as connection:
        updated = connection.execute(
            """
            UPDATE portal_accounts pa
            SET document_type = %s,
                updated_at = CURRENT_TIMESTAMP
            FROM service_orders so
            WHERE so.order_id = %s
              AND so.portal_account_id = pa.portal_account_id
            RETURNING pa.portal_account_id
            """,
            (normalized_type, order_id),
        ).fetchone()
        if updated is None:
            raise ValueError(f"Service order not found: {order_id}")


def record_order_program_listing(
    order_id: str,
    details: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    listing = sanitize_details(details) or {}
    signature = json.dumps(listing, sort_keys=True, ensure_ascii=True, default=str)
    payload = {
        "signature": signature,
        "details": listing,
        "updated_at": _now(),
    }
    with _connection(_database_url(settings)) as connection:
        previous = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s",
            (order_id,),
        ).fetchone()
        previous_payload = previous["program_listing"] if previous is not None else None
        previous_signature = (
            previous_payload.get("signature") if isinstance(previous_payload, dict) else None
        )
        changed = previous_signature != signature
        connection.execute(
            """
            INSERT INTO order_state (order_id, program_listing)
            VALUES (%s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                program_listing = excluded.program_listing
            """,
            (order_id, Jsonb(payload)),
        )
    return changed


def get_order_program_listing(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s",
            (order_id,),
        ).fetchone()
    value = row["program_listing"] if row is not None else None
    return value if isinstance(value, dict) else None


def split_service_order_programs(
    order_id: str,
    *,
    archive_parent: bool = True,
    settings: Settings | None = None,
) -> list[ServiceOrderCreateResult]:
    settings = _settings(settings)
    init_database(settings)
    listing = get_order_program_listing(order_id, settings=settings)
    if not listing:
        raise ValueError(f"No hay listado de tramites registrado para {order_id}.")
    details = listing.get("details") if isinstance(listing.get("details"), dict) else listing
    rows = details.get("rows") if isinstance(details, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"El listado de tramites de {order_id} no contiene filas.")

    runtime = get_service_order_runtime(order_id, settings=settings)
    if runtime is None:
        raise ValueError(f"No existe la orden: {order_id}")

    with _connection(_database_url(settings)) as connection:
        parent = connection.execute(
            """
            SELECT priority, charge_required, minimum_hour, minimum_date, maximum_date,
                   allowed_weekdays
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
    if parent is None:
        raise ValueError(f"No existe la orden: {order_id}")

    created: list[ServiceOrderCreateResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().casefold()
        if status and status != "pendiente":
            continue
        expediente = _optional_clean_text(row.get("expediente"))
        plate = _optional_clean_text(row.get("placa"))
        if not expediente and not plate:
            continue
        created.append(
            create_service_order(
                document_number=runtime.username,
                password=runtime.password,
                priority=int(parent["priority"]),
                applicant_name=runtime.name,
                charge_required=bool(parent["charge_required"]),
                minimum_reservation_hour=parent["minimum_hour"],
                minimum_reservation_date=parent["minimum_date"],
                maximum_reservation_date=parent["maximum_date"],
                allowed_weekdays=(
                    tuple(int(day) for day in parent["allowed_weekdays"])
                    if parent["allowed_weekdays"]
                    else None
                ),
                parent_order_id=order_id,
                program_expediente=expediente,
                program_plate=plate,
                settings=settings,
            )
        )
    if not created:
        raise ValueError(f"No hay tramites pendientes divisibles para {order_id}.")
    if archive_parent:
        with _connection(_database_url(settings)) as connection:
            connection.execute(
                """
                UPDATE service_orders
                SET status = 'archived', updated_at = %s
                WHERE order_id = %s AND status = 'ready'
                """,
                (_now(), order_id),
            )
    return created


def get_service_order_runtime(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> ServiceOrderRuntime | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, pa.document_type, pa.password, wc.display_name AS contact_name,
                   wc.phone AS contact_phone, wc.contact_source,
                   so.priority, so.status, so.created_at, so.updated_at,
                   so.parent_order_id, so.program_expediente, so.program_plate
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE so.order_id = %s
            """,
            (order_id,),
        ).fetchone()
    return _runtime_from_row(row, settings) if row is not None else None


def get_claimed_service_order_runtime(
    order_id: str,
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> ServiceOrderRuntime | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, pa.document_type, pa.password, wc.display_name AS contact_name,
                   wc.phone AS contact_phone, wc.contact_source,
                   so.priority, so.status, so.created_at, so.updated_at,
                   so.parent_order_id, so.program_expediente, so.program_plate
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE so.order_id = %s AND so.status = 'ready'
              AND so.lease_owner = %s AND so.lease_expires_at > CURRENT_TIMESTAMP
            """,
            (order_id, owner_token),
        ).fetchone()
    return _runtime_from_row(row, settings) if row is not None else None


def _runtime_from_row(row: dict[str, Any], settings: Settings) -> ServiceOrderRuntime:
    return ServiceOrderRuntime(
        order_id=str(row["order_id"]),
        name=str(row["name"]),
        username=str(row["username"]),
        document_type=str(row["document_type"]),
        password=_credential_cipher(settings).decrypt(str(row["password"])),
        priority=int(row["priority"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        contact_name=row.get("contact_name"),
        contact_whatsapp=row.get("contact_phone"),
        contact_source=row.get("contact_source"),
        parent_order_id=row.get("parent_order_id"),
        program_expediente=row.get("program_expediente"),
        program_plate=row.get("program_plate"),
    )
