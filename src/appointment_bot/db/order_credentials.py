from __future__ import annotations

import json
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
from appointment_bot.core.statuses import sanitize_details
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
from appointment_bot.db.remote_control_audit import record_remote_control_audit_in_connection

COMMUNICATION_DECISIONS = {
    "client_already_informed",
    "keep_without_send",
    "preview_single_confirmation",
}

PROGRAM_LISTING_ROW_FIELDS = (
    "action_index",
    "expediente",
    "motivo",
    "tipo",
    "placa",
    "marca",
    "modelo",
    "motor",
    "color",
    "status",
    "cells",
)


class ProgramResolutionConflict(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProgramResolutionNotFound(ValueError):
    code = "program_order_not_found"


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


def record_order_program_listing(
    order_id: str,
    details: dict[str, Any],
    *,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    listing = sanitize_details(details) or {}
    signature = json.dumps(
        _canonical_program_listing_snapshot(listing),
        sort_keys=True,
        ensure_ascii=True,
        default=str,
    )
    with _connection(_database_url(settings)) as connection:
        previous = connection.execute(
            "SELECT program_listing FROM order_state WHERE order_id = %s FOR UPDATE",
            (order_id,),
        ).fetchone()
        previous_payload = previous["program_listing"] if previous is not None else None
        previous_signature = (
            previous_payload.get("signature") if isinstance(previous_payload, dict) else None
        )
        changed = previous_signature != signature
        previous_revision = (
            int(previous_payload.get("revision") or 0)
            if isinstance(previous_payload, dict)
            else 0
        )
        payload = {
            "signature": signature,
            "revision": previous_revision + 1 if changed else max(previous_revision, 1),
            "details": listing,
            "updated_at": _now(),
        }
        if not changed and isinstance(previous_payload, dict):
            resolution = previous_payload.get("resolution")
            if isinstance(resolution, dict):
                payload["resolution"] = resolution
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


def _canonical_program_listing_snapshot(details: dict[str, Any]) -> dict[str, Any]:
    rows = details.get("rows")
    if not isinstance(rows, list):
        return {"rows": []}
    return {
        "rows": [
            {field: row.get(field) for field in PROGRAM_LISTING_ROW_FIELDS}
            for row in rows
            if isinstance(row, dict)
        ]
    }


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


def resolve_service_order_programs(
    order_id: str,
    *,
    resolution: str,
    listing_signature: str,
    communication_decision: str,
    actor: str,
    program_expediente: str | None = None,
    program_plate: str | None = None,
    children: list[dict[str, Any]] | None = None,
    confirm_same_commercial_terms: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    resolution = resolution.strip().lower()
    if resolution not in {"one", "all", "pause"}:
        raise ValueError("resolution must be one, all or pause.")
    if communication_decision not in COMMUNICATION_DECISIONS:
        raise ValueError(
            "communication_decision must be client_already_informed, "
            "keep_without_send or preview_single_confirmation."
        )
    if resolution == "pause" and communication_decision == "preview_single_confirmation":
        raise ValueError("pause cannot prepare a customer confirmation preview.")
    if not listing_signature:
        raise ValueError("listing_signature is required.")
    actor = " ".join(actor.split())[:80]
    if not actor:
        raise ValueError("An authenticated actor is required.")

    now = _now()
    with _connection(_database_url(settings)) as connection:
        locked = connection.execute(
            """
            SELECT so.*, pa.username, pa.document_type, pa.password,
                   COALESCE(NULLIF(a.full_name, ''), a.document_number) AS applicant_name,
                   os.program_listing, os.preflight_status, os.preflight_details,
                   (
                       so.lease_owner IS NOT NULL
                       AND so.lease_expires_at > CURRENT_TIMESTAMP
                   ) AS has_active_lease
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            JOIN order_state os ON os.order_id = so.order_id
            WHERE so.order_id = %s
            FOR UPDATE OF so, os
            """,
            (order_id,),
        ).fetchone()
        if locked is None:
            raise ProgramResolutionNotFound(f"No existe la orden: {order_id}")
        listing = locked["program_listing"]
        if not isinstance(listing, dict) or not isinstance(listing.get("details"), dict):
            raise ProgramResolutionConflict(
                "program_listing_missing",
                "La orden no conserva un listado de tramites resoluble.",
            )
        if listing.get("signature") != listing_signature:
            raise ProgramResolutionConflict(
                "program_listing_stale",
                "El listado de tramites cambio; refresca y confirma nuevamente.",
            )
        pending_rows = _pending_program_rows(listing["details"])
        if len(pending_rows) < 2 and resolution in {"all", "pause"}:
            raise ProgramResolutionConflict(
                "program_resolution_not_required",
                "La cuenta ya no tiene multiples tramites pendientes.",
            )

        previous_resolution = listing.get("resolution")
        requested_fingerprint = {
            "resolution": resolution,
            "communication_decision": communication_decision,
            "program_expediente": _optional_clean_text(program_expediente),
            "program_plate": _optional_clean_text(program_plate),
            "children": sorted(
                children or [],
                key=lambda item: str(item.get("program_expediente") or "")
                if isinstance(item, dict)
                else "",
            ),
            "confirm_same_commercial_terms": bool(confirm_same_commercial_terms),
        }
        if isinstance(previous_resolution, dict) and previous_resolution.get(
            "request"
        ) == requested_fingerprint:
            return {
                "status": "already_applied",
                "order_id": order_id,
                "listing_signature": listing_signature,
                "listing_revision": int(listing.get("revision") or 1),
                **previous_resolution.get("result", {}),
            }
        if isinstance(previous_resolution, dict):
            raise ProgramResolutionConflict(
                "program_resolution_already_applied",
                "Esta revision del listado ya tiene una resolucion aplicada.",
            )

        if str(locked["status"]) != "paused":
            raise ProgramResolutionConflict(
                "program_resolution_invalid_state",
                "La orden debe estar pausada antes de resolver sus tramites.",
            )
        preflight_details = locked["preflight_details"]
        if (
            str(locked["preflight_status"]) != "failed"
            or not isinstance(preflight_details, dict)
            or preflight_details.get("error_type")
            != "multiple_pending_resolution_required"
        ):
            raise ProgramResolutionConflict(
                "program_resolution_preflight_conflict",
                "La orden no conserva el bloqueo de preflight por multiples tramites.",
            )
        if bool(locked["has_active_lease"]):
            raise ProgramResolutionConflict(
                "program_resolution_active_lease",
                "La orden tiene un lease activo y no puede resolverse en paralelo.",
            )
        active_attempt = connection.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM reservation_attempts
                WHERE order_id = %s
                  AND status IN ('intent', 'pending', 'unknown')
            ) AS active
            """,
            (order_id,),
        ).fetchone()
        if bool(active_attempt and active_attempt["active"]):
            raise ProgramResolutionConflict(
                "program_resolution_active_attempt",
                "La orden tiene un intento de reserva activo o ambiguo.",
            )

        preview_rows: list[dict[str, Any]] = []
        result: dict[str, Any]
        if resolution == "pause":
            connection.execute(
                "UPDATE service_orders SET status = 'paused', updated_at = %s "
                "WHERE order_id = %s",
                (now, order_id),
            )
            result = {
                "resolution": "pause",
                "parent_order_id": order_id,
                "parent_archived": False,
                "preflight_scheduled": False,
            }
        elif resolution == "one":
            selected = _select_pending_program(
                pending_rows,
                program_expediente=program_expediente,
                program_plate=program_plate,
            )
            connection.execute(
                """
                UPDATE service_orders
                SET program_expediente = %s, program_plate = %s,
                    status = 'paused', updated_at = %s
                WHERE order_id = %s
                """,
                (
                    _optional_clean_text(selected.get("expediente")),
                    _optional_clean_text(selected.get("placa")),
                    now,
                    order_id,
                ),
            )
            result = {
                "resolution": "one",
                "parent_order_id": order_id,
                "parent_archived": False,
                "selected_program": selected,
                "preflight_scheduled": True,
            }
            preview_rows = [selected]
        else:
            _ensure_program_split_has_no_financial_history(connection, locked)
            specs = _commercial_specs_for_pending_rows(
                locked,
                pending_rows,
                children=children,
                confirm_same=confirm_same_commercial_terms,
            )
            created = _create_program_children_in_connection(
                connection,
                parent=locked,
                pending_rows=pending_rows,
                commercial_specs=specs,
                listing=listing,
                settings=settings,
            )
            connection.execute(
                "UPDATE service_orders SET status = 'archived', updated_at = %s "
                "WHERE order_id = %s",
                (now, order_id),
            )
            result = {
                "resolution": "all",
                "parent_order_id": order_id,
                "parent_archived": True,
                "service_orders": [
                    {
                        "order_id": item.order_id,
                        "applicant_id": item.applicant_id,
                        "portal_account_id": item.portal_account_id,
                    }
                    for item in created
                ],
                "preflight_scheduled": False,
            }
            preview_rows = pending_rows
        if communication_decision == "preview_single_confirmation":
            result["communication_preview"] = _program_resolution_preview(
                locked["applicant_name"], preview_rows
            )
        result["communication_decision"] = communication_decision
        audit_id = record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action="resolve_service_order_programs",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            detail=(
                f"resolution={resolution}; listing_revision={listing.get('revision')}; "
                f"communication_decision={communication_decision}"
            ),
        )
        result["audit_id"] = audit_id
        resolution_payload = {
            "request": requested_fingerprint,
            "actor": actor,
            "decided_at": now,
            "result": result,
        }
        listing["resolution"] = resolution_payload
        listing["updated_at"] = now
        connection.execute(
            "UPDATE order_state SET program_listing = %s WHERE order_id = %s",
            (Jsonb(listing), order_id),
        )
    return {
        "status": "applied",
        "order_id": order_id,
        "listing_signature": listing_signature,
        "listing_revision": int(listing.get("revision") or 1),
        **result,
    }


def _pending_program_rows(details: dict[str, Any]) -> list[dict[str, Any]]:
    rows = details.get("rows")
    if not isinstance(rows, list):
        return []
    return [
        dict(row)
        for row in rows
        if isinstance(row, dict)
        and str(row.get("status") or "").strip().casefold() == "pendiente"
    ]


def _normalized_program_value(value: object, *, remove_punctuation: bool = False) -> str:
    normalized = "".join(str(value or "").split()).casefold()
    if remove_punctuation:
        return "".join(character for character in normalized if character.isalnum())
    return normalized


def _select_pending_program(
    pending_rows: list[dict[str, Any]],
    *,
    program_expediente: str | None,
    program_plate: str | None,
) -> dict[str, Any]:
    expediente_key = _normalized_program_value(program_expediente)
    plate_key = _normalized_program_value(program_plate, remove_punctuation=True)
    if not expediente_key and not plate_key:
        raise ValueError("one requires program_expediente or program_plate.")
    matches = [
        row
        for row in pending_rows
        if (
            not expediente_key
            or _normalized_program_value(row.get("expediente")) == expediente_key
        )
        and (
            not plate_key
            or _normalized_program_value(row.get("placa"), remove_punctuation=True)
            == plate_key
        )
    ]
    if len(matches) != 1:
        raise ProgramResolutionConflict(
            "program_target_not_unique",
            "El expediente o la placa no identifica un unico tramite PENDIENTE.",
        )
    return matches[0]


def _ensure_program_split_has_no_financial_history(
    connection: Connection,
    parent: dict[str, Any],
) -> None:
    financial = connection.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM payments WHERE order_id = %s
        ) OR EXISTS (
            SELECT 1 FROM payment_receipts WHERE order_id = %s
        ) OR EXISTS (
            SELECT 1 FROM finance_entries WHERE order_id = %s
        ) AS has_financial_history
        """,
        (parent["order_id"], parent["order_id"], parent["order_id"]),
    ).fetchone()
    if str(parent["service_package"]) == SERVICE_PACKAGE_INTEGRAL or bool(
        financial and financial["has_financial_history"]
    ):
        raise ProgramResolutionConflict(
            "program_resolution_financial_allocation_required",
            "La orden tiene paquete integral o historia financiera; define primero "
            "como se asignan cobros y costos entre los tramites.",
        )


def _commercial_specs_for_pending_rows(
    parent: dict[str, Any],
    pending_rows: list[dict[str, Any]],
    *,
    children: list[dict[str, Any]] | None,
    confirm_same: bool,
) -> dict[str, dict[str, Any]]:
    expedientes = [_optional_clean_text(row.get("expediente")) for row in pending_rows]
    if any(not expediente for expediente in expedientes) or len(set(expedientes)) != len(
        expedientes
    ):
        raise ProgramResolutionConflict(
            "program_pending_expediente_not_unique",
            "Cada tramite PENDIENTE debe tener un expediente unico para resolver todos.",
        )
    if confirm_same:
        if children:
            raise ValueError(
                "Use children or confirm_same_commercial_terms, but not both."
            )
        shared = {
            "charge_required": bool(parent["charge_required"]),
            "service_type": str(parent["service_type"]),
            "service_package": str(parent["service_package"]),
            "reservation_price": parent["reservation_price"],
            "minimum_reservation_date": parent["minimum_date"],
            "maximum_reservation_date": parent["maximum_date"],
            "allowed_weekdays": parent["allowed_weekdays"],
            "excluded_date_ranges": parent["excluded_date_ranges"],
        }
        return {str(expediente): dict(shared) for expediente in expedientes}
    if not children:
        raise ValueError(
            "all requires complete children or confirm_same_commercial_terms=true."
        )
    required = {
        "program_expediente",
        "charge_required",
        "service_type",
        "service_package",
        "reservation_price",
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    }
    specs: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(children):
        if not isinstance(spec, dict):
            raise ValueError(f"children[{index}] must be an object.")
        missing = required - set(spec)
        if missing:
            raise ValueError(
                f"children[{index}] is missing: {', '.join(sorted(missing))}."
            )
        expediente = _optional_clean_text(spec.get("program_expediente"))
        if not expediente or expediente not in expedientes or expediente in specs:
            raise ValueError(
                f"children[{index}].program_expediente is invalid or duplicated."
            )
        service_type = str(spec["service_type"]).strip().lower()
        if service_type not in {"standard", "selected_weekday", "custom"}:
            raise ValueError(f"children[{index}].service_type is invalid.")
        price = Decimal(str(spec["reservation_price"])).quantize(Decimal("0.01"))
        package = normalize_service_package(str(spec["service_package"]))
        package_amounts(package, price)
        if not isinstance(spec["charge_required"], bool):
            raise ValueError(f"children[{index}].charge_required must be boolean.")
        if package == SERVICE_PACKAGE_INTEGRAL:
            raise ProgramResolutionConflict(
                "program_integral_split_unsupported",
                "Una division por tramites no puede crear ordenes hijas integrales.",
            )
        specs[expediente] = {
            **spec,
            "service_type": service_type,
            "service_package": package,
            "reservation_price": price,
        }
    if set(specs) != set(expedientes):
        raise ValueError("children must define every pending expediente exactly once.")
    return specs


def _create_program_children_in_connection(
    connection: Connection,
    *,
    parent: dict[str, Any],
    pending_rows: list[dict[str, Any]],
    commercial_specs: dict[str, dict[str, Any]],
    listing: dict[str, Any],
    settings: Settings,
) -> list[ServiceOrderCreateResult]:
    password = _credential_cipher(settings).decrypt(str(parent["password"]))
    created: list[ServiceOrderCreateResult] = []
    for row in pending_rows:
        expediente = str(_optional_clean_text(row.get("expediente")))
        spec = commercial_specs[expediente]
        result = create_service_order(
            document_number=str(parent["username"]),
            password=password,
            document_type=str(parent["document_type"]),
            priority=int(parent["priority"]),
            applicant_name=str(parent["applicant_name"]),
            charge_required=bool(spec["charge_required"]),
            service_type=str(spec["service_type"]),
            service_package=str(spec["service_package"]),
            reservation_price=Decimal(str(spec["reservation_price"])),
            minimum_reservation_date=spec.get("minimum_reservation_date"),
            maximum_reservation_date=spec.get("maximum_reservation_date"),
            allowed_weekdays=spec.get("allowed_weekdays"),
            excluded_date_ranges=spec.get("excluded_date_ranges"),
            parent_order_id=str(parent["order_id"]),
            program_expediente=expediente,
            program_plate=_optional_clean_text(row.get("placa")),
            require_preflight=False,
            settings=settings,
            _connection_override=connection,
        )
        connection.execute(
            """
            UPDATE order_state
            SET preflight_status = 'validated',
                preflight_message = %s,
                preflight_validated_at = %s,
                preflight_details = %s,
                program_listing = %s
            WHERE order_id = %s
            """,
            (
                "Tramite objetivo confirmado por resolucion explicita del operador.",
                _now(),
                Jsonb(
                    {
                        "error_type": None,
                        "program_target": row,
                        "source": "program_resolution_all",
                    }
                ),
                Jsonb(listing),
                result.order_id,
            ),
        )
        created.append(result)
    return created


def _program_resolution_preview(
    applicant_name: object,
    pending_rows: list[dict[str, Any]],
) -> str:
    lines = [
        f"Hola, {str(applicant_name or 'cliente').strip()}.",
        "Confirmamos que atenderemos los siguientes tramites:",
    ]
    for row in pending_rows:
        expediente = str(row.get("expediente") or "sin expediente").strip()
        plate = str(row.get("placa") or "sin placa").strip()
        lines.append(f"- Expediente {expediente} | Placa {plate}")
    lines.append("Este texto es solo una previsualizacion y aun no fue enviado.")
    return "\n".join(lines)


def split_service_order_programs(
    order_id: str,
    *,
    archive_parent: bool = True,
    settings: Settings | None = None,
) -> list[ServiceOrderCreateResult]:
    raise ProgramResolutionConflict(
        "explicit_program_resolution_required",
        "La division directa fue retirada. Usa program-resolution con listado, "
        "condiciones comerciales y decision de comunicacion explicitas.",
    )


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
