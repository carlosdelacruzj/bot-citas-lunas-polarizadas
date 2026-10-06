from __future__ import annotations

from psycopg import Connection

from appointment_bot.core.whatsapp_message_templates import WHATSAPP_TEMPLATE_DEFINITIONS
from appointment_bot.db.migration_steps.template_schema import (
    _create_whatsapp_message_template_schema,
)


def v74_to_v75(connection: Connection) -> None:
    _create_whatsapp_message_template_schema(connection)
    definition = WHATSAPP_TEMPLATE_DEFINITIONS["registration_monitoring_started"]
    row = connection.execute(
        "UPDATE whatsapp_message_templates SET message_template = %s, revision = revision + 1, "
        "updated_at = CURRENT_TIMESTAMP, updated_by = 'schema-migration-v75' "
        "WHERE template_key = %s RETURNING revision",
        (definition.current_default_template, definition.key),
    ).fetchone()
    connection.execute(
        "INSERT INTO whatsapp_message_template_versions "
        "(template_key, revision, message_template, created_at, created_by) "
        "VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'schema-migration-v75')",
        (definition.key, row["revision"], definition.current_default_template),
    )
    connection.execute("UPDATE schema_version SET version = 75 WHERE id = 1")
