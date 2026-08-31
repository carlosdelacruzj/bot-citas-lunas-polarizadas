from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from appointment_bot.config import OPPORTUNITY_BURST_SESSION_LIMIT, Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)
from appointment_bot.utils.sanitization import sanitize_text

_BURST_STATUSES = {"closed", "aborted"}
_EXECUTION_ROLES = {"detector", "auxiliary"}
_EVENT_TYPES = {
    "started",
    "slot_lost_resolved",
    "observation",
    "second_attempt_intent",
    "second_attempt_resolved",
    "finished",
}
_TIMING_KEYS = {
    "available_detected_at_lima",
    "reservation_finished_at_lima",
    "total_from_available_seconds",
    "selection_seconds",
    "captcha_image_seconds",
    "captcha_solver_seconds",
    "captcha_fill_to_click_seconds",
    "click_to_portal_response_seconds",
    "click_to_confirmation_screenshot_seconds",
    "post_confirmation_seconds",
    "marks_lima",
}
_CONFIG_KEYS = {
    "max_sessions",
    "max_clients",
    "max_seconds",
    "session_seconds",
    "attempts",
    "reload_probe_after_attempt",
    "slot_lost_reobservation_seconds",
    "slot_lost_reobservation_attempts",
    "slot_lost_reobservation_reload_probe_after_attempt",
}
_OBSERVATION_KEYS = {"attempt", "mode", "status", "selected_status", "duration_seconds"}
_REOBSERVATION_KEYS = {
    "max_seconds",
    "max_attempts",
    "attempts_completed",
    "reload_probe_used",
    "elapsed_seconds",
    "outcome",
    "recovered_availability",
}


