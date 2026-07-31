from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from appointment_bot.config import Settings
from appointment_bot.core.models import (
    ServiceOrderCandidate,
)
from appointment_bot.core.order_priority import (
    EXCLUSIVE_PRIORITY_THRESHOLD,
)
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _parse_excluded_date_ranges,
    _settings,
    init_database,
)


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
            ranked_orders AS (
                SELECT *,
                       MAX(priority) OVER () >= %s AS has_exclusive_order,
                       ROW_NUMBER() OVER (
                           ORDER BY
                               priority DESC,
                               created_at ASC
                       ) AS selection_rank
                FROM eligible_orders
            ),
            active_block AS (
                SELECT *
                FROM ranked_orders
                WHERE
                    (has_exclusive_order AND selection_rank = 1)
                    OR (NOT has_exclusive_order AND selection_rank <= %s)
            )
            SELECT order_id, name, username, document_type,
                   contact_name, contact_phone, contact_source,
                   priority, status, created_at, updated_at, parent_order_id,
                   program_expediente, program_plate
            FROM active_block
            ORDER BY last_run_at ASC NULLS FIRST, created_at ASC, priority DESC
            """,
            (
                EXCLUSIVE_PRIORITY_THRESHOLD,
                settings.observer_active_order_limit,
            ),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


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
