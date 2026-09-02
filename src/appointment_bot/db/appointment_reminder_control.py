from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.utils.sanitization import sanitize_text

REMINDER_MODES = frozenset({"disabled", "dry_run", "live"})
REMINDER_LEAD_DAYS = frozenset({1, 2, 3})


class AppointmentReminderControlConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class AppointmentReminderControl:
    mode: str
    lead_days: int
    revision: int
    updated_at: datetime
    updated_by: str

    def allows(self, order_id: str) -> bool:
        return self.mode == "live"


def get_appointment_reminder_control(
    settings: Settings | None = None,
) -> AppointmentReminderControl:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            SELECT mode, lead_days, revision, updated_at, updated_by
            FROM appointment_reminder_control
            WHERE id = 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Appointment reminder control row is missing.")
    return _from_row(row)


def update_appointment_reminder_control(
    *,
    mode: str,
    lead_days: int,
    expected_revision: int,
    updated_by: str,
    settings: Settings | None = None,
) -> AppointmentReminderControl:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in REMINDER_MODES:
        raise ValueError("Unsupported appointment reminder mode.")
    if isinstance(lead_days, bool) or lead_days not in REMINDER_LEAD_DAYS:
        raise ValueError("Appointment reminder lead days must be 1, 2, or 3.")
    actor = sanitize_text(updated_by.strip())[:120] or "system"
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        current = connection.execute(
            """
            SELECT revision FROM appointment_reminder_control WHERE id = 1 FOR UPDATE
            """
        ).fetchone()
        if current is None:
            raise RuntimeError("Appointment reminder control row is missing.")
        if int(current["revision"]) != expected_revision:
            raise AppointmentReminderControlConflict(
                f"Stale reminder control revision: expected {expected_revision}, "
                f"current {current['revision']}."
            )
        next_revision = expected_revision + 1
        row = connection.execute(
            """
            UPDATE appointment_reminder_control
            SET mode = %s, lead_days = %s,
                revision = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE id = 1
            RETURNING mode, lead_days, revision, updated_at, updated_by
            """,
            (
                normalized_mode,
                lead_days,
                next_revision,
                actor,
            ),
        ).fetchone()
    record_remote_control_audit(
        actor=actor,
        action="update_appointment_reminder_control",
        status="applied",
        target_type="appointment_reminder_control",
        target_id="1",
        operation_id=f"appointment-reminder-control-{next_revision}",
        detail=(
            f"mode={normalized_mode}; lead_days={lead_days}; revision={next_revision}"
        ),
        settings=resolved,
    )
    return _from_row(row)


def _from_row(row) -> AppointmentReminderControl:
    return AppointmentReminderControl(
        mode=str(row["mode"]),
        lead_days=int(row["lead_days"]),
        revision=int(row["revision"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


__all__ = [
    "AppointmentReminderControl",
    "AppointmentReminderControlConflict",
    "REMINDER_LEAD_DAYS",
    "REMINDER_MODES",
    "get_appointment_reminder_control",
    "update_appointment_reminder_control",
]