def create_opportunity_burst(
    *,
    detector_order_id: str,
    started_at: datetime | str,
    admission_deadline_at: datetime | str,
    opportunities: Iterable[Mapping[str, Any] | tuple[str, str]],
    configured_max_sessions: int,
    configured_max_clients: int,
    config: Mapping[str, Any] | None = None,
    detector_run_id: str | None = None,
    burst_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    if not 1 <= configured_max_sessions <= OPPORTUNITY_BURST_SESSION_LIMIT:
        raise ValueError(
            "configured_max_sessions must be between 1 and "
            f"{OPPORTUNITY_BURST_SESSION_LIMIT}."
        )
    if configured_max_clients < 0:
        raise ValueError("configured_max_clients must be non-negative.")
    identifier = burst_id or f"burst-{uuid4().hex}"
    safe_opportunities = _safe_opportunities(opportunities)
    safe_config = _allowlisted_mapping(config or {}, _CONFIG_KEYS)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        connection.execute(
            """
            INSERT INTO opportunity_bursts (
                burst_id, detector_order_id, detector_run_id, status,
                started_at, admission_deadline_at, opportunities_json,
                config_json, configured_max_sessions, configured_max_clients,
                max_active_sessions
            )
            VALUES (%s, %s, %s, 'running', %s, %s, %s, %s, %s, %s, 1)
            ON CONFLICT (burst_id) DO NOTHING
            """,
            (
                identifier,
                detector_order_id,
                detector_run_id,
                _timestamp(started_at),
                _timestamp(admission_deadline_at),
                Jsonb(safe_opportunities),
                Jsonb(safe_config),
                configured_max_sessions,
                configured_max_clients,
            ),
        )
    return identifier


def record_burst_candidates(
    burst_id: str,
    candidates: Iterable[Mapping[str, Any]],
    *,
    settings: Settings | None = None,
) -> list[str]:
    prepared: list[tuple[Any, ...]] = []
    candidate_ids: list[str] = []
    for fallback_position, candidate in enumerate(candidates, 1):
        position = int(candidate.get("queue_position") or fallback_position)
        candidate_id = str(candidate.get("candidate_id") or f"{burst_id}:candidate:{position}")
        source = str(candidate.get("selection_source") or "ranked").strip().lower()
        if source not in {"ranked", "preferred"}:
            raise ValueError(f"Unsupported candidate selection source: {source}")
        candidate_ids.append(candidate_id)
        prepared.append(
            (
                candidate_id,
                burst_id,
                str(candidate["order_id"]),
                position,
                int(candidate.get("priority_snapshot") or 0),
                source,
                Jsonb(_safe_opportunities(candidate.get("compatible_opportunities") or ())),
            )
        )
    if not prepared:
        return []
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO opportunity_burst_candidates (
                    candidate_id, burst_id, order_id, queue_position,
                    priority_snapshot, selection_source, compatible_opportunities
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (candidate_id) DO NOTHING
                """,
                prepared,
            )
    return candidate_ids


def create_burst_execution(
    *,
    burst_id: str,
    role: str,
    execution_position: int,
    order_id: str | None = None,
    candidate_id: str | None = None,
    previous_candidate_id: str | None = None,
    next_candidate_id: str | None = None,
    previous_execution_id: str | None = None,
    execution_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    normalized_role = role.strip().lower()
    if normalized_role not in _EXECUTION_ROLES:
        raise ValueError(f"Unsupported burst execution role: {role}")
    if normalized_role == "detector" and (candidate_id is not None or execution_position != 0):
        raise ValueError("Detector execution requires candidate_id=None and position 0.")
    if normalized_role == "auxiliary" and (candidate_id is None or execution_position <= 0):
        raise ValueError("Auxiliary execution requires a candidate and positive position.")
    identifier = execution_id or f"burst-execution-{uuid4().hex}"
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        connection.execute(
            """
            INSERT INTO opportunity_burst_executions (
                execution_id, burst_id, candidate_id, order_id, role,
                execution_position, previous_candidate_id, next_candidate_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (execution_id) DO NOTHING
            """,
            (
                identifier,
                burst_id,
                candidate_id,
                order_id,
                normalized_role,
                execution_position,
                previous_candidate_id,
                next_candidate_id,
            ),
        )
        if previous_execution_id is not None:
            linked = connection.execute(
                """
                UPDATE opportunity_burst_executions
                SET next_candidate_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE execution_id = %s AND burst_id = %s
                """,
                (candidate_id, previous_execution_id, burst_id),
            )
            if linked.rowcount != 1:
                raise KeyError(
                    f"Previous burst execution not found: {previous_execution_id}"
                )
    return identifier


def mark_burst_execution_started(
    execution_id: str,
    *,
    claim_acquired: bool | None = None,
    started_at: datetime | str | None = None,
    settings: Settings | None = None,
) -> None:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_burst_executions
            SET state = 'running', claim_acquired = COALESCE(%s, claim_acquired),
                started_at = COALESCE(started_at, %s), updated_at = CURRENT_TIMESTAMP
            WHERE execution_id = %s AND state IN ('scheduled', 'claiming', 'running')
            RETURNING candidate_id
            """,
            (claim_acquired, _timestamp(started_at), execution_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"Burst execution is missing or terminal: {execution_id}")
        if row["candidate_id"] is not None:
            connection.execute(
                """
                UPDATE opportunity_burst_candidates
                SET state = 'admitted', admitted_at = COALESCE(admitted_at, %s)
                WHERE candidate_id = %s AND state = 'queued'
                """,
                (_timestamp(started_at), row["candidate_id"]),
            )


def update_burst_execution(
    execution_id: str,
    *,
    run_id: str | None = None,
    first_read_at: datetime | str | None = None,
    captcha_started_at: datetime | str | None = None,
    submitted_at: datetime | str | None = None,
    confirmed_at: datetime | str | None = None,
    next_candidate_id: str | None = None,
    max_active_sessions: int | None = None,
    settings: Settings | None = None,
) -> None:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_burst_executions
            SET run_id = COALESCE(%s, run_id),
                first_read_at = COALESCE(first_read_at, %s),
                captcha_started_at = COALESCE(captcha_started_at, %s),
                submitted_at = COALESCE(submitted_at, %s),
                confirmed_at = COALESCE(confirmed_at, %s),
                next_candidate_id = COALESCE(%s, next_candidate_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE execution_id = %s
            RETURNING burst_id
            """,
            (
                run_id,
                _optional_timestamp(first_read_at),
                _optional_timestamp(captcha_started_at),
                _optional_timestamp(submitted_at),
                _optional_timestamp(confirmed_at),
                next_candidate_id,
                execution_id,
            ),
        ).fetchone()
        if row is None:
            raise KeyError(f"Burst execution not found: {execution_id}")
        if max_active_sessions is not None:
            if not 0 <= max_active_sessions <= OPPORTUNITY_BURST_SESSION_LIMIT:
                raise ValueError(
                    "max_active_sessions must be between 0 and "
                    f"{OPPORTUNITY_BURST_SESSION_LIMIT}."
                )
            connection.execute(
                """
                UPDATE opportunity_bursts
                SET max_active_sessions = GREATEST(max_active_sessions, %s),
                    updated_at = CURRENT_TIMESTAMP
                WHERE burst_id = %s
                """,
                (max_active_sessions, row["burst_id"]),
            )


def mark_burst_execution_finished(
    execution_id: str,
    *,
    result_status: str,
    exit_code: int,
    exit_cause: str | None = None,
    run_id: str | None = None,
    lease_lost: bool = False,
    reservation_timing: Mapping[str, Any] | None = None,
    finished_at: datetime | str | None = None,
    settings: Settings | None = None,
) -> None:
    safe_timing = _allowlisted_mapping(reservation_timing or {}, _TIMING_KEYS)
    timing_marks = safe_timing.get("marks_lima")
    if not isinstance(timing_marks, Mapping):
        timing_marks = {}
    captcha_started_at = timing_marks.get("captcha_image_started") or timing_marks.get(
        "captcha_solver_started"
    )
    submitted_at = timing_marks.get("reserve_click_started")
    confirmed_at = timing_marks.get("confirmation_screenshot_saved")
    safe_cause = sanitize_text(exit_cause.strip())[:240] if exit_cause else None
    terminal_state = "skipped" if result_status == "skipped" else "finished"
    candidate_state = "skipped" if terminal_state == "skipped" else "completed"
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_burst_executions
            SET state = %s, result_status = %s, exit_code = %s, exit_cause = %s,
                run_id = COALESCE(%s, run_id), lease_lost = %s,
                captcha_started_at = COALESCE(captcha_started_at, %s),
                submitted_at = COALESCE(submitted_at, %s),
                confirmed_at = COALESCE(confirmed_at, %s),
                reservation_timing_json = %s, finished_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE execution_id = %s AND state NOT IN ('finished', 'skipped')
            RETURNING candidate_id
            """,
            (
                terminal_state,
                result_status[:40],
                exit_code,
                safe_cause,
                run_id,
                lease_lost,
                _optional_timestamp(captcha_started_at),
                _optional_timestamp(submitted_at),
                _optional_timestamp(confirmed_at),
                Jsonb(safe_timing) if safe_timing else None,
                _timestamp(finished_at),
                execution_id,
            ),
        ).fetchone()
        if row is None:
            raise KeyError(f"Burst execution is missing or already terminal: {execution_id}")
        if row["candidate_id"] is not None:
            connection.execute(
                """
                UPDATE opportunity_burst_candidates
                SET state = %s, finished_at = %s,
                    skip_reason = CASE WHEN %s = 'skipped' THEN %s ELSE skip_reason END
                WHERE candidate_id = %s
                """,
                (
                    candidate_state,
                    _timestamp(finished_at),
                    terminal_state,
                    safe_cause,
                    row["candidate_id"],
                ),
            )


def finish_opportunity_burst(
    burst_id: str,
    *,
    completion_reason: str,
    max_active_sessions: int,
    status: str = "closed",
    circuit_reason: str | None = None,
    finished_at: datetime | str | None = None,
    scheduled_clients: int | None = None,
    duration_seconds: float | None = None,
    settings: Settings | None = None,
) -> None:
    normalized_status = status.strip().lower()
    if normalized_status not in _BURST_STATUSES:
        raise ValueError(f"Unsupported terminal burst status: {status}")
    if not 0 <= max_active_sessions <= OPPORTUNITY_BURST_SESSION_LIMIT:
        raise ValueError(
            "max_active_sessions must be between 0 and "
            f"{OPPORTUNITY_BURST_SESSION_LIMIT}."
        )
    safe_reason = sanitize_text(completion_reason.strip())[:240]
    if not safe_reason:
        raise ValueError("completion_reason is required.")
    safe_circuit = sanitize_text(circuit_reason.strip())[:240] if circuit_reason else None
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        updated = connection.execute(
            """
            UPDATE opportunity_bursts
            SET status = %s, completion_reason = %s, circuit_reason = %s,
                max_active_sessions = GREATEST(max_active_sessions, %s),
                finished_at = %s, updated_at = CURRENT_TIMESTAMP
            WHERE burst_id = %s AND status IN ('running', 'draining')
            """,
            (
                normalized_status,
                safe_reason,
                safe_circuit,
                max_active_sessions,
                _timestamp(finished_at),
                burst_id,
            ),
        )
        if updated.rowcount == 0:
            raise KeyError(f"Active opportunity burst not found: {burst_id}")
        _complete_drain_if_idle(connection)


def record_burst_event(
    reobservation_id: str,
    sequence: int,
    event_type: str,
    *,
    burst_id: str | None = None,
    execution_id: str | None = None,
    order_id: str | None = None,
    run_id: str | None = None,
    original_attempt_id: str | None = None,
    second_attempt_id: str | None = None,
    attempt_number: int | None = None,
    mode: str | None = None,
    observed_status: str | None = None,
    outcome: str | None = None,
    duration_ms: int | None = None,
    details: Mapping[str, Any] | None = None,
    event_key: str | None = None,
    settings: Settings | None = None,
) -> str:
    normalized_type = event_type.strip().lower()
    if normalized_type not in _EVENT_TYPES:
        raise ValueError(f"Unsupported OBS-007 event type: {event_type}")
    if sequence < 0:
        raise ValueError("sequence must be non-negative.")
    if duration_ms is not None and duration_ms < 0:
        raise ValueError("duration_ms must be non-negative.")
    key = event_key or f"{reobservation_id}:{sequence}:{normalized_type}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    event_id = f"slot-lost-event-{digest}"
    safe_details = _allowlisted_mapping(details or {}, _OBSERVATION_KEYS | _REOBSERVATION_KEYS)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            INSERT INTO slot_lost_reobservation_events (
                event_id, event_key, reobservation_id, sequence, burst_id,
                execution_id, order_id, run_id, event_type,
                original_attempt_id, second_attempt_id, attempt_number,
                mode, observed_status, outcome, duration_ms, details_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_key) DO UPDATE SET event_key = EXCLUDED.event_key
            RETURNING event_id
            """,
            (
                event_id,
                key,
                reobservation_id,
                sequence,
                burst_id,
                execution_id,
                order_id,
                run_id,
                normalized_type,
                original_attempt_id,
                second_attempt_id,
                attempt_number,
                _safe_optional(mode, 40),
                _safe_optional(observed_status, 40),
                _safe_optional(outcome, 80),
                duration_ms,
                Jsonb(safe_details) if safe_details else None,
            ),
        ).fetchone()
    return str(row["event_id"])


def list_opportunity_bursts(
    *,
    limit: int = 20,
    status: str | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    bounded_limit = min(max(int(limit), 1), 100)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        status_filter = "" if status is None else "WHERE b.status = %s"
        parameters: tuple[Any, ...]
        if status is None:
            parameters = (bounded_limit,)
        else:
            parameters = (status, bounded_limit)
        rows = connection.execute(
            f"""
            SELECT b.burst_id, b.detector_order_id, b.detector_run_id, b.status,
                   started_at, admission_deadline_at, finished_at,
                   completion_reason, circuit_reason, opportunities_json,
                   config_json, configured_max_sessions, configured_max_clients,
                   max_active_sessions, created_at, updated_at,
                   (SELECT count(*) FROM opportunity_burst_candidates c
                    WHERE c.burst_id = b.burst_id) AS candidate_count,
                   (SELECT count(*) FROM opportunity_burst_executions e
                    WHERE e.burst_id = b.burst_id) AS scheduled_clients
            FROM opportunity_bursts b
            {status_filter}
            ORDER BY b.started_at DESC, b.burst_id DESC
            LIMIT %s
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def get_active_opportunity_burst(
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            SELECT b.*,
                   (SELECT count(*) FROM opportunity_burst_candidates c
                    WHERE c.burst_id = b.burst_id) AS candidate_count,
                   (SELECT count(*) FROM opportunity_burst_executions e
                    WHERE e.burst_id = b.burst_id) AS scheduled_clients
            FROM opportunity_bursts b
            WHERE b.status IN ('running', 'draining')
            ORDER BY b.started_at DESC LIMIT 1
            """
        ).fetchone()
    return dict(row) if row is not None else None


def get_opportunity_burst_detail(
    burst_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        burst = connection.execute(
            """
            SELECT b.*,
                   (SELECT count(*) FROM opportunity_burst_candidates c
                    WHERE c.burst_id = b.burst_id) AS candidate_count,
                   (SELECT count(*) FROM opportunity_burst_executions e
                    WHERE e.burst_id = b.burst_id) AS scheduled_clients
            FROM opportunity_bursts b WHERE b.burst_id = %s
            """,
            (burst_id,),
        ).fetchone()
        if burst is None:
            return None
        candidates = connection.execute(
            """
            SELECT * FROM opportunity_burst_candidates
            WHERE burst_id = %s ORDER BY queue_position
            """,
            (burst_id,),
        ).fetchall()
        executions = connection.execute(
            """
            SELECT * FROM opportunity_burst_executions
            WHERE burst_id = %s ORDER BY execution_position, created_at
            """,
            (burst_id,),
        ).fetchall()
        events = connection.execute(
            """
            SELECT * FROM slot_lost_reobservation_events
            WHERE burst_id = %s ORDER BY occurred_at, reobservation_id, sequence
            """,
            (burst_id,),
        ).fetchall()
    return {
        "burst": dict(burst),
        "candidates": [dict(row) for row in candidates],
        "executions": [dict(row) for row in executions],
        "events": [dict(row) for row in events],
    }


def reconcile_stale_opportunity_bursts(
    stale_before: datetime | str,
    *,
    reason: str = "worker_restart_reconciliation",
    settings: Settings | None = None,
) -> list[str]:
    safe_reason = sanitize_text(reason.strip())[:240]
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        rows = connection.execute(
            """
            UPDATE opportunity_bursts
            SET status = 'aborted', completion_reason = %s,
                finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE status IN ('running', 'draining') AND updated_at < %s
            RETURNING burst_id
            """,
            (safe_reason, _timestamp(stale_before)),
        ).fetchall()
        burst_ids = [str(row["burst_id"]) for row in rows]
        if burst_ids:
            connection.execute(
                """
                UPDATE opportunity_burst_candidates
                SET state = 'cancelled', finished_at = CURRENT_TIMESTAMP,
                    skip_reason = %s
                WHERE burst_id = ANY(%s) AND state IN ('queued', 'admitted')
                """,
                (safe_reason, burst_ids),
            )
            connection.execute(
                """
                UPDATE opportunity_burst_executions
                SET state = 'finished', finished_at = CURRENT_TIMESTAMP,
                    exit_cause = %s, updated_at = CURRENT_TIMESTAMP
                WHERE burst_id = ANY(%s) AND state NOT IN ('finished', 'skipped')
                """,
                (safe_reason, burst_ids),
            )
        _complete_drain_if_idle(connection)
    return burst_ids


def _complete_drain_if_idle(connection) -> None:
    connection.execute(
        """
        UPDATE opportunity_runtime_control
        SET burst_mode = 'disabled', applied_revision = revision,
            applied_at = CURRENT_TIMESTAMP, applied_by_worker = 'worker',
            updated_at = CURRENT_TIMESTAMP, updated_by = 'worker'
        WHERE id = 1 AND burst_mode = 'draining'
          AND NOT EXISTS (
              SELECT 1 FROM opportunity_bursts
              WHERE status IN ('running', 'draining')
          )
        """
    )


def _safe_opportunities(
    opportunities: Iterable[Mapping[str, Any] | tuple[str, str]],
) -> list[dict[str, str]]:
    safe: list[dict[str, str]] = []
    for item in opportunities:
        if isinstance(item, Mapping):
            date_text = item.get("date") or item.get("fecha")
            hour_text = item.get("hour") or item.get("hora")
            site_text = item.get("site") or item.get("sede")
        else:
            date_text, hour_text = item
            site_text = None
        entry = {
            "date": _safe_optional(date_text, 20) or "",
            "hour": _safe_optional(hour_text, 20) or "",
        }
        if site_text:
            entry["site"] = _safe_optional(site_text, 80) or ""
        if entry["date"]:
            safe.append(entry)
    return safe


def _allowlisted_mapping(values: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {
        str(key): value
        for key, value in values.items()
        if str(key) in allowed and _json_scalar_or_safe_mapping(value)
    }


def _json_scalar_or_safe_mapping(value: Any) -> bool:
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _json_scalar_or_safe_mapping(item)
            for key, item in value.items()
        )
    return isinstance(value, (list, tuple)) and all(
        _json_scalar_or_safe_mapping(item) for item in value
    )


def _timestamp(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _optional_timestamp(value: datetime | str | None) -> datetime | None:
    return None if value is None else _timestamp(value)


def _safe_optional(value: Any, limit: int) -> str | None:
    if value in {None, ""}:
        return None
    return sanitize_text(str(value).strip())[:limit] or None
