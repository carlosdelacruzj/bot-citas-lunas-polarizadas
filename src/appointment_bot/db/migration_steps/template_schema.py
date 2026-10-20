from __future__ import annotations

import json
from datetime import UTC, datetime

from psycopg import Connection

from appointment_bot.core.whatsapp_message_templates import (
    MAX_TEMPLATE_LENGTH,
    WHATSAPP_TEMPLATE_DEFINITIONS,
)


def _create_whatsapp_message_template_schema(connection: Connection) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS whatsapp_message_templates (
            template_key text PRIMARY KEY CHECK (
                char_length(template_key) BETWEEN 1 AND 80
            ),
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND {MAX_TEMPLATE_LENGTH}
            ),
            revision integer NOT NULL DEFAULT 1 CHECK (revision >= 1),
            enabled boolean NOT NULL DEFAULT true,
            updated_at timestamptz NOT NULL,
            updated_by text NOT NULL
        )
        """
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS whatsapp_message_template_versions (
            template_key text NOT NULL REFERENCES whatsapp_message_templates(template_key),
            revision integer NOT NULL CHECK (revision >= 1),
            message_template text NOT NULL CHECK (
                char_length(message_template) BETWEEN 1 AND {MAX_TEMPLATE_LENGTH}
            ),
            created_at timestamptz NOT NULL,
            created_by text NOT NULL,
            PRIMARY KEY (template_key, revision)
        )
        """
    )
    now = datetime.now(UTC)
    for definition in WHATSAPP_TEMPLATE_DEFINITIONS.values():
        connection.execute(
            """
            INSERT INTO whatsapp_message_templates (
                template_key, message_template, revision, enabled, updated_at, updated_by
            ) VALUES (%s, %s, 1, true, %s, 'schema-migration')
            ON CONFLICT (template_key) DO NOTHING
            """,
            (definition.key, definition.current_default_template, now),
        )
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES (%s, 1, %s, %s, 'schema-migration')
            ON CONFLICT (template_key, revision) DO NOTHING
            """,
            (definition.key, definition.current_default_template, now),
        )


def _create_whatsapp_automation_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_automation_jobs
        ADD COLUMN IF NOT EXISTS template_key text,
        ADD COLUMN IF NOT EXISTS template_revision integer
        """
    )
    constraint = connection.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_whatsapp_automation_template_trace'
          AND conrelid = 'whatsapp_automation_jobs'::regclass
        """
    ).fetchone()
    if constraint is None:
        connection.execute(
            """
            ALTER TABLE whatsapp_automation_jobs
            ADD CONSTRAINT ck_whatsapp_automation_template_trace CHECK (
                (template_key IS NULL AND template_revision IS NULL)
                OR (
                    template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
            """
        )


def _create_whatsapp_message_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_messages
        ADD COLUMN IF NOT EXISTS confirmation_template_key text,
        ADD COLUMN IF NOT EXISTS confirmation_template_revision integer,
        ADD COLUMN IF NOT EXISTS payment_template_key text,
        ADD COLUMN IF NOT EXISTS payment_template_revision integer
        """
    )
    for constraint_name, key_column, revision_column in (
        (
            "ck_whatsapp_messages_confirmation_template_trace",
            "confirmation_template_key",
            "confirmation_template_revision",
        ),
        (
            "ck_whatsapp_messages_payment_template_trace",
            "payment_template_key",
            "payment_template_revision",
        ),
    ):
        constraint = connection.execute(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = %s
              AND conrelid = 'whatsapp_messages'::regclass
            """,
            (constraint_name,),
        ).fetchone()
        if constraint is None:
            connection.execute(
                f"""
                ALTER TABLE whatsapp_messages
                ADD CONSTRAINT {constraint_name} CHECK (
                    ({key_column} IS NULL AND {revision_column} IS NULL)
                    OR (
                        {key_column} IS NOT NULL
                        AND char_length({key_column}) BETWEEN 1 AND 80
                        AND {revision_column} IS NOT NULL
                        AND {revision_column} > 0
                    )
                )
                """
            )


def _create_whatsapp_followup_template_trace_schema(connection: Connection) -> None:
    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        ADD COLUMN IF NOT EXISTS message_text text,
        ADD COLUMN IF NOT EXISTS template_key text,
        ADD COLUMN IF NOT EXISTS template_revision integer
        """
    )
    constraint = connection.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_whatsapp_followup_messages_template_trace'
          AND conrelid = 'whatsapp_followup_messages'::regclass
        """
    ).fetchone()
    if constraint is None:
        connection.execute(
            """
            ALTER TABLE whatsapp_followup_messages
            ADD CONSTRAINT ck_whatsapp_followup_messages_template_trace CHECK (
                (
                    message_text IS NULL
                    AND template_key IS NULL
                    AND template_revision IS NULL
                )
                OR (
                    message_text IS NOT NULL
                    AND char_length(message_text) BETWEEN 1 AND 4096
                    AND template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
            """
        )


def _unify_appointment_reminder_template_schema(connection: Connection) -> None:
    control = connection.execute(
        """
        SELECT message_template, revision, updated_at, updated_by
        FROM appointment_reminder_control
        WHERE id = 1
        """
    ).fetchone()
    template = connection.execute(
        """
        SELECT revision, updated_by
        FROM whatsapp_message_templates
        WHERE template_key = 'appointment_reminder'
        """
    ).fetchone()
    if control is None or template is None:
        raise RuntimeError("Appointment reminder template state is incomplete.")
    if int(template["revision"]) != 1 or str(template["updated_by"]) != "schema-migration":
        return
    legacy_versions = connection.execute(
        """
        SELECT revision, message_template, created_at, created_by
        FROM appointment_reminder_template_versions
        WHERE revision > 1
        ORDER BY revision
        """
    ).fetchall()
    for version in legacy_versions:
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES ('appointment_reminder', %s, %s, %s, %s)
            ON CONFLICT (template_key, revision) DO NOTHING
            """,
            (
                version["revision"],
                version["message_template"],
                version["created_at"],
                version["created_by"],
            ),
        )
    target_revision = max(int(control["revision"]), 2)
    connection.execute(
        """
        INSERT INTO whatsapp_message_template_versions (
            template_key, revision, message_template, created_at, created_by
        ) VALUES ('appointment_reminder', %s, %s, %s, %s)
        ON CONFLICT (template_key, revision) DO NOTHING
        """,
        (
            target_revision,
            control["message_template"],
            control["updated_at"],
            control["updated_by"],
        ),
    )
    connection.execute(
        """
        UPDATE whatsapp_message_templates
        SET message_template = %s,
            revision = %s,
            updated_at = %s,
            updated_by = %s
        WHERE template_key = 'appointment_reminder'
          AND revision = 1
          AND updated_by = 'schema-migration'
        """,
        (
            control["message_template"],
            target_revision,
            control["updated_at"],
            control["updated_by"],
        ),
    )


def _retire_appointment_reminder_legacy_schema(connection: Connection) -> None:
    legacy_table = connection.execute(
        "SELECT to_regclass('appointment_reminder_template_versions') AS table_name"
    ).fetchone()
    if legacy_table is None or legacy_table["table_name"] is None:
        raise RuntimeError("Legacy appointment reminder template history is missing.")

    legacy_versions = connection.execute(
        """
        SELECT revision, message_template, created_at, created_by
        FROM appointment_reminder_template_versions
        ORDER BY revision
        """
    ).fetchall()
    if not legacy_versions:
        raise RuntimeError("Legacy appointment reminder template history is empty.")

    for version in legacy_versions:
        revision = int(version["revision"])
        current = connection.execute(
            """
            SELECT message_template
            FROM whatsapp_message_template_versions
            WHERE template_key = 'appointment_reminder' AND revision = %s
            """,
            (revision,),
        ).fetchone()
        if current is not None and str(current["message_template"]) != str(
            version["message_template"]
        ):
            references = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM whatsapp_automation_jobs
                     WHERE template_key = 'appointment_reminder'
                       AND template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_followup_messages
                     WHERE template_key = 'appointment_reminder'
                       AND template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_messages
                     WHERE confirmation_template_key = 'appointment_reminder'
                       AND confirmation_template_revision = %s)
                  + (SELECT count(*) FROM whatsapp_messages
                     WHERE payment_template_key = 'appointment_reminder'
                       AND payment_template_revision = %s) AS count
                """,
                (revision, revision, revision, revision),
            ).fetchone()
            if references is not None and int(references["count"]) > 0:
                raise RuntimeError(
                    "Cannot replace differing appointment reminder template "
                    f"revision {revision}; persisted work references it."
                )
        connection.execute(
            """
            INSERT INTO whatsapp_message_template_versions (
                template_key, revision, message_template, created_at, created_by
            ) VALUES ('appointment_reminder', %s, %s, %s, %s)
            ON CONFLICT (template_key, revision) DO UPDATE
            SET message_template = EXCLUDED.message_template,
                created_at = EXCLUDED.created_at,
                created_by = EXCLUDED.created_by
            """,
            (
                revision,
                version["message_template"],
                version["created_at"],
                version["created_by"],
            ),
        )

    mismatch = connection.execute(
        """
        SELECT count(*) AS count
        FROM appointment_reminder_template_versions legacy
        LEFT JOIN whatsapp_message_template_versions unified
          ON unified.template_key = 'appointment_reminder'
         AND unified.revision = legacy.revision
        WHERE unified.revision IS NULL
           OR unified.message_template IS DISTINCT FROM legacy.message_template
           OR unified.created_at IS DISTINCT FROM legacy.created_at
           OR unified.created_by IS DISTINCT FROM legacy.created_by
        """
    ).fetchone()
    if mismatch is None or int(mismatch["count"]) != 0:
        raise RuntimeError("Appointment reminder template history was not preserved.")

    missing_frozen_text = connection.execute(
        """
        SELECT count(*) AS count
        FROM whatsapp_automation_jobs
        WHERE job_kind = 'appointment_reminder'
          AND NULLIF(BTRIM(message_text), '') IS NULL
        """
    ).fetchone()
    if missing_frozen_text is None or int(missing_frozen_text["count"]) != 0:
        raise RuntimeError("An appointment reminder job has no frozen message text.")

    connection.execute(
        "ALTER TABLE appointment_reminder_control DROP COLUMN message_template"
    )
    connection.execute("DROP TABLE appointment_reminder_template_versions")


def _freeze_historical_whatsapp_followup_text(connection: Connection) -> None:
    rows = connection.execute(
        """
        SELECT message_id, steps, template_key, template_revision
        FROM whatsapp_followup_messages
        WHERE NULLIF(BTRIM(message_text), '') IS NULL
        ORDER BY message_id
        """
    ).fetchall()
    traced = [
        row
        for row in rows
        if row["template_key"] is not None or row["template_revision"] is not None
    ]
    if traced:
        raise RuntimeError("A traced post-payment package has no frozen message text.")

    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        DROP CONSTRAINT ck_whatsapp_followup_messages_template_trace
        """
    )
    for row in rows:
        steps_value = row["steps"]
        if isinstance(steps_value, str):
            steps_value = json.loads(steps_value)
        if not isinstance(steps_value, list):
            raise RuntimeError("A historical post-payment package has invalid steps.")
        steps = [item for item in steps_value if isinstance(item, dict)]
        full_text = "\n\n".join(str(step.get("text") or "").strip() for step in steps)
        detail_lines: list[str] = []
        for label in ("Reserva", "Sede"):
            prefix = f"{label}:"
            value = next(
                (
                    line[len(prefix) :].strip()
                    for line in full_text.splitlines()
                    if line.startswith(prefix) and line[len(prefix) :].strip()
                ),
                "",
            )
            if value:
                detail_lines.append(f"{label}: {value}")
        details = "\n" + "\n".join(detail_lines) if detail_lines else ""
        message_text = (
            "✅ *¡Pago confirmado!*\n"
            "Cita reservada. Llegue 30 min antes y vaya con el vehículo ya polarizado."
            f"{details}\n\n"
            "📄 Lleve los PDFs adjuntos impresos, llenados y firmados. Revise requisitos "
            "y copias.\n\n"
            "🔍 El peritaje dura aprox. 5 min. Después de pasarlo, en 2 días consulte "
            "su autorización virtual en la misma web de reserva.\n\n"
            "Gracias por confiar en nosotros. Si puede dejarnos un comentario en TikTok "
            "nos ayuda muchísimo: @citaspolarizadasperu"
        )
        if len(message_text) > 4096:
            raise RuntimeError("A historical post-payment package exceeds 4096 characters.")
        connection.execute(
            """
            UPDATE whatsapp_followup_messages
            SET message_text = %s, updated_at = CURRENT_TIMESTAMP
            WHERE message_id = %s
            """,
            (message_text, row["message_id"]),
        )

    connection.execute(
        "ALTER TABLE whatsapp_followup_messages ALTER COLUMN message_text SET NOT NULL"
    )
    connection.execute(
        """
        ALTER TABLE whatsapp_followup_messages
        ADD CONSTRAINT ck_whatsapp_followup_messages_template_trace CHECK (
            char_length(message_text) BETWEEN 1 AND 4096
            AND (
                (template_key IS NULL AND template_revision IS NULL)
                OR (
                    template_key IS NOT NULL
                    AND char_length(template_key) BETWEEN 1 AND 80
                    AND template_revision IS NOT NULL
                    AND template_revision > 0
                )
            )
        )
        """
    )
