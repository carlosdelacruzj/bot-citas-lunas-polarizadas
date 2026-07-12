from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.core.models import RunDetail, RunRecord, RunSummary
from appointment_bot.core.statuses import sanitize_details
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _detail_text,
    _executemany,
    _now,
    _operation_connection,
    _settings,
    init_database,
)
from appointment_bot.db.orders import _update_applicant_name_for_order
from appointment_bot.db.reservations import _record_reservation_for_order
from appointment_bot.utils.sanitization import public_filename, sanitize_text


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


def list_run_details_between(
    *,
    started_at: datetime,
    finished_at: datetime,
    settings: Settings | None = None,
) -> list[RunDetail]:
    settings = _settings(settings)
    init_database(settings)
    with _connection(_database_url(settings)) as connection:
        rows = connection.execute(
            """
            SELECT r.run_id, r.order_id, r.status, r.message, r.exit_code, r.started_at,
                   r.finished_at, r.duration_seconds, r.reservation_attempted,
                   r.reservation_confirmed, r.details_json, r.screenshot_path, r.created_at,
                   COUNT(rs.id) AS screenshot_count,
                   ARRAY_REMOVE(ARRAY_AGG(rs.path ORDER BY rs.id), NULL) AS screenshot_paths
            FROM runs r
            LEFT JOIN run_screenshots rs ON rs.run_id = r.run_id
            WHERE r.finished_at >= %s AND r.finished_at < %s
            GROUP BY r.run_id
            ORDER BY r.started_at ASC
            """,
            (started_at, finished_at),
        ).fetchall()
    return [
        _run_detail_from_row(row, [str(path) for path in row["screenshot_paths"]]) for row in rows
    ]


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
