from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _settings,
    init_database,
)
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.utils.sanitization import sanitize_text

_OBS006_NAMES = {"obs006", "burst", "opportunity_burst"}
_OBS007_NAMES = {"obs007", "slot_lost_reobservation"}
_ACTIONS = {
    "enable_obs006",
    "deactivate_obs006",
    "drain_obs006",
    "enable_obs007",
    "deactivate_obs007",
}
_ACTION_ALIASES = {
    "activate_obs006": "enable_obs006",
    "disable_obs006": "deactivate_obs006",
    "activate_obs007": "enable_obs007",
    "disable_obs007": "deactivate_obs007",
}


class OpportunityControlConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class OpportunityRuntimeControl:
    burst_mode: str
    obs007_mode: str
    revision: int
    applied_revision: int
    updated_at: datetime
    updated_by: str
    applied_at: datetime | None
    applied_by_worker: str | None
    circuit_state: str
    circuit_reason: str | None
    circuit_opened_at: datetime | None
    circuit_reset_at: datetime | None
    circuit_reset_by: str | None

    @property
    def application_pending(self) -> bool:
        return self.applied_revision < self.revision


def get_opportunity_control(
    settings: Settings | None = None,
) -> OpportunityRuntimeControl:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            SELECT burst_mode, obs007_mode, revision, applied_revision,
                   updated_at, updated_by, applied_at, applied_by_worker,
                   circuit_state, circuit_reason, circuit_opened_at,
                   circuit_reset_at, circuit_reset_by
            FROM opportunity_runtime_control
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Opportunity runtime control row is missing.")
    return _control_from_row(row)


def update_opportunity_control(
    action: str,
    *,
    expected_revision: int,
    updated_by: str,
    reason: str | None = None,
    settings: Settings | None = None,
) -> OpportunityRuntimeControl:
    normalized = action.strip().lower()
    normalized = _ACTION_ALIASES.get(normalized, normalized)
    if normalized not in _ACTIONS:
        raise ValueError(f"Unsupported opportunity control action: {action}")
    if expected_revision < 0:
        raise ValueError("expected_revision must be non-negative.")
    actor = _safe_actor(updated_by)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        current = connection.execute(
            """
            SELECT revision,
                   EXISTS (
                       SELECT 1 FROM opportunity_bursts
                       WHERE status IN ('running', 'draining')
                   ) AS active_burst
            FROM opportunity_runtime_control
            WHERE id = 1
            FOR UPDATE
            """
        ).fetchone()
        if current is None:
            raise RuntimeError("Opportunity runtime control row is missing.")
        if int(current["revision"]) != expected_revision:
            raise OpportunityControlConflict(
                f"Stale opportunity control revision: expected {expected_revision}, "
                f"current {current['revision']}."
            )
        burst_mode, obs007_mode = _modes_for_action(
            normalized,
            active_burst=bool(current["active_burst"]),
        )
        next_revision = expected_revision + 1
        immediate = not (
            normalized in {"deactivate_obs006", "drain_obs006"}
            and bool(current["active_burst"])
        )
        row = connection.execute(
            """
            UPDATE opportunity_runtime_control
            SET burst_mode = COALESCE(%s, burst_mode),
                obs007_mode = COALESCE(%s, obs007_mode),
                revision = %s,
                applied_revision = CASE WHEN %s THEN %s ELSE applied_revision END,
                applied_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE applied_at END,
                applied_by_worker = CASE WHEN %s THEN %s ELSE applied_by_worker END,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = %s
            WHERE id = 1
            RETURNING burst_mode, obs007_mode, revision, applied_revision,
                      updated_at, updated_by, applied_at, applied_by_worker,
                      circuit_state, circuit_reason, circuit_opened_at,
                      circuit_reset_at, circuit_reset_by
            """,
            (
                burst_mode,
                obs007_mode,
                next_revision,
                immediate,
                next_revision,
                immediate,
                immediate,
                actor,
                actor,
            ),
        ).fetchone()
    record_remote_control_audit(
        actor=actor,
        action=normalized,
        status="applied" if immediate else "accepted",
        target_type="opportunity_control",
        target_id="1",
        operation_id=f"opportunity-control-{next_revision}",
        detail=_audit_detail(next_revision, reason),
        settings=resolved,
    )
    return _control_from_row(row)


