from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from psycopg.types.json import Jsonb

from appointment_bot.config import Settings
from appointment_bot.db.common import _connection, _database_url, _settings, init_database
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.utils.sanitization import sanitize_text

REMINDER_MODES = frozenset({"disabled", "dry_run", "canary", "live"})


class AppointmentReminderControlConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class AppointmentReminderControl:
    mode: str
    message_template: str
    canary_order_ids: tuple[str, ...]
    revision: int
    updated_at: datetime
    updated_by: str

    def allows(self, order_id: str) -> bool:
        return self.mode == "live" or (
            self.mode == "canary" and order_id in self.canary_order_ids
        )


def get_appointment_reminder_control(
    settings: Settings | None = None,
) -> AppointmentReminderControl:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            SELECT mode, message_template, canary_order_ids, revision,
                   updated_at, updated_by
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
    message_template: str,
    canary_order_ids: list[str],
    expected_revision: int,
    updated_by: str,
    settings: Settings | None = None,
) -> AppointmentReminderControl:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in REMINDER_MODES:
        raise ValueError("Unsupported appointment reminder mode.")
    actor = sanitize_text(updated_by.strip())[:120] or "dashboard-owner"
    normalized_ids = sorted(
        {sanitize_text(value.strip()) for value in canary_order_ids if value.strip()}
    )
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
            SET mode = %s, message_template = %s, canary_order_ids = %s,
                revision = %s, updated_at = CURRENT_TIMESTAMP, updated_by = %s
            WHERE id = 1
            RETURNING mode, message_template, canary_order_ids, revision,
                      updated_at, updated_by
            """,
            (normalized_mode, message_template, Jsonb(normalized_ids), next_revision, actor),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO appointment_reminder_template_versions (
                revision, message_template, created_at, created_by
            ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s)
            """,
            (next_revision, message_template, actor),
        )
    record_remote_control_audit(
        actor=actor,
        action="update_appointment_reminder_control",
        status="applied",
        target_type="appointment_reminder_control",
        target_id="1",
        operation_id=f"appointment-reminder-control-{next_revision}",
        detail=f"mode={normalized_mode}; revision={next_revision}; canaries={len(normalized_ids)}",
        settings=resolved,
    )
    return _from_row(row)


def _from_row(row) -> AppointmentReminderControl:
    raw_ids = row["canary_order_ids"] if isinstance(row["canary_order_ids"], list) else []
    return AppointmentReminderControl(
        mode=str(row["mode"]),
        message_template=str(row["message_template"]),
        canary_order_ids=tuple(str(value) for value in raw_ids),
        revision=int(row["revision"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


__all__ = [
    "AppointmentReminderControl",
    "AppointmentReminderControlConflict",
    "REMINDER_MODES",
    "get_appointment_reminder_control",
    "update_appointment_reminder_control",
]
