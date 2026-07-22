from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.models import (
    ServiceOrderCandidate,
)
from appointment_bot.core.rules import ReservationConstraints, appointment_filter_from_constraints
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _now,
    _parse_excluded_date_ranges,
    _settings,
    init_database,
)
from appointment_bot.services.detail_helpers import appointment_datetime_details

FOCUSED_PRIORITY_THRESHOLD = 100


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
) -> tuple[
    int | None,
    date | None,
    date | None,
    tuple[int, ...] | None,
    tuple[tuple[date, date], ...],
]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            """
            SELECT minimum_hour, minimum_date, maximum_date, allowed_weekdays,
                   excluded_date_ranges
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
    if row is None:
        return None, None, None, None, ()
    minimum_hour = row["minimum_hour"]
    minimum_date = row["minimum_date"]
    maximum_date = row["maximum_date"]
    allowed_weekdays = row["allowed_weekdays"]
    return (
        int(minimum_hour) if minimum_hour is not None else None,
        minimum_date if isinstance(minimum_date, date) else None,
        maximum_date if isinstance(maximum_date, date) else None,
        tuple(int(day) for day in allowed_weekdays) if allowed_weekdays else None,
        _parse_excluded_date_ranges(row["excluded_date_ranges"]),
    )


def list_active_orders(
    settings: Settings | None = None,
    *,
    include_constrained: bool = True,
    order_ids: Iterable[str] | None = None,
) -> list[ServiceOrderCandidate]:
    settings = _settings(settings)
    init_database(settings)
    filters = ["so.status = 'ready'"]
    params: list[object] = []
    if not include_constrained:
        filters.append(
            """
            so.minimum_hour IS NULL
            AND so.minimum_date IS NULL
            AND so.maximum_date IS NULL
            AND so.allowed_weekdays IS NULL
            AND so.excluded_date_ranges = '[]'::jsonb
            """
        )
    if order_ids is not None:
        order_id_values = [str(order_id) for order_id in order_ids]
        if not order_id_values:
            return []
        filters.append("so.order_id = ANY(%s)")
        params.append(order_id_values)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            f"""
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, pa.document_type, wc.display_name AS contact_name,
                   wc.phone AS contact_phone, wc.contact_source,
                   so.priority, so.status, so.created_at, so.updated_at,
                   so.parent_order_id, so.program_expediente, so.program_plate
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE {" AND ".join(filters)}
            ORDER BY so.priority DESC, so.created_at ASC
            """,
            params,
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
                       pa.username, pa.document_type, wc.display_name AS contact_name,
                       wc.phone AS contact_phone, wc.contact_source,
                       so.priority, so.status, so.created_at, so.updated_at,
                       so.parent_order_id, so.program_expediente, so.program_plate,
                       os.last_run_at,
                       (
                           so.minimum_hour IS NOT NULL
                           OR so.minimum_date IS NOT NULL
                           OR so.maximum_date IS NOT NULL
                           OR so.allowed_weekdays IS NOT NULL
                           OR so.excluded_date_ranges <> '[]'::jsonb
                       ) AS is_constrained
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
                ORDER BY
                    (priority >= %s) DESC,
                    CASE
                        WHEN priority >= %s THEN false
                        ELSE is_constrained
                    END ASC,
                    priority DESC,
                    created_at ASC
                LIMIT %s
            )
            SELECT order_id, name, username, document_type,
                   contact_name, contact_phone, contact_source,
                   priority, status, created_at, updated_at, parent_order_id,
                   program_expediente, program_plate
            FROM active_block
            ORDER BY last_run_at ASC NULLS FIRST, created_at ASC, priority DESC
            """,
            (
                FOCUSED_PRIORITY_THRESHOLD,
                FOCUSED_PRIORITY_THRESHOLD,
                settings.observer_active_order_limit,
            ),
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
            SELECT order_id, minimum_hour, minimum_date, maximum_date, allowed_weekdays,
                   excluded_date_ranges, priority
            FROM service_orders
            WHERE status = 'ready'
              AND order_id <> COALESCE(%s, '')
              AND (
                  minimum_hour IS NOT NULL
                  OR minimum_date IS NOT NULL
                  OR maximum_date IS NOT NULL
                  OR allowed_weekdays IS NOT NULL
                  OR excluded_date_ranges <> '[]'::jsonb
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
        promoted_priority = min(
            int(max_priority_row["max_priority"]) + 1,
            FOCUSED_PRIORITY_THRESHOLD - 1,
        )
        for row in rows:
            allowed_weekdays = row["allowed_weekdays"]
            constraints = ReservationConstraints(
                minimum_hour=(
                    int(row["minimum_hour"]) if row["minimum_hour"] is not None else None
                ),
                minimum_date=(
                    row["minimum_date"] if isinstance(row["minimum_date"], date) else None
                ),
                maximum_date=(
                    row["maximum_date"] if isinstance(row["maximum_date"], date) else None
                ),
                allowed_weekdays=(
                    tuple(int(day) for day in allowed_weekdays) if allowed_weekdays else None
                ),
                excluded_date_ranges=_parse_excluded_date_ranges(row["excluded_date_ranges"]),
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
                   pa.username, pa.document_type, wc.display_name AS contact_name,
                   wc.phone AS contact_phone, wc.contact_source,
                   so.priority, so.status, so.created_at, so.updated_at,
                   so.parent_order_id, so.program_expediente, so.program_plate
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


def _candidate_from_row(row: dict[str, Any]) -> ServiceOrderCandidate:
    return ServiceOrderCandidate(
        order_id=str(row["order_id"]),
        name=str(row["name"]),
        username=str(row["username"]),
        document_type=str(row["document_type"]),
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
