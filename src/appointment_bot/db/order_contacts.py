from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from psycopg import Connection

from appointment_bot.config import Settings
from appointment_bot.core.contacts import (
    ContactValidationError,
    normalize_contact_name,
    normalize_contact_source,
    normalize_contact_whatsapp,
    normalize_contact_whatsapp_username,
)
from appointment_bot.core.models import (
    ServiceOrderSummary,
)
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _decimal_or_none,
    _decimal_text,
    _id_from_value,
    _mask_phone,
    _mask_username,
    _now,
    _settings,
    _timestamp_text,
    init_database,
)
from appointment_bot.db.remote_control_audit import (
    record_remote_control_audit_in_connection,
)
from appointment_bot.db.whatsapp_automation import enqueue_whatsapp_automation_job

ORDER_CLOSURE_REASONS = {
    "completed_by_us",
    "family_no_charge",
    "client_withdrew",
    "external_slot",
    "duplicate",
    "not_serviceable",
    "uncollectible",
}
NO_CHARGE_CLOSURE_REASONS = {
    "family_no_charge",
    "client_withdrew",
    "external_slot",
    "duplicate",
    "not_serviceable",
}


def list_service_order_summaries(
    settings: Settings | None = None,
) -> list[ServiceOrderSummary]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT so.order_id, so.applicant_id, a.full_name, a.document_number,
                   pa.document_type,
                   wc.display_name AS contact_name, wc.phone AS contact_phone,
                   wc.username AS contact_username,
                   wc.contact_source,
                   so.priority, so.charge_required, so.service_type,
                   so.reservation_price, so.status,
                   so.created_at, so.updated_at,
                   r.status AS reservation_status, r.site AS reservation_site,
                   r.appointment_date AS reservation_date, r.appointment_hour AS reservation_hour,
                   p.status AS payment_status,
                   CASE
                       WHEN so.charge_required
                       THEN COALESCE(p.amount_agreed, so.reservation_price)
                       ELSE NULL
                   END AS amount_agreed,
                   p.amount_paid,
                   wm.status AS whatsapp_message_status,
                   wm.sent_at AS whatsapp_message_sent_at,
                   CASE
                       WHEN EXISTS (
                           SELECT 1
                           FROM whatsapp_messages sent_wm
                           WHERE sent_wm.order_id = so.order_id
                             AND sent_wm.test_mode = false
                             AND sent_wm.status = 'sent'
                       ) THEN 'sent'
                       WHEN waj.review_resolution IS NOT NULL THEN 'resolved'
                       WHEN waj.status IS NOT NULL THEN waj.status
                       WHEN so.status = 'reserved_payment_pending'
                         AND r.status = 'confirmed'
                         AND p.status = 'pending'
                       THEN 'manual_required'
                       ELSE 'not_applicable'
                   END AS whatsapp_message_action_state,
                   wfm.status AS whatsapp_followup_status,
                   wfm.sent_at AS whatsapp_followup_sent_at,
                   CASE
                       WHEN EXISTS (
                           SELECT 1
                           FROM whatsapp_followup_messages sent_wfm
                           WHERE sent_wfm.order_id = so.order_id
                             AND sent_wfm.test_mode = false
                             AND sent_wfm.status = 'sent'
                       ) THEN 'sent'
                       WHEN wfaj.review_resolution IS NOT NULL THEN 'resolved'
                       WHEN wfaj.status IS NOT NULL THEN wfaj.status
                       ELSE 'not_applicable'
                   END AS whatsapp_followup_action_state,
                   so.parent_order_id, so.program_expediente, so.program_plate,
                   so.closure_reason, so.closure_note, so.closed_at,
                   so.minimum_hour AS minimum_reservation_hour,
                   so.minimum_date AS minimum_reservation_date,
                   so.maximum_date AS maximum_reservation_date,
                   so.allowed_weekdays,
                   so.excluded_date_ranges,
                   COALESCE(os.preflight_status, 'not_required') AS preflight_status,
                   os.preflight_message, os.preflight_started_at,
                   os.preflight_validated_at, os.preflight_details,
                   COALESCE(os.preflight_cycle, 0) AS preflight_cycle,
                   rnaj.registration_notice_type,
                   rnaj.status AS registration_notice_status,
                   rnaj.updated_at AS registration_notice_updated_at,
                   rnaj.error_message AS registration_notice_error
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN order_state os ON os.order_id = so.order_id
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
            LEFT JOIN LATERAL (
                SELECT status, sent_at
                FROM whatsapp_messages
                WHERE order_id = so.order_id AND test_mode = false
                ORDER BY prepared_at DESC
                LIMIT 1
            ) wm ON true
            LEFT JOIN LATERAL (
                SELECT status, sent_at
                FROM whatsapp_followup_messages
                WHERE order_id = so.order_id AND test_mode = false
                ORDER BY prepared_at DESC
                LIMIT 1
            ) wfm ON true
            LEFT JOIN whatsapp_automation_jobs waj
                ON waj.order_id = so.order_id
               AND waj.job_kind = 'reservation_album'
            LEFT JOIN whatsapp_automation_jobs wfaj
                ON wfaj.order_id = so.order_id
               AND wfaj.job_kind = 'post_payment_followup'
            LEFT JOIN LATERAL (
                SELECT registration_notice_type, status, updated_at, error_message
                FROM whatsapp_automation_jobs
                WHERE order_id = so.order_id
                  AND job_kind = 'registration_notice'
                ORDER BY preflight_cycle DESC, created_at DESC
                LIMIT 1
            ) rnaj ON true
            ORDER BY so.priority DESC, so.created_at ASC
            """
        ).fetchall()
    return [_service_order_summary_from_row(row) for row in rows]


def add_or_update_service_order_contact(
    order_id: str,
    *,
    contact_whatsapp: str | None = None,
    contact_whatsapp_username: str | None = None,
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
        current_contact = connection.execute(
            """
            SELECT wc.phone, wc.username, wc.display_name, wc.contact_source
            FROM applicant_contacts ac
            JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE ac.applicant_id = %s AND ac.is_primary = true
            LIMIT 1
            """,
            (str(row["applicant_id"]),),
        ).fetchone()
        _upsert_contact(
            connection,
            applicant_id=str(row["applicant_id"]),
            phone=contact_whatsapp
            if contact_whatsapp is not None
            else (current_contact["phone"] if current_contact is not None else None),
            username=contact_whatsapp_username
            if contact_whatsapp_username is not None
            else (current_contact["username"] if current_contact is not None else None),
            display_name=contact_name
            if contact_name is not None
            else (current_contact["display_name"] if current_contact is not None else None),
            source=contact_source
            if contact_source is not None
            else (current_contact["contact_source"] if current_contact is not None else None),
            now=now,
        )


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
    paid = _decimal_or_none(amount_paid)
    agreed = _decimal_or_none(amount_agreed)
    if paid is None or paid <= 0:
        raise ValueError("amount_paid must be a valid positive amount.")
    if agreed is None:
        agreed = paid
    if agreed < 0:
        raise ValueError("amount_agreed must be a valid non-negative amount.")
    normalized_reason = (difference_reason or "").strip()
    if paid < agreed and (not allow_difference or not normalized_reason):
        raise ValueError(
            "A lower final payment requires allow_difference=true and difference_reason."
        )
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        current = _lock_payment_state(connection, order_id)
        _validate_payment_snapshot(
            current,
            expected_payment_status=expected_payment_status,
            expected_amount_agreed=expected_amount_agreed,
            expected_amount_paid=expected_amount_paid,
        )
        if current["order_status"] != "reserved_payment_pending":
            raise ValueError("Service order is no longer pending payment.")
        if current["payment_status"] not in {None, "pending"}:
            raise ValueError("Payment is no longer pending.")
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
            SET status = 'paid',
                charge_required = true,
                closure_reason = 'completed_by_us',
                closed_at = COALESCE(closed_at, %s),
                updated_at = %s
            WHERE order_id = %s
            """,
            (now, now, order_id),
        )
        enqueue_whatsapp_automation_job(
            order_id,
            "post_payment_followup",
            settings=settings,
            _connection_override=connection,
        )
        return record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action="payment_paid",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            detail=(
                f"amount_agreed={agreed}; amount_paid={paid}; "
                f"difference_allowed={str(paid < agreed).lower()}; "
                f"difference_reason={normalized_reason or 'none'}; post_payment=queued"
            ),
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
    paid = _decimal_or_none(amount_paid)
    agreed = _decimal_or_none(amount_agreed)
    if paid is None or paid <= 0:
        raise ValueError("amount_paid must be a valid positive amount.")
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    with _connection(_database_url(settings)) as connection:
        current = _lock_payment_state(connection, order_id)
        _validate_payment_snapshot(
            current,
            expected_payment_status=expected_payment_status,
            expected_amount_agreed=expected_amount_agreed,
            expected_amount_paid=expected_amount_paid,
        )
        if current["order_status"] != "reserved_payment_pending":
            raise ValueError("Service order is no longer pending payment.")
        if current["payment_status"] not in {None, "pending"}:
            raise ValueError("Payment is no longer pending.")
        effective_agreed = agreed if agreed is not None else current["amount_agreed"]
        if effective_agreed is None or effective_agreed <= 0:
            raise ValueError("amount_agreed must be a valid positive amount.")
        if paid >= effective_agreed:
            raise ValueError(
                "A partial payment must remain below amount_agreed; use payment/paid instead."
            )
        previous_paid = current["amount_paid"] or 0
        if paid < previous_paid:
            raise ValueError("A partial payment cannot reduce the accumulated amount paid.")
        connection.execute(
            """
            INSERT INTO payments (
                payment_id, order_id, status, amount_agreed, amount_paid,
                currency, paid_at, created_at, updated_at
            )
            VALUES (%s, %s, 'pending', %s, %s, 'PEN', NULL, %s, %s)
            ON CONFLICT(payment_id) DO UPDATE SET
                status = 'pending',
                amount_agreed = excluded.amount_agreed,
                amount_paid = excluded.amount_paid,
                paid_at = NULL,
                updated_at = excluded.updated_at
            """,
            (
                _id_from_value("payment", order_id),
                order_id,
                effective_agreed,
                paid,
                now,
                now,
            ),
        )
        return record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action="payment_partial",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            detail=(
                f"amount_agreed={effective_agreed}; amount_paid={paid}; "
                "payment_status=pending; post_payment=not_queued"
            ),
        )


