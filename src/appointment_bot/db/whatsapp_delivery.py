from __future__ import annotations

from uuid import uuid4

from psycopg.types.json import Jsonb

from appointment_bot.db.common import _connection, _database_url


def reconcile_late_confirmations(*, settings):
    """Close only new timeout incidents with a finished, fully evidenced attempt."""
    reconciled = []
    with _connection(_database_url(settings)) as connection:
        jobs = connection.execute("""
            SELECT job_key, job_kind, message_id, order_id, report_date, error_message, status
            FROM whatsapp_automation_jobs jobs
            WHERE review_resolution IS NULL
              AND ((status='uncertain'
                    AND error_message LIKE '%%confirmation_deadline_exceeded:%%')
                   OR (status='sent' AND EXISTS (
                       SELECT 1 FROM telegram_alert_outbox alerts WHERE alerts.dedupe_key=
                           'whatsapp-confirmation:' || jobs.job_key || ':delayed'
                   ) AND NOT EXISTS (
                       SELECT 1 FROM telegram_alert_outbox alerts WHERE alerts.dedupe_key=
                           'whatsapp-confirmation:' || jobs.job_key || ':confirmed'
                   )))
              AND NOT EXISTS (SELECT 1 FROM whatsapp_automation_jobs recovery
                  WHERE recovery.source_job_key=jobs.job_key)
            ORDER BY updated_at LIMIT 20 FOR UPDATE SKIP LOCKED
        """).fetchall()
        for job in jobs:
            attempts = delivery_history(connection, job["job_key"])
            if not attempts:
                continue
            attempt = attempts[-1]
            marker = f"confirmation_deadline_exceeded:{attempt['attempt_id']} "
            components = attempt["components"]
            if (
                (job["status"] == "uncertain" and marker not in job["error_message"])
                or not attempt["finished_at"]
                or attempt["message_id"] != job["message_id"]
                or not components
                or any(item["state"] != "confirmed" for item in components)
                or any(not (item.get("outgoing_id") or item.get("evidence_path"))
                       for item in components)
            ):
                continue
            table = {
                "reservation_album": "whatsapp_messages",
                "post_payment_followup": "whatsapp_followup_messages",
            }.get(job["job_kind"])
            if table:
                updated = connection.execute(
                    f"UPDATE {table} SET status='sent', sent_at=COALESCE(sent_at,%s), "
                    "updated_at=CURRENT_TIMESTAMP WHERE message_id=%s RETURNING message_id",
                    (attempt["finished_at"], job["message_id"]),
                ).fetchone()
                if not updated:
                    continue
            note = (
                "Confirmado posteriormente por eventos completos del mismo intento "
                f"{attempt['attempt_id']}. Se conserva el timeout original; sin reenvio."
            )
            if job["status"] == "uncertain":
                connection.execute("""
                    UPDATE whatsapp_automation_jobs
                    SET review_resolution='confirmed_complete', review_note=%s,
                        reviewed_by='system:late_confirmation', reviewed_at=CURRENT_TIMESTAMP,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE job_key=%s
                """, (note, job["job_key"]))
            else:
                note = "Evidencia completa del mismo intento; sin reenvio."
            target = job["order_id"] or job["report_date"]
            connection.execute("""
                INSERT INTO telegram_alert_outbox(dedupe_key,payload)
                VALUES (%s,%s) ON CONFLICT (dedupe_key) DO NOTHING
            """, (
                f"whatsapp-confirmation:{job['job_key']}:confirmed",
                Jsonb({"message": "WhatsApp: envio confirmado posteriormente.\n"
                       f"Destino operativo: {target}.\n{note}", "alert_kind": "operational"}),
            ))
            reconciled.append(dict(job))
    return reconciled


def start_delivery_attempt(job_key, recipient_masked, *, settings) -> str:
    attempt_id = uuid4().hex
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            "INSERT INTO whatsapp_delivery_attempts(attempt_id, job_key, recipient_masked) "
            "VALUES (%s, %s, %s)",
            (attempt_id, job_key, recipient_masked),
        )
    return attempt_id


def complete_delivery_attempt(attempt_id, *, settings):
    with _connection(_database_url(settings)) as connection:
        connection.execute(
            "UPDATE whatsapp_delivery_attempts SET finished_at=CURRENT_TIMESTAMP "
            "WHERE attempt_id=%s AND finished_at IS NULL",
            (attempt_id,),
        )


