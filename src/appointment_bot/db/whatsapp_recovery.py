from __future__ import annotations

from hashlib import sha256

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.db.common import _connection, _database_url, _now, _settings, init_database
from appointment_bot.utils.sanitization import sanitize_text


def retry_whatsapp_job(
    job_key: str,
    *,
    confirmed_no_delivery: bool,
    reviewed_by: str,
    settings: RuntimeSettings | None = None,
) -> dict[str, object]:
    effective = _settings(settings)
    init_database(effective)
    recovery_key = "recovery:" + sha256(job_key.encode()).hexdigest()
    actor = sanitize_text(reviewed_by)[:80] or "system"
    now = _now()
    with _connection(_database_url(effective)) as connection:
        job = connection.execute(
            "SELECT * FROM whatsapp_automation_jobs WHERE job_key = %s FOR UPDATE",
            (job_key,),
        ).fetchone()
        if job is None:
            raise ValueError("El intento de WhatsApp no existe.")
        previous = connection.execute(
            "SELECT job_key, status FROM whatsapp_automation_jobs WHERE job_key = %s",
            (recovery_key,),
        ).fetchone()
        if previous is not None:
            return {
                "job_key": recovery_key,
                "status": previous["status"],
                "source_job_key": job_key,
            }
        if job["job_kind"] not in {
            "registration_notice",
            "reservation_album",
            "post_payment_followup",
        }:
            raise ValueError("Este tipo de envio no admite recuperacion desde el dashboard.")
        if job["status"] not in {"failed", "uncertain"} or job["review_resolution"]:
            raise ValueError("El intento ya no esta pendiente de revision.")
        if job["status"] == "uncertain" and not confirmed_no_delivery:
            raise ValueError("Confirma que revisaste el chat y no se envio ninguna parte.")
        connection.execute(
            "SELECT order_id FROM service_orders WHERE order_id = %s FOR UPDATE",
            (job["order_id"],),
        )
        newer = connection.execute(
            """
            SELECT 1 FROM whatsapp_automation_jobs
            WHERE order_id = %s AND job_kind = %s AND job_key <> %s
              AND (status IN ('queued', 'blocked', 'running') OR created_at > %s)
            LIMIT 1
            """,
            (job["order_id"], job["job_kind"], job_key, job["created_at"]),
        ).fetchone()
        if newer:
            raise ValueError(
                "Existe otro intento activo, enviado o posterior. Actualiza la pantalla."
            )
        if job["job_kind"] != "registration_notice":
            table = (
                "whatsapp_messages"
                if job["job_kind"] == "reservation_album"
                else "whatsapp_followup_messages"
            )
            sent = connection.execute(
                f"SELECT 1 FROM {table} WHERE order_id = %s "
                "AND status = 'sent' AND NOT test_mode LIMIT 1",
                (job["order_id"],),
            ).fetchone()
            if sent:
                raise ValueError("El paquete ya figura como enviado; revisa el chat.")
            if job["message_id"]:
                prepared = connection.execute(
                    f"SELECT 1 FROM {table} WHERE message_id = %s AND order_id = %s "
                    "AND status = 'prepared' AND NOT test_mode FOR UPDATE",
                    (job["message_id"], job["order_id"]),
                ).fetchone()
                if prepared is None:
                    raise ValueError("El mensaje preparado ya no esta disponible para reintentar.")
        connection.execute(
            """
            INSERT INTO whatsapp_automation_jobs (
                job_key, order_id, job_kind, status, message_id, recipient_phone,
                recipient_username, message_text, registration_notice_type,
                preflight_cycle, template_key, template_revision,
                next_attempt_at, created_at, updated_at
            )
            SELECT %s, order_id, job_kind, 'queued', message_id, recipient_phone,
                   recipient_username, message_text, registration_notice_type,
                   preflight_cycle, template_key, template_revision, %s, %s, %s
            FROM whatsapp_automation_jobs WHERE job_key = %s
            """,
            (recovery_key, now, now, now, job_key),
        )
        connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET review_resolution = 'dismissed', review_note = %s,
                reviewed_at = %s, reviewed_by = %s, updated_at = %s
            WHERE job_key = %s
            """,
            (
                f"Recuperacion autorizada sin entrega previa: {recovery_key}",
                now,
                actor,
                now,
                job_key,
            ),
        )
    return {"job_key": recovery_key, "status": "queued", "source_job_key": job_key}