def _lock_payment_state(connection: Connection, order_id: str) -> dict[str, Any]:
    order = connection.execute(
        "SELECT status FROM service_orders WHERE order_id = %s FOR UPDATE",
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
    return {
        "order_status": order["status"],
        "payment_status": payment["status"] if payment is not None else None,
        "amount_agreed": payment["amount_agreed"] if payment is not None else None,
        "amount_paid": payment["amount_paid"] if payment is not None else None,
    }


def _validate_payment_snapshot(
    current: dict[str, Any],
    *,
    expected_payment_status: str | None,
    expected_amount_agreed: str | float | int | None,
    expected_amount_paid: str | float | int | None,
) -> None:
    if (
        expected_payment_status is not None
        and current["payment_status"] != expected_payment_status
    ):
        raise ValueError("Payment changed since it was reviewed.")
    for field, expected in (
        ("amount_agreed", expected_amount_agreed),
        ("amount_paid", expected_amount_paid),
    ):
        if expected is None:
            continue
        normalized_expected = _decimal_or_none(expected)
        if normalized_expected is None:
            raise ValueError("Expected payment amounts must be valid numbers.")
        current_value = current[field]
        if field == "amount_paid" and current_value is None:
            current_value = Decimal("0")
        if current_value != normalized_expected:
            raise ValueError("Payment amounts changed since they were reviewed.")


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
        connection.execute(
            """
            DELETE FROM payments
            WHERE order_id = %s AND status = 'pending'
            """,
            (order_id,),
        )


def close_service_order(
    order_id: str,
    *,
    closure_reason: str,
    closure_note: str | None = None,
    settings: Settings | None = None,
) -> None:
    closure_reason = closure_reason.strip().casefold().replace("-", "_")
    if closure_reason not in ORDER_CLOSURE_REASONS:
        raise ValueError(f"Unsupported closure reason: {closure_reason}")
    settings = _settings(settings)
    init_database(settings)
    now = _now()
    note = _optional_clean_text(closure_note)
    charge_required = closure_reason not in NO_CHARGE_CLOSURE_REASONS
    order_status = "paid" if closure_reason == "completed_by_us" else "archived"
    with _connection(_database_url(settings)) as connection:
        cursor = connection.execute(
            """
            UPDATE service_orders
            SET status = %s,
                charge_required = %s,
                closure_reason = %s,
                closure_note = %s,
                closed_at = %s,
                updated_at = %s,
                lease_owner = NULL,
                lease_expires_at = NULL
            WHERE order_id = %s
            """,
            (order_status, charge_required, closure_reason, note, now, now, order_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"Service order not found: {order_id}")
        if closure_reason == "uncollectible":
            connection.execute(
                """
                UPDATE payments
                SET status = 'written_off', updated_at = %s
                WHERE order_id = %s AND status = 'pending'
                """,
                (now, order_id),
            )
        elif not charge_required:
            connection.execute(
                """
                DELETE FROM payments
                WHERE order_id = %s AND status = 'pending'
                """,
                (order_id,),
            )
        connection.execute(
            """
            INSERT INTO order_state (
                order_id, programmed_at, last_status, last_message, last_run_at
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT(order_id) DO UPDATE SET
                programmed_at = excluded.programmed_at,
                last_status = excluded.last_status,
                last_message = excluded.last_message,
                last_run_at = excluded.last_run_at,
                next_allowed_at = NULL,
                consecutive_errors = 0
            """,
            (order_id, now, "completed", closure_reason, now),
        )


def _service_order_identity(connection: Connection, order_id: str) -> dict[str, Any] | None:
    return connection.execute(
        """
        SELECT order_id, applicant_id, portal_account_id
        FROM service_orders
        WHERE order_id = %s
        """,
        (order_id,),
    ).fetchone()


def _service_order_summary_from_row(row: dict[str, Any]) -> ServiceOrderSummary:
    return ServiceOrderSummary(
        order_id=str(row["order_id"]),
        applicant_id=str(row["applicant_id"]),
        applicant_name=row["full_name"],
        document_number=str(row["document_number"]),
        document_number_masked=_mask_username(str(row["document_number"])),
        document_type=str(row["document_type"]),
        contact_name=row["contact_name"],
        contact_whatsapp=row["contact_phone"],
        contact_whatsapp_masked=_mask_phone(row["contact_phone"]),
        contact_whatsapp_username=row["contact_username"],
        contact_whatsapp_username_masked=_mask_whatsapp_username(row["contact_username"]),
        contact_source=row["contact_source"],
        priority=int(row["priority"]),
        charge_required=bool(row["charge_required"]),
        service_type=str(row["service_type"]),
        reservation_price=_decimal_text(row["reservation_price"]) or "50.00",
        status=str(row["status"]),
        reservation_status=row["reservation_status"],
        reservation_site=row["reservation_site"],
        reservation_date=row["reservation_date"],
        reservation_hour=row["reservation_hour"],
        payment_status=row["payment_status"],
        amount_agreed=_decimal_text(row["amount_agreed"]),
        amount_paid=_decimal_text(row["amount_paid"]),
        whatsapp_message_status=row["whatsapp_message_status"],
        whatsapp_message_sent_at=_timestamp_text(row["whatsapp_message_sent_at"]),
        whatsapp_message_action_state=str(row["whatsapp_message_action_state"]),
        whatsapp_followup_status=row["whatsapp_followup_status"],
        whatsapp_followup_sent_at=_timestamp_text(row["whatsapp_followup_sent_at"]),
        whatsapp_followup_action_state=str(row["whatsapp_followup_action_state"]),
        parent_order_id=row["parent_order_id"],
        program_expediente=row["program_expediente"],
        program_plate=row["program_plate"],
        closure_reason=row["closure_reason"],
        closure_note=row["closure_note"],
        closed_at=_timestamp_text(row["closed_at"]),
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
        maximum_reservation_date=(
            row["maximum_reservation_date"].isoformat()
            if isinstance(row["maximum_reservation_date"], date)
            else (
                str(row["maximum_reservation_date"])
                if row["maximum_reservation_date"] is not None
                else None
            )
        ),
        allowed_weekdays=(
            tuple(int(day) for day in row["allowed_weekdays"]) if row["allowed_weekdays"] else None
        ),
        excluded_date_ranges=tuple(
            {
                "start_date": str(item["start_date"]),
                "end_date": str(item["end_date"]),
            }
            for item in (row["excluded_date_ranges"] or [])
            if isinstance(item, dict) and item.get("start_date") and item.get("end_date")
        ),
        preflight_status=str(row["preflight_status"]),
        preflight_message=row["preflight_message"],
        preflight_started_at=_timestamp_text(row["preflight_started_at"]),
        preflight_validated_at=_timestamp_text(row["preflight_validated_at"]),
        preflight_details=(
            row["preflight_details"] if isinstance(row["preflight_details"], dict) else None
        ),
        preflight_cycle=int(row["preflight_cycle"]),
        registration_notice_type=row["registration_notice_type"],
        registration_notice_status=row["registration_notice_status"],
        registration_notice_updated_at=_timestamp_text(
            row["registration_notice_updated_at"]
        ),
        registration_notice_error=_registration_notice_error(
            row["registration_notice_error"]
        ),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _optional_clean_text(value: object) -> str | None:
    if value in {None, ""}:
        return None
    text = " ".join(str(value).split())
    return text or None


def _registration_notice_error(value: object) -> str | None:
    if value in {None, ""}:
        return None
    text = str(value)
    if "role=\"dialog\"" in text and "intercepts pointer events" in text:
        return (
            "Un dialogo de WhatsApp bloqueo la apertura del chat. "
            "No se confirmo el aviso de registro."
        )
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) <= 320:
        return first_line or None
    return f"{first_line[:317]}..."


def _upsert_contact(
    connection: Connection,
    *,
    applicant_id: str,
    phone: str | None,
    username: str | None,
    display_name: str | None,
    source: str | None,
    now: str,
) -> str:
    normalized_phone = normalize_contact_whatsapp(phone)
    normalized_username = normalize_contact_whatsapp_username(username)
    normalized_display_name = normalize_contact_name(display_name)
    normalized_source = normalize_contact_source(source)
    if not normalized_source:
        raise ContactValidationError(
            "contact_source",
            "La fuente de contacto es obligatoria.",
        )
    if not normalized_phone and not normalized_username and not normalized_display_name:
        raise ValueError("contact_whatsapp, contact_whatsapp_username or contact_name is required.")
    contact_key = normalized_phone
    if contact_key is None and normalized_username is not None:
        contact_key = normalized_username.casefold()
    if contact_key is None:
        contact_key = f"{normalized_source}:{normalized_display_name}"
    contact_id = _id_from_value("contact", contact_key)
    if normalized_phone:
        existing_contact = connection.execute(
            "SELECT contact_id FROM whatsapp_contacts WHERE phone = %s",
            (normalized_phone,),
        ).fetchone()
        if existing_contact is not None:
            contact_id = str(existing_contact["contact_id"])
    elif normalized_username:
        existing_contact = connection.execute(
            "SELECT contact_id FROM whatsapp_contacts WHERE lower(username) = lower(%s)",
            (normalized_username,),
        ).fetchone()
        if existing_contact is not None:
            contact_id = str(existing_contact["contact_id"])
    connection.execute(
        """
        INSERT INTO whatsapp_contacts (
            contact_id, phone, username, display_name, contact_source, created_at, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(contact_id) DO UPDATE SET
            phone = COALESCE(excluded.phone, whatsapp_contacts.phone),
            username = COALESCE(excluded.username, whatsapp_contacts.username),
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
            normalized_username,
            normalized_display_name,
            normalized_source,
            now,
            now,
        ),
    )
    connection.execute(
        """
        UPDATE applicant_contacts
        SET is_primary = false, updated_at = %s
        WHERE applicant_id = %s AND contact_id <> %s AND is_primary = true
        """,
        (now, applicant_id, contact_id),
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


def _mask_whatsapp_username(value: object) -> str | None:
    if value is None:
        return None
    username = str(value)
    if len(username) <= 4:
        return username[0] + "***"
    return f"{username[:3]}***{username[-2:]}"
