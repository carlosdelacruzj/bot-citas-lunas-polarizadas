from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from appointment_bot.config import Settings
from appointment_bot.core.whatsapp_message_templates import (
    normalize_template,
    validate_whatsapp_template,
    whatsapp_template_definition,
)
from appointment_bot.db.common import _connection, _database_url, _settings, init_database
from appointment_bot.db.remote_control_audit import record_remote_control_audit_in_connection
from appointment_bot.utils.sanitization import sanitize_text


class WhatsAppMessageTemplateConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class WhatsAppMessageTemplate:
    template_key: str
    message_template: str
    revision: int
    enabled: bool
    updated_at: datetime
    updated_by: str


def list_whatsapp_message_templates(
    settings: Settings | None = None,
) -> list[WhatsAppMessageTemplate]:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        rows = connection.execute(
            """
            SELECT template_key, message_template, revision, enabled,
                   updated_at, updated_by
            FROM whatsapp_message_templates
            ORDER BY template_key
            """
        ).fetchall()
    return [_from_row(row) for row in rows]


def get_whatsapp_message_template(
    template_key: str,
    settings: Settings | None = None,
) -> WhatsAppMessageTemplate | None:
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        row = connection.execute(
            """
            SELECT template_key, message_template, revision, enabled,
                   updated_at, updated_by
            FROM whatsapp_message_templates
            WHERE template_key = %s
            """,
            (template_key.strip(),),
        ).fetchone()
    return _from_row(row) if row is not None else None


def update_whatsapp_message_template(
    *,
    template_key: str,
    message_template: str,
    expected_revision: int,
    updated_by: str,
    settings: Settings | None = None,
) -> WhatsAppMessageTemplate:
    definition = whatsapp_template_definition(template_key)
    if definition is None:
        raise KeyError(template_key)
    normalized_template = normalize_template(message_template)
    errors = validate_whatsapp_template(definition, normalized_template)
    if errors:
        raise ValueError(errors["message_template"])
    if expected_revision < 1:
        raise ValueError("expected_revision must be at least 1.")
    actor = sanitize_text(updated_by.strip())[:120] or "dashboard-owner"
    resolved = _settings(settings)
    init_database(resolved)
    with _connection(_database_url(resolved)) as connection:
        current = connection.execute(
            """
            SELECT revision
            FROM whatsapp_message_templates
            WHERE template_key = %s
            FOR UPDATE
            """,
            (definition.key,),
        ).fetchone()
        if current is None:
            raise RuntimeError(f"WhatsApp template row is missing: {definition.key}.")
        current_revision = int(current["revision"])
        if current_revision != expected_revision:
            raise WhatsAppMessageTemplateConflict(
                f"Stale WhatsApp template revision: expected {expected_revision}, "
                f"current {current_revision}."
            )
        next_revision = current_revision + 1
        row = connection.execute(
            """
            UPDATE whatsapp_message_templates
            SET message_template = %s,
                revision = %s,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = %s
            WHERE template_key = %s
            RETURNING template_key, message_template, revision, enabled,
                      updated_at, updated_by
            """,
            (normalized_template, next_revision, actor, definition.key),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s)
            """,
            (definition.key, next_revision, normalized_template, actor),
        )
        record_remote_control_audit_in_connection(
            connection,
            actor=actor,
            action="update_whatsapp_message_template",
            status="applied",
            target_type="whatsapp_message_template",
            target_id=definition.key,
            operation_id=f"whatsapp-template-{definition.key}-{next_revision}",
            detail=(
                f"revision={next_revision}; previous_revision={current_revision}; "
                "source="
                + (
                    "restore_recommended"
                    if normalized_template
                    == normalize_template(definition.recommended_template)
                    else "operator_edit"
                )
            ),
        )
    if row is None:
        raise RuntimeError(f"WhatsApp template update failed: {definition.key}.")
    return _from_row(row)


def _from_row(row) -> WhatsAppMessageTemplate:
    return WhatsAppMessageTemplate(
        template_key=str(row["template_key"]),
        message_template=str(row["message_template"]),
        revision=int(row["revision"]),
        enabled=bool(row["enabled"]),
        updated_at=row["updated_at"],
        updated_by=str(row["updated_by"]),
    )


__all__ = [
    "WhatsAppMessageTemplate",
    "WhatsAppMessageTemplateConflict",
    "get_whatsapp_message_template",
    "list_whatsapp_message_templates",
    "update_whatsapp_message_template",
]
