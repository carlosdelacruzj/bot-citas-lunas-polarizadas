from __future__ import annotations

from hashlib import sha256
from uuid import uuid4

from psycopg.types.json import Jsonb

from appointment_bot.configuration.runtime import RuntimeSettings
from appointment_bot.db.common import _connection, _database_url, _now, _settings, init_database
from appointment_bot.db.whatsapp_delivery import delivery_history
from appointment_bot.utils.sanitization import sanitize_text


def retry_whatsapp_job(
    job_key: str,
    *,
    confirmed_no_delivery: bool,
    reviewed_by: str,
    expected_recipient: str | None = None,
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
        history = delivery_history(connection, job_key)
        if any(attempt["finished_at"] is None for attempt in history):
            raise ValueError("El navegador todavia no cerro el intento. No se puede recuperar.")
        history = [attempt for attempt in history if attempt["components"]]
        components = history[-1]["components"] if history else []
        selection = [item["key"] for item in components if item["state"] != "confirmed"]
        if components and not selection:
            raise ValueError("Todos los componentes estan confirmados; concilia el intento.")
        requires_review = any(item["state"] == "uncertain" for item in components)
        if (
            job["status"] == "uncertain"
            and not confirmed_no_delivery
            and (not components or requires_review)
        ):
            raise ValueError("Confirma que revisaste el chat y no se envio ninguna parte.")
        connection.execute(
            "SELECT order_id FROM service_orders WHERE order_id = %s FOR UPDATE",
            (job["order_id"],),
        )
        contact = connection.execute(
            """
            SELECT wc.phone, wc.username FROM service_orders so
            JOIN applicant_contacts ac ON ac.applicant_id = so.applicant_id AND ac.is_primary
            JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            WHERE so.order_id = %s FOR UPDATE OF ac, wc
            """,
            (job["order_id"],),
        ).fetchone()
        current_recipient = (contact["phone"] or contact["username"]) if contact else None
        message_id = job["message_id"]
        frozen_recipient = job["recipient_phone"] or job["recipient_username"]
        if job["job_kind"] != "registration_notice" and message_id:
            message_table = (
                "whatsapp_messages"
                if job["job_kind"] == "reservation_album"
                else "whatsapp_followup_messages"
            )
            frozen = connection.execute(
                f"SELECT recipient_phone, recipient_username FROM {message_table} "
                "WHERE message_id=%s",
                (message_id,),
            ).fetchone()
            if frozen is None:
                raise ValueError("El mensaje preparado ya no esta disponible para reintentar.")
            frozen_recipient = frozen["recipient_phone"] or frozen["recipient_username"]
        contact_changed = current_recipient != frozen_recipient and (
            message_id is not None or job["job_kind"] == "registration_notice"
        )
        if expected_recipient is not None and expected_recipient != current_recipient:
            raise ValueError("El contacto cambio desde la revision. Actualiza la pantalla.")
        if contact_changed:
            if job["job_kind"] != "reservation_album" or not message_id:
                raise ValueError("El contacto cambio; prepara y revisa un nuevo aviso.")
            if not current_recipient or expected_recipient != current_recipient:
                raise ValueError(
                    "Revisa y confirma el contacto actual antes de recuperar el album."
                )
            if any(item["state"] == "confirmed" for item in components):
                raise ValueError(
                    "Hay componentes enviados al contacto anterior. Requiere revision manual."
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
        if contact_changed:
            message_id = "whatsapp-" + uuid4().hex
            connection.execute(
                """
                INSERT INTO whatsapp_messages (
                    message_id, order_id, message_kind, recipient_phone, recipient_username,
                    greeting, evidence_caption, payment_message, attachment_path, status,
                    payment_attachment_path, confirmation_template_key,
                    confirmation_template_revision,
                    payment_template_key, payment_template_revision, test_mode,
                    prepared_at, created_at, updated_at
                )
                SELECT %s, order_id, message_kind, %s, %s, greeting, evidence_caption,
                       payment_message, attachment_path, 'prepared', payment_attachment_path,
                       confirmation_template_key, confirmation_template_revision,
                       payment_template_key, payment_template_revision, test_mode, %s, %s, %s
                FROM whatsapp_messages WHERE message_id=%s
                """,
                (
                    message_id,
                    contact["phone"],
                    contact["username"],
                    now,
                    now,
                    now,
                    job["message_id"],
                ),
            )
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
        if contact_changed:
            connection.execute(
                "UPDATE whatsapp_automation_jobs SET message_id=%s WHERE job_key=%s",
                (message_id, recovery_key),
            )
        connection.execute(
            "UPDATE whatsapp_automation_jobs SET recovery_components=%s,source_job_key=%s "
            "WHERE job_key=%s",
            (Jsonb(selection) if components else None, job_key, recovery_key),
        )
        connection.execute(
            """
            UPDATE whatsapp_automation_jobs
            SET review_resolution = 'dismissed', review_note = %s,
                reviewed_at = %s, reviewed_by = %s, updated_at = %s
            WHERE job_key = %s
            """,
            (
                f"Recuperacion autorizada de componentes no confirmados: {recovery_key}",
                now,
                actor,
                now,
                job_key,
            ),
        )
    return {"job_key": recovery_key, "status": "queued", "source_job_key": job_key}


def current_whatsapp_recipient(order_id: str) -> str | None:
    effective = _settings(None)
    with _connection(_database_url(effective)) as connection:
        contact = connection.execute(
            """
            SELECT wc.phone, wc.username FROM service_orders so
            JOIN applicant_contacts ac ON ac.applicant_id=so.applicant_id AND ac.is_primary
            JOIN whatsapp_contacts wc ON wc.contact_id=ac.contact_id WHERE so.order_id=%s
            """,
            (order_id,),
        ).fetchone()
    return (contact["phone"] or contact["username"]) if contact else None
