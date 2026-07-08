from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings, load_settings
from appointment_bot.domain import OrderStateStatus, ResultStatus, sanitize_details
from appointment_bot.services.credential_cipher import CredentialCipher
from appointment_bot.services.database_migrations import migrate_database
from appointment_bot.services.database_models import (
    RunDetail,
    RunRecord,
    RunSummary,
    ServiceOrderCandidate,
    ServiceOrderCreateResult,
    ServiceOrderRuntime,
    ServiceOrderSummary,
    WorkerState,
)
from appointment_bot.services.postgres_pool import pooled_connection
from appointment_bot.utils.sanitization import public_filename, sanitize_text

DEFAULT_RESERVATION_AMOUNT = Decimal("40.00")
APPOINTMENT_DATETIME_RE = re.compile(
    r"^\s*(?P<date>\d{1,2}/\d{1,2}/\d{4})(?:\s+(?P<hour>\d{1,2}:\d{2}))?\s*$"
)
_INITIALIZED_URLS: set[str] = set()
_INITIALIZATION_LOCK = threading.Lock()


def init_database(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    database_url = _database_url(settings)
    if database_url in _INITIALIZED_URLS:
        return

    with _INITIALIZATION_LOCK:
        if database_url in _INITIALIZED_URLS:
            return
        with _connection(database_url) as connection:
            migrate_database(connection)
        _INITIALIZED_URLS.add(database_url)


def create_service_order(
    *,
    document_number: str,
    password: str,
    priority: int = 0,
    contact_whatsapp: str | None = None,
    contact_name: str | None = None,
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
        if contact_whatsapp:
            contact_id = _upsert_whatsapp_contact(
                connection,
                applicant_id=applicant_id,
                phone=contact_whatsapp,
                display_name=contact_name,
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
    contact_whatsapp: str,
    contact_name: str | None = None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        row = _service_order_identity(connection, order_id)
        if row is None:
            raise ValueError(f"Service order not found: {order_id}")
        _upsert_whatsapp_contact(
            connection,
            applicant_id=str(row["applicant_id"]),
            phone=contact_whatsapp,
            display_name=contact_name,
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


def _record_reservation_for_order(
    order_id: str,
    report: object,
    *,
    confirmed: bool | None = None,
    settings: Settings | None = None,
    _connection_override: Connection | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = getattr(report, "details", None) or {}
    now = _now()
    run_id = getattr(report, "run_id", None)
    is_confirmed = (
        bool(getattr(report, "reservation_confirmed", False)) if confirmed is None else confirmed
    )
    appointment_date, appointment_hour = _appointment_datetime_details(details)
    status = "confirmed" if is_confirmed else "unconfirmed"
    reservation_id = _id_from_value("reservation", f"{order_id}-{run_id or now}")
    with _operation_connection(settings, _connection_override) as connection:
        order = connection.execute(
            """
            SELECT order_id, charge_required
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
        if order is None:
            return
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, order_id, run_id, status, site, appointment_date,
                appointment_hour, slots, evidence_path, details_json,
                reserved_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(reservation_id) DO UPDATE SET
                status = excluded.status,
                evidence_path = excluded.evidence_path,
                details_json = excluded.details_json,
                updated_at = excluded.updated_at
            """,
            (
                reservation_id,
                order_id,
                run_id,
                status,
                _detail_text(details, "sede"),
                appointment_date,
                appointment_hour,
                _detail_text(details, "cupos"),
                getattr(report, "screenshot_path", None),
                Jsonb(sanitize_details(details)) if details else None,
                now,
                now,
                now,
            ),
        )
        if status == "confirmed":
            no_charge = not bool(order["charge_required"])
            if not no_charge:
                connection.execute(
                    """
                    INSERT INTO payments (
                        payment_id, order_id, reservation_id, status, amount_agreed,
                        currency, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s, 'PEN', %s, %s)
                    ON CONFLICT(payment_id) DO NOTHING
                    """,
                    (
                        _id_from_value("payment", order_id),
                        order_id,
                        reservation_id,
                        DEFAULT_RESERVATION_AMOUNT,
                        now,
                        now,
                    ),
                )
            connection.execute(
                """
                UPDATE service_orders
                SET status = %s, updated_at = %s
                WHERE order_id = %s
                """,
                ("archived" if no_charge else "reserved_payment_pending", now, order_id),
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
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, wc.display_name AS contact_name,
                   so.priority, so.status, so.created_at, so.updated_at
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN order_state os ON os.order_id = so.order_id
            WHERE so.status = 'ready'
              AND (os.next_allowed_at IS NULL OR os.next_allowed_at <= CURRENT_TIMESTAMP)
            ORDER BY so.priority DESC, os.last_run_at ASC NULLS FIRST, so.created_at ASC
            """
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


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


def create_reservation_attempt(
    attempt_id: str,
    order_id: str,
    *,
    details: dict[str, Any] | None,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = sanitize_details(details) or {}
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO reservation_attempts (
                attempt_id, order_id, idempotency_key, status, site,
                appointment_date, appointment_hour, details_json, created_at, updated_at
            ) VALUES (%s, %s, %s, 'intent', %s, %s, %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO UPDATE SET
                details_json = COALESCE(reservation_attempts.details_json, excluded.details_json),
                updated_at = excluded.updated_at
            """,
            (
                attempt_id,
                order_id,
                attempt_id,
                _detail_text(details, "sede"),
                _detail_text(details, "fecha"),
                _detail_text(details, "hora"),
                Jsonb(details) if details else None,
                now,
                now,
            ),
        )


def mark_reservation_attempt_pending(
    attempt_id: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE reservation_attempts
            SET status = 'pending', submitted_at = COALESCE(submitted_at, %s), updated_at = %s
            WHERE attempt_id = %s AND status = 'intent'
            """,
            (now, now, attempt_id),
        )


def resolve_reservation_attempt(
    attempt_id: str,
    status: str,
    *,
    run_id: str | None = None,
    evidence_path: str | None = None,
    settings: Settings | None = None,
) -> None:
    if status not in {"confirmed", "rejected", "unknown"}:
        raise ValueError(f"Invalid reservation attempt status: {status}")
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    resolved_at = now if status in {"confirmed", "rejected"} else None
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE reservation_attempts
            SET status = %s, run_id = COALESCE(%s, run_id),
                evidence_path = COALESCE(%s, evidence_path),
                resolved_at = %s, updated_at = %s
            WHERE attempt_id = %s
              AND status IN ('intent', 'pending', 'unknown')
            """,
            (status, run_id, evidence_path, resolved_at, now, attempt_id),
        )


def get_active_reservation_attempt(
    order_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        return connection.execute(
            """
            SELECT attempt_id, status, site, appointment_date, appointment_hour
            FROM reservation_attempts
            WHERE order_id = %s AND status IN ('intent', 'pending', 'unknown')
            ORDER BY created_at DESC LIMIT 1
            """,
            (order_id,),
        ).fetchone()


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


def create_run_record(
    settings: Settings | None,
    record: RunRecord,
    screenshot_paths: Iterable[str],
    *,
    _connection_override: Connection | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = Jsonb(sanitize_details(record.details)) if record.details else None
    with _operation_connection(settings, _connection_override) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id, order_id, status, message, exit_code, started_at, finished_at,
                duration_seconds, reservation_attempted, reservation_confirmed, details_json,
                screenshot_path, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(run_id) DO UPDATE SET
                order_id = excluded.order_id,
                status = excluded.status,
                message = excluded.message,
                exit_code = excluded.exit_code,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at,
                duration_seconds = excluded.duration_seconds,
                reservation_attempted = excluded.reservation_attempted,
                reservation_confirmed = excluded.reservation_confirmed,
                details_json = excluded.details_json,
                screenshot_path = excluded.screenshot_path
            """,
            (
                record.run_id,
                record.order_id,
                record.status,
                sanitize_text(record.message),
                record.exit_code,
                record.started_at,
                record.finished_at,
                record.duration_seconds,
                record.reservation_attempted,
                record.reservation_confirmed,
                details,
                record.screenshot_path,
                _now(),
            ),
        )
        rows = [(record.run_id, path, _now()) for path in screenshot_paths]
        _executemany(
            connection,
            """
            INSERT INTO run_screenshots (run_id, path, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            rows,
        )


def record_run_outcome(
    settings: Settings | None,
    record: RunRecord,
    screenshot_paths: Iterable[str],
    *,
    report: object,
    person_name: str | None,
    include_reservation: bool,
) -> None:
    """Persist a run and its domain effects in one transaction."""
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        create_run_record(
            settings,
            record,
            screenshot_paths,
            _connection_override=connection,
        )
        if record.order_id and person_name:
            _update_applicant_name_for_order(
                record.order_id,
                person_name,
                settings=settings,
                _connection_override=connection,
            )
        if record.order_id and include_reservation:
            _record_reservation_for_order(
                record.order_id,
                report,
                confirmed=True,
                settings=settings,
                _connection_override=connection,
            )


def list_runs(
    *,
    limit: int = 50,
    offset: int = 0,
    order_id: str | None = None,
    status: str | None = None,
    settings: Settings | None = None,
) -> list[RunSummary]:
    settings = _settings(settings)
    init_database(settings)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    where, values = _run_filters(order_id=order_id, status=status)
    values.extend([limit, offset])
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            f"""
            SELECT r.run_id, r.order_id, r.status, r.message, r.exit_code, r.started_at,
                   r.finished_at, r.duration_seconds, r.reservation_attempted,
                   r.reservation_confirmed, r.screenshot_path, r.created_at,
                   COUNT(rs.id) AS screenshot_count
            FROM runs r
            LEFT JOIN run_screenshots rs ON rs.run_id = r.run_id
            {where}
            GROUP BY r.run_id
            ORDER BY r.started_at DESC
            LIMIT %s OFFSET %s
            """,
            values,
        ).fetchall()
    return [_run_summary_from_row(row) for row in rows]


def record_order_check(
    order_id: str,
    *,
    status: str,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO order_checks (order_id, status, checked_at)
            VALUES (%s, %s, %s)
            """,
            (order_id, status, _now()),
        )


def record_observer_window_metric(
    settings: Settings | None,
    *,
    metric_date: date,
    window_label: str,
    source: str,
    report: Any,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    details = getattr(report, "details", None) or {}
    status = str(getattr(report, "status", "") or "unknown")
    duration = _metric_duration_seconds(report, details)
    error_count = 1 if status in {"error", "unknown", "reservation_unconfirmed"} else 0
    now = _now()
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            INSERT INTO observer_window_metrics (
                metric_date, window_label, source, status, site, check_count,
                error_count, total_duration_seconds, first_seen_at, last_seen_at,
                last_order_id, last_date, last_hour
            )
            VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (metric_date, window_label, source, status, site)
            DO UPDATE SET
                check_count = observer_window_metrics.check_count + 1,
                error_count = observer_window_metrics.error_count + excluded.error_count,
                total_duration_seconds = (
                    observer_window_metrics.total_duration_seconds
                    + excluded.total_duration_seconds
                ),
                last_seen_at = excluded.last_seen_at,
                last_order_id = excluded.last_order_id,
                last_date = excluded.last_date,
                last_hour = excluded.last_hour
            """,
            (
                metric_date,
                window_label,
                source,
                status,
                _detail_text(details, "sede") or "",
                error_count,
                duration,
                now,
                now,
                getattr(report, "order_id", None),
                _detail_text(details, "fecha"),
                _detail_text(details, "hora"),
            ),
        )


def summarize_order_checks(
    order_id: str,
    *,
    started_at: datetime,
    finished_at: datetime,
    settings: Settings | None = None,
) -> tuple[int, datetime | None, datetime | None, str | None, datetime | None]:
    if finished_at <= started_at:
        return 0, None, None, None, None
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            WITH filtered_checks AS (
                SELECT status, checked_at
                FROM order_checks
                WHERE order_id = %s
                  AND checked_at >= %s
                  AND checked_at <= %s
            )
            SELECT COUNT(*) AS check_count,
                   MIN(checked_at) AS first_check_at,
                   MAX(checked_at) AS last_check_at,
                   (ARRAY_AGG(status ORDER BY checked_at DESC))[1] AS last_status,
                   (SELECT MIN(all_checks.checked_at) FROM order_checks all_checks)
                       AS tracking_started_at
            FROM filtered_checks
            """,
            (order_id, started_at, finished_at),
        ).fetchone()
    if row is None:
        return 0, None, None, None, None
    return (
        int(row["check_count"]),
        row["first_check_at"],
        row["tracking_started_at"],
        row["last_status"],
        row["last_check_at"],
    )


def _metric_duration_seconds(report: Any, details: dict[str, Any]) -> float:
    raw_value = (
        details.get("check_duration_seconds")
        or details.get("duration_seconds")
        or getattr(report, "duration_seconds", None)
        or 0
    )
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        return 0.0


def get_run(
    run_id: str,
    *,
    settings: Settings | None = None,
) -> RunDetail | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT r.run_id, r.order_id, r.status, r.message, r.exit_code, r.started_at,
                   r.finished_at, r.duration_seconds, r.reservation_attempted,
                   r.reservation_confirmed, r.details_json, r.screenshot_path, r.created_at,
                   COUNT(rs.id) AS screenshot_count
            FROM runs r
            LEFT JOIN run_screenshots rs ON rs.run_id = r.run_id
            WHERE r.run_id = %s
            GROUP BY r.run_id
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        screenshot_rows = connection.execute(
            """
            SELECT path
            FROM run_screenshots
            WHERE run_id = %s
            ORDER BY id ASC
            """,
            (run_id,),
        ).fetchall()
    return _run_detail_from_row(row, [str(item["path"]) for item in screenshot_rows])


def get_worker_state(settings: Settings | None = None) -> WorkerState:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT phase, paused, current_order_id, masked_account,
                   session_started_at, last_check_at, next_check_at,
                   confirmed_reservations, consecutive_errors, last_error,
                   availability_signature, owner_token, updated_at
            FROM worker_state
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        return WorkerState()
    return WorkerState(
        phase=str(row["phase"]),
        paused=bool(row["paused"]),
        current_order_id=row["current_order_id"],
        masked_account=row["masked_account"],
        session_started_at=_timestamp_text(row["session_started_at"]),
        last_check_at=_timestamp_text(row["last_check_at"]),
        next_check_at=_timestamp_text(row["next_check_at"]),
        confirmed_reservations=int(row["confirmed_reservations"]),
        consecutive_errors=int(row["consecutive_errors"]),
        last_error=row["last_error"],
        availability_signature=row["availability_signature"],
        owner_token=row["owner_token"],
        updated_at=_timestamp_text(row["updated_at"]),
    )


def acquire_worker_lease(
    owner_token: str,
    *,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE worker_state
            SET owner_token = %s,
                lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
              AND (
                  owner_token IS NULL
                  OR owner_token = %s
                  OR lease_expires_at IS NULL
                  OR lease_expires_at <= CURRENT_TIMESTAMP
              )
            """,
            (owner_token, lease_seconds, owner_token),
        )
        return bool(cursor.rowcount)


def renew_worker_lease(
    owner_token: str,
    *,
    lease_seconds: int,
    settings: Settings | None = None,
) -> bool:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE worker_state
            SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
              AND owner_token = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            """,
            (lease_seconds, owner_token),
        )
        return bool(cursor.rowcount)


def release_worker_lease(
    owner_token: str,
    *,
    settings: Settings | None = None,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            """
            UPDATE worker_state
            SET owner_token = NULL,
                lease_expires_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1 AND owner_token = %s
            """,
            (owner_token,),
        )


def update_worker_state(
    settings: Settings | None = None,
    *,
    expected_owner_token: str | None = None,
    **changes: Any,
) -> WorkerState:
    settings = _settings(settings)
    init_database(settings)
    allowed = {
        "phase",
        "paused",
        "current_order_id",
        "masked_account",
        "session_started_at",
        "last_check_at",
        "next_check_at",
        "confirmed_reservations",
        "consecutive_errors",
        "last_error",
        "availability_signature",
        "owner_token",
    }
    invalid = set(changes) - allowed
    if invalid:
        raise ValueError(f"Invalid worker state fields: {sorted(invalid)}")
    if not changes:
        return get_worker_state(settings)

    assignments = []
    values = []
    for key, value in changes.items():
        assignments.append(f"{key} = %s")
        values.append(value)
    assignments.append("updated_at = %s")
    values.append(_now())
    values.append(1)
    where = "id = %s"
    if expected_owner_token is not None:
        where += " AND owner_token = %s"
        values.append(expected_owner_token)
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            f"UPDATE worker_state SET {', '.join(assignments)} WHERE {where}",
            values,
        )
        if expected_owner_token is not None and cursor.rowcount != 1:
            raise RuntimeError("Worker state ownership changed during the update.")
    return get_worker_state(settings)


def cleanup_database_history(settings: Settings | None = None) -> None:
    settings = _settings(settings)
    init_database(settings)
    cutoff = (datetime.now(UTC) - timedelta(days=settings.cleanup_retention_days)).isoformat(
        timespec="seconds"
    )
    with _connection(_database_url(settings)) as connection:
        connection.execute("DELETE FROM runs WHERE created_at < %s", (cutoff,))
        connection.execute("DELETE FROM order_checks WHERE checked_at < %s", (cutoff,))


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


def _settings(settings: Settings | None) -> Settings:
    return settings or load_settings(require_login=False)


def _database_url(settings: Settings) -> str:
    if not settings.database_url:
        raise ValueError("APPOINTMENT_DATABASE_URL is required for PostgreSQL.")
    return settings.database_url


def _credential_cipher(settings: Settings) -> CredentialCipher:
    return CredentialCipher(settings.credential_encryption_keys)


@contextmanager
def _connection(database_url: str) -> Iterator[Connection]:
    with pooled_connection(database_url) as connection:
        yield connection


@contextmanager
def _operation_connection(
    settings: Settings,
    connection: Connection | None,
) -> Iterator[Connection]:
    if connection is not None:
        yield connection
        return
    with _connection(_database_url(settings)) as managed_connection:
        yield managed_connection


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


def _run_summary_from_row(row: dict[str, Any]) -> RunSummary:
    return RunSummary(
        run_id=str(row["run_id"]),
        order_id=row["order_id"],
        status=str(row["status"]),
        message=sanitize_text(str(row["message"])),
        exit_code=int(row["exit_code"]),
        started_at=str(row["started_at"]),
        finished_at=str(row["finished_at"]),
        duration_seconds=float(row["duration_seconds"]),
        reservation_attempted=bool(row["reservation_attempted"]),
        reservation_confirmed=bool(row["reservation_confirmed"]),
        screenshot_path=public_filename(row["screenshot_path"]),
        screenshot_count=int(row["screenshot_count"]),
        created_at=str(row["created_at"]),
    )


def _run_detail_from_row(row: dict[str, Any], screenshot_paths: list[str]) -> RunDetail:
    summary = _run_summary_from_row(row)
    details = row["details_json"]
    return RunDetail(
        **summary.__dict__,
        details=sanitize_details(details) if isinstance(details, dict) else None,
        screenshot_paths=[
            path
            for path in (public_filename(item) for item in screenshot_paths)
            if path is not None
        ],
    )


def _run_filters(*, order_id: str | None, status: str | None) -> tuple[str, list[Any]]:
    filters = []
    values: list[Any] = []
    if order_id:
        filters.append("r.order_id = %s")
        values.append(order_id)
    if status:
        filters.append("r.status = %s")
        values.append(status)
    if not filters:
        return "", values
    return "WHERE " + " AND ".join(filters), values


def _upsert_whatsapp_contact(
    connection: Connection,
    *,
    applicant_id: str,
    phone: str,
    display_name: str | None,
    now: str,
) -> str:
    normalized_phone = _normalize_phone(phone)
    if not normalized_phone:
        raise ValueError("contact_whatsapp is required.")
    contact_id = _id_from_value("whatsapp", normalized_phone)
    connection.execute(
        """
        INSERT INTO whatsapp_contacts (contact_id, phone, display_name, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(phone) DO UPDATE SET
            display_name = COALESCE(
                NULLIF(excluded.display_name, ''),
                whatsapp_contacts.display_name
            ),
            updated_at = excluded.updated_at
        """,
        (contact_id, normalized_phone, display_name, now, now),
    )
    contact_id = str(
        connection.execute(
            "SELECT contact_id FROM whatsapp_contacts WHERE phone = %s",
            (normalized_phone,),
        ).fetchone()["contact_id"]
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


def _executemany(connection: Connection, query: str, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def _id_from_value(prefix: str, value: str) -> str:
    normalized = value.strip().lower()
    safe = "".join(character for character in normalized if character.isalnum()) or "item"
    if safe == normalized and len(safe) <= 32:
        return f"{prefix}-{safe}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{safe[:15]}-{digest}"


def _normalize_phone(value: str) -> str:
    return "".join(character for character in value if character.isdigit() or character == "+")


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def _decimal_or_none(value: str | float | int | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _detail_text(details: dict[str, Any], key: str) -> str | None:
    value = details.get(key)
    if value in {None, ""}:
        return None
    return str(value)


def _appointment_datetime_details(details: dict[str, Any]) -> tuple[str | None, str | None]:
    date_text = _detail_text(details, "fecha")
    hour_text = _detail_text(details, "hora")
    if not date_text:
        return None, hour_text

    match = APPOINTMENT_DATETIME_RE.match(date_text)
    if match is None:
        return date_text, hour_text

    parsed_hour = match.group("hour")
    return match.group("date"), hour_text or parsed_hour


def _parse_minimum_reservation_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("minimum_reservation_date must use YYYY-MM-DD or DD/MM/YYYY.")


def _parse_allowed_weekdays(value: Iterable[int] | None) -> list[int] | None:
    if value is None:
        return None
    days = sorted({int(day) for day in value})
    if not days:
        return None
    invalid = [day for day in days if day < 1 or day > 7]
    if invalid:
        raise ValueError("allowed_weekdays must use ISO days from 1 to 7.")
    return days


def _mask_username(username: str) -> str:
    if not username:
        return ""
    if len(username) <= 3:
        return "***"
    return f"{username[:2]}***{username[-1]}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _timestamp_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
