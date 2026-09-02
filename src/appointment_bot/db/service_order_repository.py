from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.models import ServiceOrderCreateResult
from appointment_bot.core.service_packages import SERVICE_PACKAGE_INTEGRAL
from appointment_bot.db.common import (
    _excluded_date_ranges_json,
    _id_from_value,
    _operation_connection,
    _settings,
    init_database,
)
from appointment_bot.db.order_contacts import _optional_clean_text, _upsert_contact


@dataclass(frozen=True, slots=True, repr=False)
class ServiceOrderPersistenceRequest:
    document_number: str
    encrypted_password: str
    document_type: str
    priority: int
    contact_whatsapp: str | None
    contact_whatsapp_username: str | None
    contact_name: str | None
    contact_source: str | None
    applicant_name: str | None
    charge_required: bool
    service_type: str
    service_package: str
    reservation_price: Decimal
    official_fee_amount: Decimal
    initial_payment_amount: Decimal
    minimum_date: date | None
    maximum_date: date | None
    allowed_weekdays: list[int] | None
    excluded_date_ranges: list[tuple[date, date]]
    parent_order_id: str | None
    program_expediente: str | None
    program_plate: str | None
    actor: str
    require_preflight: bool
    occurred_at: str


def persist_service_order(
    request: ServiceOrderPersistenceRequest,
    *,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> ServiceOrderCreateResult:
    settings = _settings(settings)
    init_database(settings)
    document_number = request.document_number
    encrypted_password = request.encrypted_password
    document_type = request.document_type
    priority = request.priority
    contact_whatsapp = request.contact_whatsapp
    contact_whatsapp_username = request.contact_whatsapp_username
    contact_name = request.contact_name
    contact_source = request.contact_source
    applicant_name = request.applicant_name
    charge_required = request.charge_required
    service_type = request.service_type
    effective_service_package = request.service_package
    effective_reservation_price = request.reservation_price
    official_fee_amount = request.official_fee_amount
    initial_payment_amount = request.initial_payment_amount
    parsed_minimum_date = request.minimum_date
    parsed_maximum_date = request.maximum_date
    parsed_allowed_weekdays = request.allowed_weekdays
    parsed_excluded_date_ranges = request.excluded_date_ranges
    parent_order_id = request.parent_order_id
    program_expediente = request.program_expediente
    program_plate = request.program_plate
    actor = request.actor
    require_preflight = request.require_preflight
    now = request.occurred_at
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
        existing_commercial_terms = connection.execute(
            """
            SELECT service_package, service_type, reservation_price, charge_required
            FROM service_orders
            WHERE order_id = %s
            FOR UPDATE
            """,
            (order_id,),
        ).fetchone()
        if existing_commercial_terms is not None:
            _validate_integral_commercial_correction(
                connection,
                order_id=order_id,
                current=existing_commercial_terms,
                service_package=effective_service_package,
                service_type=service_type,
                reservation_price=effective_reservation_price,
                charge_required=charge_required,
            )
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
                        %s, %s)
                ON CONFLICT(receipt_id) DO NOTHING
                """,
                (
                    _id_from_value("receipt", f"integral_initial:{order_id}"),
                    payment_id,
                    order_id,
                    initial_payment_amount,
                    now,
                    actor,
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


def _validate_integral_commercial_correction(
    connection: Connection,
    *,
    order_id: str,
    current: dict[str, object],
    service_package: str,
    service_type: str,
    reservation_price: Decimal,
    charge_required: bool,
) -> None:
    current_package = str(current["service_package"])
    if SERVICE_PACKAGE_INTEGRAL not in {current_package, service_package}:
        return
    unchanged = (
        current_package == service_package
        and str(current["service_type"]) == service_type
        and current["reservation_price"] == reservation_price
        and bool(current["charge_required"]) == charge_required
    )
    if unchanged:
        return
    has_financial_history = connection.execute(
        """
        SELECT EXISTS (SELECT 1 FROM payments WHERE order_id = %s)
            OR EXISTS (SELECT 1 FROM payment_receipts WHERE order_id = %s)
            OR EXISTS (SELECT 1 FROM finance_entries WHERE order_id = %s)
            AS present
        """,
        (order_id, order_id, order_id),
    ).fetchone()
    if has_financial_history is not None and bool(has_financial_history["present"]):
        raise ValueError(
            "Las condiciones del paquete Trámite integral no pueden corregirse después "
            "de registrar abonos o costos; se requiere una corrección contable auditada."
        )
