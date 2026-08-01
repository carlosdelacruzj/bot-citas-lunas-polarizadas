from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database


def create_registration_contact(
    *,
    whatsapp_phone: str,
    display_name: str | None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    phone = _normalize_peru_phone(whatsapp_phone)
    name = _normalize_optional_name(display_name)
    contact_ref = str(uuid4())
    now = datetime.now(UTC)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            INSERT INTO hosted_registration_contacts (
                contact_ref, whatsapp_phone, display_name, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
            """,
            (contact_ref, phone, name, now, now),
        ).fetchone()
    return dict(row)


def attach_invitation(
    contact_ref: str,
    invitation_id: str,
    *,
    state: str = "issued",
    settings: Settings | None = None,
) -> None:
    _update_contact(
        contact_ref,
        settings=settings,
        invitation_id=invitation_id,
        state=state,
        last_error_category=None,
    )


def replace_invitation(
    previous_invitation_id: str,
    invitation_id: str,
    *,
    contact_ref: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    lookup_column = "contact_ref" if contact_ref else "invitation_id"
    lookup_value = contact_ref or previous_invitation_id
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            f"""
            UPDATE hosted_registration_contacts
            SET invitation_id = %s,
                request_id = NULL,
                order_id = NULL,
                state = 'issued',
                availability_mode = NULL,
                last_error_category = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE {lookup_column} = %s
            RETURNING *
            """,
            (invitation_id, lookup_value),
        ).fetchone()
    if row is None:
        raise ValueError("La invitación anterior no está vinculada a un contacto local.")
    return dict(row)


def update_registration_contact_name(
    contact_ref: str,
    display_name: str | None,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    name = _normalize_optional_name(display_name)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE hosted_registration_contacts
            SET display_name = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE contact_ref = %s
            RETURNING *
            """,
            (name, contact_ref),
        ).fetchone()
    if row is None:
        raise ValueError("The hosted contact reference is not available locally.")
    return dict(row)


def record_claim(
    contact_ref: str,
    request_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE hosted_registration_contacts
            SET request_id = COALESCE(request_id, %s),
                state = CASE
                    WHEN state IN (
                        'accepted', 'awaiting_restrictions',
                        'credentials_invalid', 'rejected'
                    ) THEN state
                    ELSE 'leased'
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE contact_ref = %s
              AND (request_id IS NULL OR request_id = %s)
            RETURNING *
            """,
            (request_id, contact_ref, request_id),
        ).fetchone()
    if row is None:
        raise ValueError("The hosted contact reference is not available locally.")
    return dict(row)


def complete_local_registration(
    contact_ref: str,
    *,
    request_id: str,
    state: str,
    availability_mode: str | None = None,
    order_id: str | None = None,
    error_category: str | None = None,
    settings: Settings | None = None,
) -> None:
    _update_contact(
        contact_ref,
        settings=settings,
        request_id=request_id,
        state=state,
        availability_mode=availability_mode,
        order_id=order_id,
        last_error_category=error_category,
    )


def list_registration_contacts(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT contact_ref, whatsapp_phone, display_name, invitation_id,
                   request_id, order_id, state, availability_mode,
                   last_error_category, created_at, updated_at
            FROM hosted_registration_contacts
            ORDER BY created_at DESC
            LIMIT 200
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_registration_contact(
    contact_ref: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT * FROM hosted_registration_contacts WHERE contact_ref = %s",
            (contact_ref,),
        ).fetchone()
    return dict(row) if row else None


def update_registration_after_preflight(
    order_id: str,
    *,
    state: str,
    error_category: str | None = None,
    settings: Settings | None = None,
) -> bool:
    if state not in {"accepted", "credentials_invalid", "retry_wait"}:
        raise ValueError(f"Unsupported hosted registration state: {state}")
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            UPDATE hosted_registration_contacts
            SET state = %s,
                last_error_category = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
              AND state IN ('awaiting_restrictions', 'retry_wait', 'credentials_invalid')
            RETURNING contact_ref
            """,
            (state, error_category, order_id),
        ).fetchone()
    return row is not None


def _update_contact(
    contact_ref: str,
    *,
    settings: Settings | None,
    **values: Any,
) -> None:
    settings = _settings(settings)
    init_database(settings)
    allowed = {
        "invitation_id",
        "request_id",
        "order_id",
        "state",
        "availability_mode",
        "last_error_category",
    }
    invalid = set(values) - allowed
    if invalid:
        raise ValueError(f"Unsupported registration fields: {sorted(invalid)}")
    assignments = [f"{key} = %s" for key in values]
    parameters = list(values.values())
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    parameters.append(contact_ref)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            f"""
            UPDATE hosted_registration_contacts
            SET {", ".join(assignments)}
            WHERE contact_ref = %s
            RETURNING contact_ref
            """,
            tuple(parameters),
        ).fetchone()
    if row is None:
        raise ValueError("The hosted contact reference is not available locally.")


def _normalize_peru_phone(value: str) -> str:
    digits = "".join(character for character in value if character.isdigit())
    if digits.startswith("51") and len(digits) == 11:
        digits = digits[2:]
    if len(digits) != 9 or not digits.startswith("9"):
        raise ValueError("whatsapp_phone must be a valid 9-digit Peru mobile number.")
    return f"+51{digits}"


def _normalize_optional_name(value: str | None) -> str | None:
    name = " ".join((value or "").split())
    if len(name) > 120:
        raise ValueError("display_name must not exceed 120 characters.")
    return name or None