def initialize_delivery_attempt(attempt_id, message_id, recipient_masked, manifest, *, settings):
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "UPDATE whatsapp_delivery_attempts SET message_id=%s, recipient_masked=%s, manifest=%s "
            "WHERE attempt_id=%s AND manifest='[]'::jsonb RETURNING attempt_id",
            (message_id, recipient_masked, Jsonb(manifest), attempt_id),
        ).fetchone()
        if row is None:
            raise ValueError("El manifiesto del intento ya fue registrado.")
        for component in manifest:
            connection.execute(
                "INSERT INTO whatsapp_delivery_events(attempt_id, component_key, state) "
                "VALUES (%s,%s,%s)",
                (attempt_id, component["key"], component.get("state", "not_attempted")),
            )


def record_delivery_event(
    attempt_id, keys, state, evidence_path, outgoing_id, *, settings, guard_running=False
):
    with _connection(_database_url(settings)) as connection:
        if guard_running:
            attempt = connection.execute(
                "SELECT job_key FROM whatsapp_delivery_attempts WHERE attempt_id=%s",
                (attempt_id,),
            ).fetchone()
            if attempt is None:
                raise ValueError("El intento de envio no existe.")
            if attempt["job_key"] is not None:
                job = connection.execute(
                    "SELECT status,lease_expires_at > CURRENT_TIMESTAMP AS live "
                    "FROM whatsapp_automation_jobs WHERE job_key=%s FOR UPDATE",
                    (attempt["job_key"],),
                ).fetchone()
                if not job or job["status"] != "running" or not job["live"]:
                    raise ValueError("El intento ya no tiene permiso activo para enviar.")
        for key in keys:
            connection.execute(
                "INSERT INTO whatsapp_delivery_events "
                "(attempt_id,component_key,state,evidence_path,outgoing_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (attempt_id, key, state, evidence_path, outgoing_id),
            )


def delivery_history(connection, job_key):
    keys = []
    current = job_key
    while current is not None and current not in keys:
        keys.append(current)
        source = connection.execute(
            "SELECT source_job_key FROM whatsapp_automation_jobs WHERE job_key=%s", (current,)
        ).fetchone()
        current = source["source_job_key"] if source else None
    attempts = connection.execute(
        "SELECT attempt_id,job_key,message_id,recipient_masked,manifest,created_at,finished_at "
        "FROM whatsapp_delivery_attempts WHERE job_key=ANY(%s) OR (job_key IS NULL AND message_id "
        "IN (SELECT message_id FROM whatsapp_automation_jobs WHERE job_key=ANY(%s))) "
        "ORDER BY created_at,attempt_id",
        (keys, keys),
    ).fetchall()
    history = []
    for attempt in attempts:
        events = connection.execute(
            "SELECT component_key,state,evidence_path,outgoing_id,created_at "
            "FROM whatsapp_delivery_events WHERE attempt_id=%s ORDER BY event_id",
            (attempt["attempt_id"],),
        ).fetchall()
        latest = {}
        for event in events:
            key = event["component_key"]
            latest[key] = {
                **latest.get(key, {}),
                **{field: value for field, value in event.items() if value is not None},
            }
        components = []
        for component in attempt["manifest"]:
            event = latest.get(component["key"], {})
            components.append(
                {
                    **component,
                    **{
                        key: str(value) if value is not None else None
                        for key, value in event.items()
                    },
                }
            )
        history.append(
            {
                "attempt_id": attempt["attempt_id"],
                "job_key": attempt["job_key"],
                "message_id": attempt["message_id"],
                "recipient_masked": attempt["recipient_masked"],
                "created_at": str(attempt["created_at"]),
                "finished_at": str(attempt["finished_at"]) if attempt["finished_at"] else None,
                "components": components,
                "events": [
                    {key: str(value) if value is not None else None for key, value in event.items()}
                    for event in events
                ],
            }
        )
    return history


def recovery_delivery_plan(job_key, *, settings):
    with _connection(_database_url(settings)) as connection:
        row = connection.execute(
            "SELECT recovery_components,source_job_key FROM whatsapp_automation_jobs "
            "WHERE job_key=%s",
            (job_key,),
        ).fetchone()
        if not row or row["recovery_components"] is None:
            return None, {}
        history = delivery_history(connection, row["source_job_key"])
        history = [attempt for attempt in history if attempt["components"]]
        if not history:
            raise ValueError("La recuperacion no tiene un manifiesto original verificable.")
        return row["recovery_components"], {
            item["key"]: item["state"] for item in history[-1]["components"]
        }
