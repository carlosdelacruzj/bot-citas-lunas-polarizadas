from __future__ import annotations

from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.documents import normalize_document_type
from appointment_bot.core.models import (
    ServiceOrderRuntime,
)
from appointment_bot.core.service_packages import (
    SERVICE_PACKAGE_STANDARD,
)
from appointment_bot.db.common import (
    _connection,
    _credential_cipher,
    _database_url,
    _now,
    _settings,
    init_database,
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
        service_package=str(row.get("service_package") or SERVICE_PACKAGE_STANDARD),
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