def mark_opportunity_control_applied(
    revision: int,
    *,
    applied_by_worker: str,
    settings: Settings | None = None,
) -> OpportunityRuntimeControl:
    if revision < 0:
        raise ValueError("revision must be non-negative.")
    worker = _safe_actor(applied_by_worker)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_runtime_control
            SET applied_revision = GREATEST(applied_revision, %s),
                applied_at = CURRENT_TIMESTAMP,
                applied_by_worker = %s
            WHERE id = 1 AND revision >= %s
            RETURNING burst_mode, obs007_mode, revision, applied_revision,
                      updated_at, updated_by, applied_at, applied_by_worker,
                      circuit_state, circuit_reason, circuit_opened_at,
                      circuit_reset_at, circuit_reset_by
            """,
            (revision, worker, revision),
        ).fetchone()
    if row is None:
        raise OpportunityControlConflict(
            f"Cannot apply unknown future opportunity control revision {revision}."
        )
    record_remote_control_audit(
        actor=worker,
        action="apply_opportunity_control",
        status="applied",
        target_type="opportunity_control",
        target_id="1",
        operation_id=f"opportunity-control-{revision}",
        detail=f"revision={revision}",
        settings=resolved,
    )
    return _control_from_row(row)


def is_opportunity_admission_allowed(
    control_name: str,
    settings: Settings | None = None,
) -> bool:
    resolved = _settings(settings)
    control = get_opportunity_control(resolved)
    if control.circuit_state == "open":
        return False
    normalized = control_name.strip().lower()
    if normalized in _OBS006_NAMES:
        return control.burst_mode == "enabled"
    if normalized in _OBS007_NAMES:
        return control.obs007_mode == "enabled"
    raise ValueError(f"Unsupported opportunity control name: {control_name}")


def admissions_allowed(
    kind: str,
    settings: Settings | None = None,
) -> bool:
    return is_opportunity_admission_allowed(kind, settings)


def trip_opportunity_circuit_breaker(
    reason: str,
    burst_id: str | None = None,
    settings: Settings | None = None,
) -> OpportunityRuntimeControl:
    safe_reason = sanitize_text(reason.strip())[:240]
    if not safe_reason:
        raise ValueError("Circuit breaker reason is required.")
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_runtime_control
            SET circuit_state = 'open',
                circuit_reason = %s,
                circuit_opened_at = CURRENT_TIMESTAMP,
                revision = revision + 1,
                applied_revision = CASE
                    WHEN applied_revision = revision THEN revision + 1
                    ELSE applied_revision
                END,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = 'worker',
                applied_at = CASE
                    WHEN applied_revision = revision THEN CURRENT_TIMESTAMP
                    ELSE applied_at
                END,
                applied_by_worker = CASE
                    WHEN applied_revision = revision THEN 'worker'
                    ELSE applied_by_worker
                END
            WHERE id = 1
            RETURNING burst_mode, obs007_mode, revision, applied_revision,
                      updated_at, updated_by, applied_at, applied_by_worker,
                      circuit_state, circuit_reason, circuit_opened_at,
                      circuit_reset_at, circuit_reset_by
            """,
            (safe_reason,),
        ).fetchone()
    record_remote_control_audit(
        actor="worker",
        action="trip_opportunity_circuit_breaker",
        status="applied",
        target_type="opportunity_burst" if burst_id else "opportunity_control",
        target_id=burst_id or "1",
        operation_id=f"opportunity-control-{row['revision']}",
        detail=safe_reason,
        settings=resolved,
    )
    return _control_from_row(row)


def reset_opportunity_circuit_breaker(
    *,
    expected_revision: int,
    reset_by: str,
    reason: str | None = None,
    settings: Settings | None = None,
) -> OpportunityRuntimeControl:
    actor = _safe_actor(reset_by)
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            UPDATE opportunity_runtime_control
            SET circuit_state = 'closed', circuit_reason = NULL,
                circuit_opened_at = NULL, circuit_reset_at = CURRENT_TIMESTAMP,
                circuit_reset_by = %s, revision = revision + 1,
                applied_revision = CASE
                    WHEN applied_revision = revision THEN revision + 1
                    ELSE applied_revision
                END,
                applied_at = CASE
                    WHEN applied_revision = revision THEN CURRENT_TIMESTAMP
                    ELSE applied_at
                END,
                applied_by_worker = CASE
                    WHEN applied_revision = revision THEN %s
                    ELSE applied_by_worker
                END,
                updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE id = 1 AND revision = %s
            RETURNING burst_mode, obs007_mode, revision, applied_revision,
                      updated_at, updated_by, applied_at, applied_by_worker,
                      circuit_state, circuit_reason, circuit_opened_at,
                      circuit_reset_at, circuit_reset_by
            """,
            (actor, actor, actor, expected_revision),
        ).fetchone()
    if row is None:
        raise OpportunityControlConflict(
            f"Stale opportunity control revision {expected_revision}."
        )
    record_remote_control_audit(
        actor=actor,
        action="reset_opportunity_circuit_breaker",
        status="applied",
        target_type="opportunity_control",
        target_id="1",
        operation_id=f"opportunity-control-{row['revision']}",
        detail=_audit_detail(int(row["revision"]), reason),
        settings=resolved,
    )
    return _control_from_row(row)


def _modes_for_action(action: str, *, active_burst: bool) -> tuple[str | None, str | None]:
    if action == "enable_obs006":
        return "enabled", None
    if action == "drain_obs006":
        return "draining", None
    if action == "deactivate_obs006":
        return ("draining" if active_burst else "disabled"), None
    if action == "enable_obs007":
        return None, "enabled"
    return None, "disabled"


def _safe_actor(value: str) -> str:
    return sanitize_text(value.strip())[:64] or "admin_api"


def _audit_detail(revision: int, reason: str | None) -> str:
    safe_reason = sanitize_text((reason or "").strip())[:200]
    if not safe_reason:
        return f"revision={revision}"
    return f"revision={revision}; reason={safe_reason}"


def _control_from_row(row) -> OpportunityRuntimeControl:
    return OpportunityRuntimeControl(
        burst_mode=str(row["burst_mode"]),
        obs007_mode=str(row["obs007_mode"]),
        revision=int(row["revision"]),
        applied_revision=int(row["applied_revision"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
        applied_at=row["applied_at"],
        applied_by_worker=row["applied_by_worker"],
        circuit_state=str(row["circuit_state"]),
        circuit_reason=row["circuit_reason"],
        circuit_opened_at=row["circuit_opened_at"],
        circuit_reset_at=row["circuit_reset_at"],
        circuit_reset_by=row["circuit_reset_by"],
    )
