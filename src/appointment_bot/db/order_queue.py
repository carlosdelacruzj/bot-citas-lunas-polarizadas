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
from appointment_bot.core.rules import (
    ReservationConstraints,
    appointment_filter_from_constraints,
)
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _parse_excluded_date_ranges,
    _settings,
    init_database,
)


def get_reservation_constraints_for_order(
    order_id: str,
    settings: Settings | None = None,
) -> tuple[
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
            SELECT minimum_date, maximum_date, allowed_weekdays,
                   excluded_date_ranges
            FROM service_orders
            WHERE order_id = %s
            """,
            (order_id,),
        ).fetchone()
    if row is None:
        return None, None, None, ()
    minimum_date = row["minimum_date"]
    maximum_date = row["maximum_date"]
    allowed_weekdays = row["allowed_weekdays"]
    return (
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
            so.minimum_date IS NULL
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
                   wc.phone AS contact_phone, wc.username AS contact_username,
                   wc.contact_source,
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
                       wc.phone AS contact_phone, wc.username AS contact_username,
                       wc.contact_source,
                       so.priority, so.status, so.created_at, so.updated_at,
                       so.parent_order_id, so.program_expediente, so.program_plate,
                       os.last_run_at,
                       (
                           CASE WHEN so.minimum_date IS NULL THEN 0 ELSE 1 END
                           + CASE WHEN so.maximum_date IS NULL THEN 0 ELSE 1 END
                           + CASE
                               WHEN so.allowed_weekdays IS NULL
                                   OR cardinality(so.allowed_weekdays) = 0
                               THEN 0
                               ELSE 7 - cardinality(so.allowed_weekdays)
                             END
                           + COALESCE(
                               jsonb_array_length(so.excluded_date_ranges),
                               0
                             )
                       ) AS constraint_penalty
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
                               parent_order_id IS NULL,
                               constraint_penalty ASC,
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
                   contact_name, contact_phone, contact_username, contact_source,
                   priority, status, created_at, updated_at, parent_order_id,
                   program_expediente, program_plate
            FROM active_block
            ORDER BY parent_order_id IS NULL, last_run_at ASC NULLS FIRST,
                     created_at ASC, priority DESC
            """,
            (
                EXCLUSIVE_PRIORITY_THRESHOLD,
                settings.observer_active_order_limit,
            ),
        ).fetchall()
    return [_candidate_from_row(row) for row in rows]


def list_compatible_orders_for_opportunities(
    opportunities: Iterable[tuple[str, str]],
    *,
    exclude_order_ids: Iterable[str] = (),
    limit: int | None = None,
    settings: Settings | None = None,
) -> list[ServiceOrderCandidate]:
    if limit is not None and limit <= 0:
        return []
    unique_opportunities = tuple(
        dict.fromkeys(
            (str(date_text).strip(), str(hour_text).strip())
            for date_text, hour_text in opportunities
            if str(date_text).strip()
        )
    )
    if not unique_opportunities:
        return []
    settings = _settings(settings)
    init_database(settings)
    excluded = {str(order_id) for order_id in exclude_order_ids}
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT so.order_id, COALESCE(NULLIF(a.full_name, ''), a.document_number) AS name,
                   pa.username, pa.document_type, wc.display_name AS contact_name,
                   wc.phone AS contact_phone, wc.username AS contact_username, wc.contact_source,
                   so.priority, so.status, so.created_at, so.updated_at,
                   so.parent_order_id, so.program_expediente, so.program_plate,
                   so.minimum_date, so.maximum_date,
                   so.allowed_weekdays, so.excluded_date_ranges
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            JOIN portal_accounts pa ON pa.portal_account_id = so.portal_account_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN order_state os ON os.order_id = so.order_id
            WHERE so.status = 'ready'
              AND (os.next_allowed_at IS NULL OR os.next_allowed_at <= CURRENT_TIMESTAMP)
              AND NOT EXISTS (
                  SELECT 1
                  FROM reservation_attempts ra
                  WHERE ra.order_id = so.order_id
                    AND ra.status IN ('intent', 'pending', 'unknown')
              )
            ORDER BY so.priority DESC, so.created_at ASC
            """
        ).fetchall()

    ranked: list[tuple[tuple[object, ...], ServiceOrderCandidate]] = []
    for row in rows:
        order_id = str(row["order_id"])
        if order_id in excluded:
            continue
        is_allowed = appointment_filter_from_constraints(
            ReservationConstraints(
                minimum_date=(
                    row["minimum_date"]
                    if isinstance(row["minimum_date"], date)
                    else None
                ),
                maximum_date=(
                    row["maximum_date"]
                    if isinstance(row["maximum_date"], date)
                    else None
                ),
                allowed_weekdays=(
                    tuple(int(day) for day in row["allowed_weekdays"])
                    if row["allowed_weekdays"]
                    else None
                ),
                excluded_date_ranges=_parse_excluded_date_ranges(
                    row["excluded_date_ranges"]
                ),
            )
        )
        compatibility_count = sum(
            is_allowed(appointment_date, appointment_hour)
            for appointment_date, appointment_hour in unique_opportunities
        )
        if compatibility_count == 0:
            continue
        constraint_penalty = _constraint_penalty(row)
        priority = int(row["priority"])
        ranked.append(
            (
                (
                    priority < EXCLUSIVE_PRIORITY_THRESHOLD,
                    row.get("parent_order_id") is None,
                    -compatibility_count,
                    constraint_penalty,
                    -priority,
                    str(row["created_at"]),
                ),
                _candidate_from_row(row),
            )
        )
    ranked.sort(key=lambda item: item[0])
    compatible = [candidate for _, candidate in ranked]
    return compatible[:limit] if limit is not None else compatible


def _constraint_penalty(row: dict[str, Any]) -> int:
    allowed_weekdays = row.get("allowed_weekdays") or ()
    return (
        int(row.get("minimum_date") is not None)
        + int(row.get("maximum_date") is not None)
        + (7 - len(allowed_weekdays) if allowed_weekdays else 0)
        + len(_parse_excluded_date_ranges(row.get("excluded_date_ranges")))
    )


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
        contact_whatsapp_username=row.get("contact_username"),
        contact_source=row.get("contact_source"),
        parent_order_id=row.get("parent_order_id"),
        program_expediente=row.get("program_expediente"),
        program_plate=row.get("program_plate"),
    )
