from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.documents import normalize_document_type
from appointment_bot.core.models import (
    ServiceOrderCreateResult,
    ServiceOrderRuntime,
)
from appointment_bot.core.service_packages import (
    SERVICE_PACKAGE_INTEGRAL,
    infer_service_package,
    normalize_service_package,
    package_amounts,
)
from appointment_bot.db.common import (
    DEFAULT_RESERVATION_AMOUNT,
    _connection,
    _credential_cipher,
    _database_url,
    _excluded_date_ranges_json,
    _id_from_value,
    _now,
    _operation_connection,
    _parse_allowed_weekdays,
    _parse_excluded_date_ranges,
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
    contact_whatsapp_username: str | None = None,
    contact_name: str | None = None,
    contact_source: str | None = None,
    applicant_name: str | None = None,
    charge_required: bool = True,
    service_type: str = "standard",
    service_package: str | None = None,
    reservation_price: Decimal | None = None,
    minimum_reservation_hour: int | None = None,
    minimum_reservation_date: str | date | None = None,
    maximum_reservation_date: str | date | None = None,
    allowed_weekdays: Iterable[int] | None = None,
    excluded_date_ranges: Iterable[dict[str, object] | Iterable[object]] | None = None,
    parent_order_id: str | None = None,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    require_preflight: bool = True,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
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
    service_type = service_type.strip().lower()
    if service_type not in {"standard", "selected_weekday", "custom"}:
        raise ValueError("service_type must be standard, selected_weekday or custom.")
    effective_reservation_price = (
        DEFAULT_RESERVATION_AMOUNT if reservation_price is None else reservation_price
    )
    if effective_reservation_price <= 0:
        raise ValueError("reservation_price must be greater than zero.")
    effective_service_package = normalize_service_package(
        service_package or infer_service_package(service_type)
    )
    official_fee_amount, initial_payment_amount = package_amounts(
        effective_service_package,
        effective_reservation_price,
    )
    if minimum_reservation_hour is not None:
        raise ValueError("Las restricciones horarias ya no se aceptan.")
    parsed_minimum_date = _parse_minimum_reservation_date(minimum_reservation_date)
    parsed_maximum_date = _parse_maximum_reservation_date(maximum_reservation_date)
    parsed_allowed_weekdays = _parse_allowed_weekdays(allowed_weekdays)
    if service_type == "selected_weekday" and (
        parsed_allowed_weekdays is None or len(parsed_allowed_weekdays) != 1
    ):
        raise ValueError("selected_weekday requires exactly one allowed weekday.")
    if (
        parsed_minimum_date is not None
        and parsed_maximum_date is not None
        and parsed_maximum_date < parsed_minimum_date
    ):
        raise ValueError("maximum_reservation_date cannot be before minimum_reservation_date.")
    parsed_excluded_date_ranges = _parse_excluded_date_ranges(excluded_date_ranges)

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
    initial_status = "paused" if require_preflight else "ready"
    with _operation_connection(settings, _connection_override) as connection:
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
        persisted_order = connection.execute(
            """
            INSERT INTO service_orders (
                order_id, applicant_id, portal_account_id, priority, charge_required,
                service_type, reservation_price, service_package, official_fee_amount,
                initial_payment_amount, acquisition_source, acquisition_source_origin,
                minimum_hour, minimum_date, maximum_date, allowed_weekdays,
                excluded_date_ranges,
                parent_order_id, program_expediente, program_plate,
                status, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT(order_id) DO UPDATE SET
                applicant_id = excluded.applicant_id,
                portal_account_id = excluded.portal_account_id,
                priority = excluded.priority,
                charge_required = excluded.charge_required,
                service_type = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.service_type
                    ELSE excluded.service_type
                END,
                reservation_price = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.reservation_price
                    ELSE excluded.reservation_price
                END,
                service_package = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.service_package
                    ELSE excluded.service_package
                END,
                official_fee_amount = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.official_fee_amount
                    ELSE excluded.official_fee_amount
                END,
                initial_payment_amount = CASE
                    WHEN service_orders.status IN ('reserved_payment_pending', 'paid')
                        THEN service_orders.initial_payment_amount
                    ELSE excluded.initial_payment_amount
                END,
                acquisition_source = COALESCE(
                    service_orders.acquisition_source,
                    excluded.acquisition_source
                ),
                acquisition_source_origin = COALESCE(
                    service_orders.acquisition_source_origin,
                    excluded.acquisition_source_origin
                ),
                minimum_hour = NULL,
                minimum_date = COALESCE(excluded.minimum_date, service_orders.minimum_date),
                maximum_date = COALESCE(excluded.maximum_date, service_orders.maximum_date),
                allowed_weekdays = COALESCE(
                    excluded.allowed_weekdays,
                    service_orders.allowed_weekdays
                ),
                excluded_date_ranges = CASE
                    WHEN excluded.excluded_date_ranges = '[]'::jsonb
                        THEN service_orders.excluded_date_ranges
                    ELSE excluded.excluded_date_ranges
                END,
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
                    ELSE excluded.status
                END,
                updated_at = excluded.updated_at
            RETURNING service_package
            """,
            (
                order_id,
                applicant_id,
                portal_account_id,
                priority,
                charge_required,
                service_type,
                effective_reservation_price,
                effective_service_package,
                official_fee_amount,
                initial_payment_amount,
                _optional_clean_text(contact_source),
                "order_creation" if _optional_clean_text(contact_source) else None,
                None,
                parsed_minimum_date,
                parsed_maximum_date,
                parsed_allowed_weekdays,
                Jsonb(_excluded_date_ranges_json(parsed_excluded_date_ranges)),
                parent_order_id,
                program_expediente,
                program_plate,
                initial_status,
                now,
                now,
            ),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO order_state (order_id, preflight_status, preflight_message)
            VALUES (%s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                preflight_status = excluded.preflight_status,
                preflight_message = excluded.preflight_message,
                preflight_started_at = NULL,
                preflight_validated_at = NULL,
                preflight_details = NULL
            """,
            (
                order_id,
                "pending" if require_preflight else "not_required",
                "Validacion de acceso pendiente." if require_preflight else None,
            ),
        )
        if (
            persisted_order is not None
            and str(persisted_order["service_package"]) == SERVICE_PACKAGE_INTEGRAL
        ):
            payment_id = _id_from_value("payment", order_id)
            connection.execute(
                """
                INSERT INTO payments (
                    payment_id, order_id, status, amount_agreed, amount_paid,
                    currency, paid_at, created_at, updated_at
                )
                VALUES (%s, %s, 'pending', %s, %s, 'PEN', NULL, %s, %s)
                ON CONFLICT(payment_id) DO NOTHING
                """,
                (
                    payment_id,
                    order_id,
                    effective_reservation_price,
                    initial_payment_amount,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO payment_receipts (
                    receipt_id, payment_id, order_id, amount, received_at,
                    source, actor, created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'integral_initial_payment',
                        'dashboard-owner', %s)
                ON CONFLICT(receipt_id) DO NOTHING
                """,
                (
                    _id_from_value("receipt", f"integral_initial:{order_id}"),
                    payment_id,
                    order_id,
                    initial_payment_amount,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO finance_entries (
                    entry_id, occurred_on, entry_kind, category_code, vendor, description,
                    amount_original, currency, exchange_rate_pen, amount_pen, quantity, unit,
                    order_id, notes, data_quality, status, created_at, updated_at
                )
                VALUES (
                    %s, %s, 'expense', 'government_fee', %s, %s,
                    %s, 'PEN', 1, %s, 1, 'tasa', %s, %s, 'actual', 'active', %s, %s
                )
                ON CONFLICT(entry_id) DO NOTHING
                """,
                (
                    _id_from_value("finance", f"government_fee:{order_id}"),
                    date.fromisoformat(now[:10]),
                    "Págalo.pe / Banco de la Nación",
                    "Tasa 08362 para permiso nuevo de lunas polarizadas",
                    official_fee_amount,
                    official_fee_amount,
                    order_id,
                    "Costo directo incluido en el paquete integral.",
                    now,
                    now,
                ),
            )
        if contact_whatsapp or contact_whatsapp_username or contact_name:
            contact_id = _upsert_contact(
                connection,
                applicant_id=applicant_id,
                phone=contact_whatsapp,
                username=contact_whatsapp_username,
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


def update_service_order_credentials(
    order_id: str,
    *,
    document_number: str,
    password: str,
    document_type: str,
    settings: Settings | None = None,
) -> tuple[str, ...]:
    """Replace an account login while preserving the order and its history."""
    settings = _settings(settings)
    init_database(settings)
    document_number = document_number.strip()
    if not document_number:
        raise ValueError("document_number is required.")
    if not password:
        raise ValueError("password is required.")
    normalized_type = normalize_document_type(document_type)
    encrypted_password = _credential_cipher(settings).encrypt(password)
    now = _now()

    with _connection(_database_url(settings)) as connection:
        identity = connection.execute(
            """
            SELECT so.status, so.applicant_id, so.portal_account_id,
                   a.document_number AS previous_document
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            WHERE so.order_id = %s
            FOR UPDATE OF so, a, pa
            """,
            (order_id,),
        ).fetchone()
        if identity is None:
            raise ValueError(f"Service order not found: {order_id}")
        if identity["status"] not in {"ready", "paused"}:
            raise ValueError("Solo se pueden cambiar credenciales de una orden activa o pausada.")

        applicant_id = str(identity["applicant_id"])
        portal_account_id = str(identity["portal_account_id"])
        previous_document = str(identity["previous_document"])
        leased = connection.execute(
            """
            SELECT order_id
            FROM service_orders
            WHERE portal_account_id = %s
              AND lease_owner IS NOT NULL
              AND lease_expires_at > %s
            LIMIT 1
            """,
            (portal_account_id, now),
        ).fetchone()
        if leased is not None:
            raise RuntimeError(
                "La cuenta esta siendo usada por el worker. "
                "Espera a que termine y vuelve a guardar."
            )

        duplicate_applicant = connection.execute(
            """
            SELECT applicant_id
            FROM applicants
            WHERE document_number = %s AND applicant_id <> %s
            """,
            (document_number, applicant_id),
        ).fetchone()
        duplicate_account = connection.execute(
            """
            SELECT portal_account_id
            FROM portal_accounts
            WHERE username = %s AND portal_account_id <> %s
            """,
            (document_number, portal_account_id),
        ).fetchone()
        if duplicate_applicant is not None or duplicate_account is not None:
            raise ValueError("Ese usuario o documento ya pertenece a otra cuenta.")

        connection.execute(
            """
            UPDATE applicants
            SET document_number = %s,
                full_name = CASE
                    WHEN full_name IS NULL OR BTRIM(full_name) = '' OR full_name = %s
                        THEN %s
                    ELSE full_name
                END,
                updated_at = %s
            WHERE applicant_id = %s
            """,
            (document_number, previous_document, document_number, now, applicant_id),
        )
        connection.execute(
            """
            UPDATE portal_accounts
            SET username = %s, document_type = %s, password = %s, updated_at = %s
            WHERE portal_account_id = %s
            """,
            (document_number, normalized_type, encrypted_password, now, portal_account_id),
        )
        affected_rows = connection.execute(
            """
            UPDATE service_orders
            SET status = 'paused', updated_at = %s
            WHERE portal_account_id = %s
              AND status IN ('ready', 'paused')
            RETURNING order_id
            """,
            (now, portal_account_id),
        ).fetchall()
        affected_order_ids = tuple(str(row["order_id"]) for row in affected_rows)
        for affected_order_id in affected_order_ids:
            connection.execute(
                """
                INSERT INTO order_state (
                    order_id, preflight_status, preflight_message,
                    consecutive_errors, credential_failures
                )
                VALUES (%s, 'pending', %s, 0, 0)
                ON CONFLICT(order_id) DO UPDATE SET
                    preflight_status = 'pending',
                    preflight_message = excluded.preflight_message,
                    preflight_started_at = NULL,
                    preflight_validated_at = NULL,
                    preflight_details = NULL,
                    last_status = NULL,
                    last_message = NULL,
                    next_allowed_at = NULL,
                    consecutive_errors = 0,
                    credential_failures = 0,
                    program_listing = NULL
                """,
                (affected_order_id, "Credenciales actualizadas. Validacion de acceso pendiente."),
            )
    return affected_order_ids


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
                   wc.phone AS contact_phone, wc.username AS contact_username,
                   wc.contact_source,
                   so.priority, so.status, so.service_type, so.reservation_price,
                   so.service_package, so.official_fee_amount, so.initial_payment_amount,
                   so.minimum_date, so.maximum_date, so.allowed_weekdays,
                   so.excluded_date_ranges,
                   so.created_at, so.updated_at,
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
                   wc.phone AS contact_phone, wc.username AS contact_username,
                   wc.contact_source,
                   so.priority, so.status, so.service_type, so.reservation_price,
                   so.service_package, so.official_fee_amount, so.initial_payment_amount,
                   so.minimum_date, so.maximum_date, so.allowed_weekdays,
                   so.excluded_date_ranges,
                   so.created_at, so.updated_at,
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
        contact_whatsapp_username=row.get("contact_username"),
        contact_source=row.get("contact_source"),
        parent_order_id=row.get("parent_order_id"),
        program_expediente=row.get("program_expediente"),
        program_plate=row.get("program_plate"),
        service_type=str(row.get("service_type") or "standard"),
        reservation_price=f"{row.get('reservation_price'):.2f}",
        service_package=str(row.get("service_package") or "standard"),
        official_fee_amount=f"{row.get('official_fee_amount') or 0:.2f}",
        initial_payment_amount=f"{row.get('initial_payment_amount') or 0:.2f}",
        minimum_reservation_date=(
            str(row["minimum_date"]) if row.get("minimum_date") is not None else None
        ),
        maximum_reservation_date=(
            str(row["maximum_date"]) if row.get("maximum_date") is not None else None
        ),
        allowed_weekdays=(
            tuple(int(day) for day in row["allowed_weekdays"])
            if row.get("allowed_weekdays")
            else None
        ),
        excluded_date_ranges=tuple(
            {
                "start_date": str(item["start_date"]),
                "end_date": str(item["end_date"]),
            }
            for item in (row.get("excluded_date_ranges") or [])
            if isinstance(item, dict) and item.get("start_date") and item.get("end_date")
        ),
    )
