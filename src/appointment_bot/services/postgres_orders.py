from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.domain import OrderStateStatus, ResultStatus, sanitize_details
from appointment_bot.services.database_models import (
    ServiceOrderCandidate,
    ServiceOrderCreateResult,
    ServiceOrderRuntime,
    ServiceOrderSummary,
)
from appointment_bot.services.detail_helpers import appointment_datetime_details
from appointment_bot.services.order_selection import (
    ReservationConstraints,
    appointment_filter_from_constraints,
)
from appointment_bot.services.postgres_common import (
    _connection,
    _credential_cipher,
    _database_url,
    _decimal_or_none,
    _decimal_text,
    _id_from_value,
    _mask_phone,
    _mask_username,
    _normalize_phone,
    _now,
    _operation_connection,
    _parse_allowed_weekdays,
    _parse_minimum_reservation_date,
    _settings,
    init_database,
)
from appointment_bot.utils.sanitization import sanitize_text


def create_service_order(
    *,
    document_number: str,
    password: str,
    priority: int = 0,
    contact_whatsapp: str | None = None,
    contact_name: str | None = None,
    contact_source: str | None = None,
    applicant_name: str | None = None,
    charge_required: bool = True,
    minimum_reservation_hour: int | None = None,
    minimum_reservation_date: str | date | None = None,
    allowed_weekdays: Iterable[int] | None = None,
    settings: Settings | None = None,
) -> ServiceOrderCreateResult:
    settings = _settings(settings)
    init_database(settings)
    document_number = document_number.strip()
    if not document_number:
        raise ValueError("document_number is required.")
    if not password:
        raise ValueError("password is required.")
    if priority < 0:
        raise ValueError("priority must be non-negative.")
    if minimum_reservation_hour is not None and not 0 <= minimum_reservation_hour <= 23:
        raise ValueError("minimum_reservation_hour must be between 0 and 23.")
    parsed_minimum_date = _parse_minimum_reservation_date(minimum_reservation_date)
    parsed_allowed_weekdays = _parse_allowed_weekdays(allowed_weekdays)

    now = _now()
    encrypted_password = _credential_cipher(settings).encrypt(password)
    applicant_id = _id_from_value("applicant", document_number)
    portal_account_id = _id_from_value("portal", document_number)
    order_id = _id_from_value("order", document_number)
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
                portal_account_id, applicant_id, username, password, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(username) DO UPDATE SET
                applicant_id = excluded.applicant_id,
                password = excluded.password,
                updated_at = excluded.updated_at
            """,
            (portal_account_id, applicant_id, document_number, encrypted_password, now, now),
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
        existing_order = connection.execute(
            """
            SELECT order_id
            FROM service_orders
            WHERE applicant_id = %s AND portal_account_id = %s
            ORDER BY created_at
            LIMIT 1
            """,
            (applicant_id, portal_account_id),
        ).fetchone()
        if existing_order is not None:
            order_id = str(existing_order["order_id"])
        connection.execute(
            """
            INSERT INTO service_orders (
                order_id, applicant_id, portal_account_id, priority, charge_required,
                minimum_hour, minimum_date, allowed_weekdays, status, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ready', %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                applicant_id = excluded.applicant_id,
                portal_account_id = excluded.portal_account_id,
                priority = excluded.priority,
                charge_required = excluded.charge_required,
                minimum_hour = COALESCE(excluded.minimum_hour, service_orders.minimum_hour),
                minimum_date = COALESCE(excluded.minimum_date, service_orders.minimum_date),
                allowed_weekdays = COALESCE(
                    excluded.allowed_weekdays,
                    service_orders.allowed_weekdays
                ),
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
                parsed_allowed_weekdays,
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


def list_service_order_summaries(
    settings: Settings | None = None,
) -> list[ServiceOrderSummary]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT so.order_id, so.applicant_id, a.full_name, a.document_number,
                   wc.display_name AS contact_name, wc.phone AS contact_phone,
                   wc.contact_source,
                   so.priority, so.charge_required, so.status,
                   so.created_at, so.updated_at,
                   r.status AS reservation_status, r.site AS reservation_site,
                   r.appointment_date AS reservation_date, r.appointment_hour AS reservation_hour,
                   p.status AS payment_status, p.amount_agreed, p.amount_paid,
                   so.minimum_hour AS minimum_reservation_hour,
                   so.minimum_date AS minimum_reservation_date,
                   so.allowed_weekdays
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN LATERAL (
                SELECT status, site, appointment_date, appointment_hour
                FROM reservations
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) r ON true
            LEFT JOIN LATERAL (
                SELECT status, amount_agreed, amount_paid
                FROM payments
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) p ON true
            ORDER BY so.priority DESC, so.created_at ASC
            """
        ).fetchall()
    return [_service_order_summary_from_row(row) for row in rows]


def add_or_update_service_order_contact(
    order_id: str,
    *,
    contact_whatsapp: str | None = None,
    contact_name: str | None = None,
    contact_source: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = _service_order_identity(connection, order_id)
        if row is None:
            raise ValueError(f"Service order not found: {order_id}")
        _upsert_contact(
            connection,
            applicant_id=str(row["applicant_id"]),
            phone=contact_whatsapp,
            display_name=contact_name,
            source=contact_source,
            now=now,
        )


def mark_payment_paid(
    order_id: str,
    *,
    amount_paid: str | float | int,
    amount_agreed: str | float | int | None = None,
    settings: Settings | None = None,
) -> None:
    paid = _decimal_or_none(amount_paid)
    agreed = _decimal_or_none(amount_agreed)
    if paid is None:
        raise ValueError("amount_paid must be a valid amount.")
    if agreed is None:
        agreed = paid
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        if _service_order_identity(connection, order_id) is None:
            raise ValueError(f"Service order not found: {order_id}")
        connection.execute(
            """
            INSERT INTO payments (
                payment_id, order_id, status, amount_agreed, amount_paid,
                currency, paid_at, created_at, updated_at
            )
            VALUES (%s, %s, 'paid', %s, %s, 'PEN', %s, %s, %s)
            ON CONFLICT(payment_id) DO UPDATE SET
                status = 'paid',
                amount_agreed = excluded.amount_agreed,
                amount_paid = excluded.amount_paid,
                paid_at = excluded.paid_at,
                updated_at = excluded.updated_at
            """,
            (_id_from_value("payment", order_id), order_id, agreed, paid, now, now, now),
        )
        connection.execute(
            """
            UPDATE service_orders
            SET status = 'paid', updated_at = %s
            WHERE order_id = %s
            """,
            (now, order_id),
        )


def mark_service_order_no_charge(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET charge_required = false, updated_at = %s
            WHERE order_id = %s
            """,
            (now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")


def get_minimum_reservation_hour_for_order(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> int | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT minimum_hour FROM service_orders WHERE order_id = %s",
            (order_id,),
        ).fetchone()
    if row is None or row["minimum_hour"] is None:
        return None
    return int(row["minimum_hour"])


def get_reservation_constraints_for_order(
    order_id: str,
    settings: Settings | None = None,
) -> tuple[int | None, date | None, tuple[int, ...] | None]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT minimum_hour, minimum_date, allowed_weekdays
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
    if row is None:
        return None, None, None
    minimum_hour = row["minimum_hour"]
    minimum_date = row["minimum_date"]
    allowed_weekdays = row["allowed_weekdays"]
    return (
        int(minimum_hour) if minimum_hour is not None else None,
        minimum_date if isinstance(minimum_date, date) else None,
        tuple(int(day) for day in allowed_weekdays) if allowed_weekdays else None,
    )


def list_active_orders(settings: Settings | None = None) -> list[ServiceOrderCandidate]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, wc.display_name AS contact_name,
                   so.priority, so.status, so.created_at, so.updated_at
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE so.status = 'ready'
            ORDER BY so.priority DESC, so.created_at ASC
            """
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_observer_orders(settings: Settings | None = None) -> list[ServiceOrderCandidate]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            WITH eligible_orders AS (
                SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                       pa.username, wc.display_name AS contact_name,
                       so.priority, so.status, so.created_at, so.updated_at,
                       os.last_run_at
                FROM service_orders so
                JOIN applicants a ON a.applicant_id = so.applicant_id
                JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
                LEFT JOIN applicant_contacts ac
                    ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
                LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
                LEFT JOIN order_state os ON os.order_id = so.order_id
                WHERE so.status = 'ready'
                  AND (os.next_allowed_at IS NULL OR os.next_allowed_at <= CURRENT_TIMESTAMP)
            ),
            active_block AS (
                SELECT *
                FROM eligible_orders
                ORDER BY priority DESC, created_at ASC
                LIMIT %s
            )
            SELECT order_id, name, username, contact_name, priority, status, created_at, updated_at
            FROM active_block
            ORDER BY last_run_at ASC NULLS FIRST, created_at ASC, priority DESC
            """,
            (settings.observer_active_order_limit,),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def promote_orders_matching_reserved_slot(
    details: dict[str, Any],
    *,
    excluded_order_id: str | None = None,
    settings: Settings | None = None,
) -> list[ServiceOrderCandidate]:
    settings = _settings(settings)
    init_database(settings)
    date_value, hour_value = appointment_datetime_details(details)
    date_text = str(date_value or "").strip()
    hour_text = str(hour_value or "").strip()
    if not date_text:
        return []

    now = _now()
    promoted_order_ids: list[str] = []
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT order_id, minimum_hour, minimum_date, allowed_weekdays, priority
            FROM service_orders
            WHERE status = 'ready'
              AND order_id <> COALESCE(%s, '')
              AND (
                  minimum_hour IS NOT NULL
                  OR minimum_date IS NOT NULL
                  OR allowed_weekdays IS NOT NULL
              )
            """,
            (excluded_order_id,),
        ).fetchall()
        if not rows:
            return []
        max_priority_row = connection.execute(
            """
            SELECT COALESCE(MAX(priority), 0) AS max_priority
            FROM service_orders
            WHERE status = 'ready'
            """
        ).fetchone()
        promoted_priority = int(max_priority_row["max_priority"]) + 1
        for row in rows:
            allowed_weekdays = row["allowed_weekdays"]
            constraints = ReservationConstraints(
                minimum_hour=(
                    int(row["minimum_hour"]) if row["minimum_hour"] is not None else None
                ),
                minimum_date=(
                    row["minimum_date"] if isinstance(row["minimum_date"], date) else None
                ),
                allowed_weekdays=(
                    tuple(int(day) for day in allowed_weekdays) if allowed_weekdays else None
                ),
            )
            is_allowed = appointment_filter_from_constraints(constraints)
            if not is_allowed(date_text, hour_text):
                continue
            if int(row["priority"]) >= promoted_priority:
                continue
            connection.execute(
                """
                UPDATE service_orders
                SET priority = %s, updated_at = %s
                WHERE order_id = %s AND status = 'ready'
                """,
                (promoted_priority, now, row["order_id"]),
            )
            promoted_order_ids.append(str(row["order_id"]))
        if not promoted_order_ids:
            return []
        promoted_rows = connection.execute(
            """
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, wc.display_name AS contact_name,
                   so.priority, so.status, so.created_at, so.updated_at
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE so.order_id = ANY(%s)
            ORDER BY so.priority DESC, so.created_at ASC
            """,
            (promoted_order_ids,),
        ).fetchall()
    return [_candidate_from_row(row) for row in promoted_rows]


def cleanup_expired_service_order_claims(settings: Settings | None = None) -> int:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE lease_owner IS NOT NULL
              AND lease_expires_at <= CURRENT_TIMESTAMP
            """
        )
        return cursor.rowcount


def claim_service_order(
    order_id: str,
    *,
    owner_token: str,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    """Atomically claim an eligible order for one worker."""
    if not owner_token.strip():
        raise ValueError("owner_token is required to claim a service order.")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be greater than zero.")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders AS so
            SET lease_owner = %s,
                lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE so.order_id = %s
              AND so.status = 'ready'
              AND (
                  so.lease_owner = %s
                  OR so.lease_expires_at IS NULL
                  OR so.lease_expires_at <= CURRENT_TIMESTAMP
              )
            """,
            (owner_token, lease_seconds, order_id, owner_token),
        )
        return bool(cursor.rowcount)


def release_service_order_claim(
    order_id: str,
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> bool:
    """Release a lease only when it is still owned by the caller."""
    if not owner_token.strip():
        return False
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_owner = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
              AND lease_owner = %s
            """,
            (order_id, owner_token),
        )
        return bool(cursor.rowcount)


def renew_service_order_claim(
    order_id: str,
    *,
    owner_token: str,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
              AND lease_owner = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (lease_seconds, order_id, owner_token),
        )
        return bool(cursor.rowcount)


def service_order_claim_owned(
    order_id: str,
    *,
    owner_token: str,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM service_orders
            WHERE order_id = %s
              AND status = 'ready'
              AND lease_owner = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (order_id, owner_token),
        ).fetchone()
        return row is not None


def _update_applicant_name_for_order(
    order_id: str,
    full_name: str,
    *,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> bool:
    full_name = " ".join(full_name.split())
    if not full_name:
        return False
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _operation_connection(settings, _connection_override) as connection:
        row = _service_order_identity(connection, order_id)
        if row is None:
            return False
        cursor = connection.execute(
            """
            UPDATE applicants
            SET full_name = %s, updated_at = %s
            WHERE applicant_id = %s
              AND (
                full_name IS NULL
                OR btrim(full_name) = ''
                OR btrim(full_name) <> %s
              )
            """,
            (full_name, now, row["applicant_id"], full_name),
        )
        return bool(cursor.rowcount)


def order_backoff_seconds(order_id: str, *, settings: Settings | None = None) -> int:
    row = _order_state_row(order_id, settings=settings)
    if row is None or not row["next_allowed_at"]:
        return 0
    try:
        next_allowed_at = datetime.fromisoformat(str(row["next_allowed_at"]))
    except ValueError:
        return 0
    return max(0, int((next_allowed_at - datetime.now(UTC)).total_seconds()))


def order_reservation_pending(order_id: str, *, settings: Settings | None = None) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM reservation_attempts
            WHERE order_id = %s AND status IN ('intent', 'pending', 'unknown')
            """,
            (order_id,),
        ).fetchone()
    if row is not None:
        return True
    state_row = _order_state_row(order_id, settings=settings)
    return state_row is not None and state_row["last_status"] in {
        OrderStateStatus.SUBMISSION_INTENT,
        OrderStateStatus.SUBMISSION_PENDING,
        OrderStateStatus.RESERVATION_UNCONFIRMED,
    }


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
            previous_payload.get("signature")
            if isinstance(previous_payload, dict)
            else None
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


def mark_order_submission_pending(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    _set_order_submission_state(
        order_id,
        OrderStateStatus.SUBMISSION_PENDING,
        "Se inicio el envio de una reserva; falta confirmar el resultado.",
        settings=settings,
    )


def mark_order_submission_intent(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    _set_order_submission_state(
        order_id,
        OrderStateStatus.SUBMISSION_INTENT,
        "Se detecto intencion de enviar una reserva.",
        settings=settings,
    )


def clear_order_submission_state(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE order_state
            SET last_status = NULL, last_message = NULL, next_allowed_at = NULL
            WHERE order_id = %s
            """,
            (order_id,),
        )


def order_submission_age_seconds(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> int | None:
    row = _order_state_row(order_id, settings=settings)
    if row is None or row["last_status"] not in {
        OrderStateStatus.SUBMISSION_INTENT,
        OrderStateStatus.SUBMISSION_PENDING,
        OrderStateStatus.RESERVATION_UNCONFIRMED,
    }:
        return None
    try:
        started_at = datetime.fromisoformat(str(row["last_run_at"]))
    except (TypeError, ValueError):
        return None
    return max(0, int((datetime.now(UTC) - started_at).total_seconds()))


def set_order_paused(order_id: str, paused: bool, *, settings: Settings | None = None) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = CASE WHEN %s THEN 'paused' ELSE 'ready' END,
                updated_at = %s
            WHERE order_id = %s
            """,
            (paused, now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        if not paused:
            connection.execute(
                """
                UPDATE order_state
                SET last_status = NULL, last_message = NULL, next_allowed_at = NULL,
                    consecutive_errors = 0, credential_failures = 0, programmed_at = NULL
                WHERE order_id = %s
                """,
                (order_id,),
            )


def record_invalid_credential_failure(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> tuple[int, bool]:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    message = "El portal rechazo la clave: clave incorrecta o cuenta no registrada."
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO order_state (
                order_id, last_status, last_message, consecutive_errors,
                credential_failures, last_run_at
            ) VALUES (%s, 'error', %s, 1, 1, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = 'error',
                last_message = excluded.last_message,
                consecutive_errors = order_state.consecutive_errors + 1,
                credential_failures = order_state.credential_failures + 1,
                next_allowed_at = NULL,
                last_run_at = excluded.last_run_at
            RETURNING credential_failures
            """,
            (order_id, message, now),
        ).fetchone()
        failures = int(row["credential_failures"])
        paused = failures >= 2
        if paused:
            cursor = connection.execute(
                """
                UPDATE service_orders
                SET status = 'paused', updated_at = %s
                WHERE order_id = %s
                """,
                (now, order_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"Service order not found: {order_id}")
    return failures, paused


def mark_order_done(
    order_id: str,
    *,
    status: str = "registered",
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    order_status = (
        "reserved_payment_pending" if status in {"registered", "programmed"} else "archived"
    )
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = %s, updated_at = %s
            WHERE order_id = %s
            """,
            (order_status, now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        connection.execute(
            """
            INSERT INTO order_state (order_id, programmed_at, last_status, last_run_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                programmed_at = excluded.programmed_at,
                last_status = excluded.last_status,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL,
                consecutive_errors = 0
            """,
            (order_id, now, status, now),
        )


def update_order_state(
    order_id: str,
    *,
    status: str,
    message: str,
    exit_code: int,
    backoff_seconds: int | None = None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    next_allowed_at = None
    if backoff_seconds is not None:
        next_allowed_at = (datetime.now(UTC) + timedelta(seconds=backoff_seconds)).isoformat(
            timespec="seconds"
        )
    is_error = exit_code != 0 or status in {
        ResultStatus.ERROR,
        ResultStatus.UNKNOWN,
        ResultStatus.RESERVATION_UNCONFIRMED,
    }
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO order_state (
                order_id, last_status, last_message, consecutive_errors, next_allowed_at,
                last_run_at, last_success_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                consecutive_errors = CASE
                    WHEN %s THEN order_state.consecutive_errors + 1
                    ELSE 0
                END,
                next_allowed_at = excluded.next_allowed_at,
                last_run_at = excluded.last_run_at,
                last_success_at = CASE
                    WHEN %s THEN order_state.last_success_at
                    ELSE excluded.last_success_at
                END
            """,
            (
                order_id,
                status,
                sanitize_text(message),
                1 if is_error else 0,
                next_allowed_at,
                now,
                None if is_error else now,
                is_error,
                is_error,
            ),
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
                   pa.username, pa.password, wc.display_name AS contact_name,
                   so.priority, so.status, so.created_at, so.updated_at
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
                   pa.username, pa.password, wc.display_name AS contact_name,
                   so.priority, so.status, so.created_at, so.updated_at
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


def _service_order_identity(connection: Connection, order_id: str) -> dict[str, Any] | None:
    return connection.execute(
        """
        SELECT order_id, applicant_id, portal_account_id
        FROM service_orders
        WHERE order_id = %s
        """,
        (order_id,),
    ).fetchone()


def _order_state_row(order_id: str, *, settings: Settings | None) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return connection.execute(
            """
            SELECT last_status, last_run_at, next_allowed_at
            FROM order_state
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()


def _set_order_submission_state(
    order_id: str,
    status: OrderStateStatus,
    message: str,
    *,
    settings: Settings | None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO order_state (order_id, last_status, last_message, last_run_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL
            """,
            (order_id, status, message, now),
        )


def _runtime_from_row(row: dict[str, Any], settings: Settings) -> ServiceOrderRuntime:
    return ServiceOrderRuntime(
        order_id=str(row["order_id"]),
        name=str(row["name"]),
        username=str(row["username"]),
        password=_credential_cipher(settings).decrypt(str(row["password"])),
        priority=int(row["priority"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        contact_name=row.get("contact_name"),
    )


def _candidate_from_row(row: dict[str, Any]) -> ServiceOrderCandidate:
    return ServiceOrderCandidate(
        order_id=str(row["order_id"]),
        name=str(row["name"]),
        username=str(row["username"]),
        priority=int(row["priority"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        contact_name=row.get("contact_name"),
    )


def _service_order_summary_from_row(row: dict[str, Any]) -> ServiceOrderSummary:
    return ServiceOrderSummary(
        order_id=str(row["order_id"]),
        applicant_id=str(row["applicant_id"]),
        applicant_name=row["full_name"],
        document_number_masked=_mask_username(str(row["document_number"])),
        contact_name=row["contact_name"],
        contact_whatsapp_masked=_mask_phone(row["contact_phone"]),
        contact_source=row["contact_source"],
        priority=int(row["priority"]),
        charge_required=bool(row["charge_required"]),
        status=str(row["status"]),
        reservation_status=row["reservation_status"],
        reservation_site=row["reservation_site"],
        reservation_date=row["reservation_date"],
        reservation_hour=row["reservation_hour"],
        payment_status=row["payment_status"],
        amount_agreed=_decimal_text(row["amount_agreed"]),
        amount_paid=_decimal_text(row["amount_paid"]),
        minimum_reservation_hour=(
            int(row["minimum_reservation_hour"])
            if row["minimum_reservation_hour"] is not None
            else None
        ),
        minimum_reservation_date=(
            row["minimum_reservation_date"].isoformat()
            if isinstance(row["minimum_reservation_date"], date)
            else (
                str(row["minimum_reservation_date"])
                if row["minimum_reservation_date"] is not None
                else None
            )
        ),
        allowed_weekdays=(
            tuple(int(day) for day in row["allowed_weekdays"])
            if row["allowed_weekdays"]
            else None
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _upsert_contact(
    connection: Connection,
    *,
    applicant_id: str,
    phone: str | None,
    display_name: str | None,
    source: str | None,
    now: str,
) -> str:
    normalized_phone = _normalize_phone(phone) if phone else None
    normalized_display_name = " ".join(str(display_name or "").split())
    normalized_source = " ".join(str(source or "").split()).lower()
    if not normalized_source:
        normalized_source = "whatsapp" if normalized_phone else "contact"
    if not normalized_phone and not normalized_display_name:
        raise ValueError("contact_whatsapp or contact_name is required.")
    contact_key = normalized_phone or f"{normalized_source}:{normalized_display_name}"
    contact_id = _id_from_value("contact", contact_key)
    if normalized_phone:
        existing_contact = connection.execute(
            "SELECT contact_id FROM whatsapp_contacts WHERE phone = %s",
            (normalized_phone,),
        ).fetchone()
        if existing_contact is not None:
            contact_id = str(existing_contact["contact_id"])
    connection.execute(
        """
        INSERT INTO whatsapp_contacts (
            contact_id, phone, display_name, contact_source, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(contact_id) DO UPDATE SET
            phone = COALESCE(excluded.phone, whatsapp_contacts.phone),
            display_name = COALESCE(
                NULLIF(excluded.display_name, ''),
                whatsapp_contacts.display_name
            ),
            contact_source = COALESCE(
                NULLIF(excluded.contact_source, ''),
                whatsapp_contacts.contact_source
            ),
            updated_at = excluded.updated_at
        """,
        (
            contact_id,
            normalized_phone,
            normalized_display_name or None,
            normalized_source,
            now,
            now,
        ),
    )
    connection.execute(
        """
        INSERT INTO applicant_contacts (
            applicant_id, contact_id, is_primary, created_at, updated_at
        )
        VALUES (%s, %s, true, %s, %s)
        ON CONFLICT(applicant_id, contact_id) DO UPDATE SET
            is_primary = true,
            updated_at = excluded.updated_at
        """,
        (applicant_id, contact_id, now, now),
    )
    connection.execute(
        """
        UPDATE applicant_contacts
        SET is_primary = false, updated_at = %s
        WHERE applicant_id = %s AND contact_id <> %s
        """,
        (now, applicant_id, contact_id),
    )
    return contact_id


