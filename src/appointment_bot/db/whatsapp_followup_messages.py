from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from appointment_bot.config import Settings
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _mask_phone,
    _now,
    _settings,
    init_database,
)
from appointment_bot.db.whatsapp_messages import _international_phone

MESSAGE_KIND = "post_payment_followup"
OUTGOING_ROOT = Path("screenshots/whatsapp-followup-outgoing")
FOLLOWUP_CONFIG_PATH = Path(".runtime/whatsapp-followup/followup-details.json")


def prepare_test_post_payment_whatsapp_message(
    recipient_phone: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    phone = _international_phone(recipient_phone)
    message_id = f"followup-test-{uuid4().hex}"
    steps = _build_followup_steps(
        message_id=message_id,
        applicant_name="CLIENTE DE PRUEBA",
        site="LIMA-LA VICTORIA",
        appointment_date="15/08/2026",
        appointment_hour="10:00",
    )
    return _insert_followup_message(
        message_id=message_id,
        order_id=None,
        recipient_phone=phone,
        steps=steps,
        test_mode=True,
        settings=settings,
    )


def prepare_post_payment_whatsapp_message(
    order_id: str,
    *,
    allow_resend: bool = False,
    settings: Settings | None = None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT so.order_id, so.status, so.charge_required,
                   a.full_name AS applicant_name,
                   wc.display_name AS contact_name, wc.phone AS contact_phone,
                   r.status AS reservation_status, r.site, r.appointment_date,
                   r.appointment_hour,
                   p.status AS payment_status, p.amount_paid, p.amount_agreed
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN LATERAL (
                SELECT status, site, appointment_date, appointment_hour
                FROM reservations
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) r ON true
            LEFT JOIN LATERAL (
                SELECT status, amount_paid, amount_agreed
                FROM payments
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) p ON true
            WHERE so.order_id = %s
            """,
            (order_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Service order not found: {order_id}")
        previous = connection.execute(
            """
            SELECT message_id
            FROM whatsapp_followup_messages
            WHERE order_id = %s AND test_mode = false AND status = 'sent'
            ORDER BY sent_at DESC
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()

    if previous is not None and not allow_resend:
        raise ValueError(
            "El seguimiento post-pago ya fue marcado como enviado. "
            "Confirma explicitamente el reenvio para preparar otra copia."
        )
    if row["status"] != "paid":
        raise ValueError("La orden debe estar pagada para preparar este seguimiento.")
    if row["reservation_status"] != "confirmed":
        raise ValueError("La reserva todavia no esta confirmada.")
    if row["payment_status"] != "paid" or row["amount_paid"] is None:
        raise ValueError("La orden no tiene el pago confirmado.")

    phone = _international_phone(str(row["contact_phone"] or ""))
    message_id = f"followup-{uuid4().hex}"
    applicant_name = str(row["applicant_name"] or "").strip()
    steps = _build_followup_steps(
        message_id=message_id,
        applicant_name=applicant_name,
        site=str(row["site"] or "").strip(),
        appointment_date=row["appointment_date"],
        appointment_hour=row["appointment_hour"],
    )
    payload = _insert_followup_message(
        message_id=message_id,
        order_id=order_id,
        recipient_phone=phone,
        steps=steps,
        test_mode=False,
        settings=effective_settings,
    )
    return payload


def mark_followup_message_sent(
    message_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = _now()
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            UPDATE whatsapp_followup_messages
            SET status = 'sent', sent_at = COALESCE(sent_at, %s), updated_at = %s
            WHERE message_id = %s
            RETURNING message_id, order_id, status, sent_at, test_mode
            """,
            (now, now, message_id),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp follow-up message not found: {message_id}")
    return {
        "status": str(row["status"]),
        "message_id": str(row["message_id"]),
        "order_id": row["order_id"],
        "sent_at": str(row["sent_at"]),
        "test_mode": bool(row["test_mode"]),
    }


def get_followup_attachment(
    message_id: str,
    step_index: int,
    attachment_index: int,
    *,
    settings: Settings | None = None,
) -> Path:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            "SELECT steps FROM whatsapp_followup_messages WHERE message_id = %s",
            (message_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp follow-up message not found: {message_id}")
    steps = _load_steps(row["steps"])
    if step_index < 0 or step_index >= len(steps):
        raise ValueError("El paso solicitado no existe.")
    attachments = _step_attachments(steps[step_index])
    if attachment_index < 0 or attachment_index >= len(attachments):
        raise ValueError("El adjunto solicitado no existe.")
    path = Path(attachments[attachment_index]).resolve()
    root = OUTGOING_ROOT.resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("El adjunto de seguimiento no esta disponible.")
    return path


def get_followup_web_draft(
    message_id: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT message_id, order_id, recipient_phone, steps, status, test_mode
            FROM whatsapp_followup_messages
            WHERE message_id = %s
            """,
            (message_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp follow-up message not found: {message_id}")
    if row["status"] != "prepared":
        raise ValueError("El paquete debe estar en estado prepared antes de abrir el borrador.")
    steps = _load_steps(row["steps"])
    attachment_paths = [
        path
        for step in steps
        for path in _step_attachments(step)
    ]
    if not attachment_paths:
        raise ValueError("El seguimiento post-pago no tiene PDFs adjuntos.")
    return {
        "message_id": str(row["message_id"]),
        "order_id": row["order_id"],
        "recipient_phone": str(row["recipient_phone"]),
        "attachment_paths": attachment_paths,
        "caption": _combined_followup_text(steps),
        "draft_kind": "post_payment_followup",
        "test_mode": bool(row["test_mode"]),
    }


def prepare_followup_attachment_path(
    message_id: str,
    step_index: int,
    attachment_index: int,
    *,
    settings: Settings | None = None,
) -> str:
    return (
        f"/api/v1/whatsapp-followup-messages/{message_id}/attachments/"
        f"{step_index}/{attachment_index}"
    )


def _build_followup_steps(
    *,
    message_id: str,
    applicant_name: str,
    site: str,
    appointment_date: object,
    appointment_hour: object,
) -> list[dict[str, object]]:
    config = _followup_details()
    document_paths = _copy_followup_documents(message_id, config.get("documents", []))
    display_date = str(appointment_date or "").strip()
    display_hour = str(appointment_hour or "").strip()
    steps = [
        {
            "title": "Pago confirmado",
            "text": _followup_step_text(
                applicant_name=applicant_name,
                body=(
                    "Pago confirmado.\n"
                    "Su cita ya quedo reservada. Por favor, tome en cuenta las "
                    "siguientes indicaciones para el dia del tramite:\n"
                    "De ser posible, llegue 30 minutos antes, ya que la atencion "
                    "se realiza por orden de llegada.\n"
                    "Muy importante: debe acudir con el vehiculo ya polarizado, "
                    "porque ese mismo dia se realizara el peritaje de las lunas y "
                    "la identificacion vehicular."
                ),
            ),
            "attachment_paths": [],
        },
        {
            "title": "Formatos y requisitos",
            "text": _followup_step_text(
                applicant_name=applicant_name,
                body=(
                    "Debe llevar los formatos adjuntos impresos, completamente "
                    "llenados a mano y firmados donde corresponda.\n"
                    "Tambien recuerde llevar todos los documentos y copias "
                    "indicados en la hoja de requisitos."
                ),
            ),
            "attachment_paths": document_paths,
        },
        {
            "title": "Peritaje",
            "text": _followup_step_text(
                applicant_name=applicant_name,
                body=(
                    "Cuando llegue su turno, el peritaje suele demorar "
                    "aproximadamente 5 minutos.\n"
                    "Luego de aproximadamente 2 dias, podra ingresar a la misma "
                    "pagina donde realizo la reserva:\n"
                    "https://sistemas.policia.gob.pe/lunasoscurecidas/"
                    "Solicitud_Menu.aspx\n"
                    "Ahí aparecera su autorizacion virtual, con la cual podra "
                    "movilizarse sin inconvenientes."
                ),
            ),
            "attachment_paths": [],
        },
        {
            "title": "Cierre",
            "text": _followup_step_text(
                applicant_name=applicant_name,
                body=(
                    "Eso seria todo.\n"
                    "Muchas gracias por confiar en nosotros.\n"
                    "Tambien nos seria de mucha ayuda si pudiera dejarnos un "
                    "mensaje o comentario en nuestro TikTok.\n"
                    "https://www.tiktok.com/@citaspolarizadasperu?_r=1&_t=ZS-97wsIXhTdoq\n"
                    "Gracias de antemano."
                ),
            ),
            "attachment_paths": [],
        },
    ]
    if site:
        for step in steps:
            if step["title"] == "Peritaje":
                step["text"] = f"{step['text']}\n\nSede: {site}"
    if display_date or display_hour:
        steps[2]["text"] = f"{steps[2]['text']}\n\nReserva: {display_date} {display_hour}".strip()
    return steps


def _followup_step_text(*, applicant_name: str, body: str) -> str:
    heading = (
        f"Estimado/a {applicant_name}, {body}"
        if applicant_name
        else body
    )
    return heading.strip()


def _copy_followup_documents(message_id: str, values: object) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(
            "Falta la lista de PDFs para el seguimiento post-pago en "
            ".runtime/whatsapp-followup/followup-details.json."
        )
    copied: list[str] = []
    package_dir = OUTGOING_ROOT / message_id
    package_dir.mkdir(parents=True, exist_ok=True)
    for index, value in enumerate(values, start=1):
        source = Path(str(value)).expanduser().resolve()
        if source.suffix.lower() != ".pdf" or not source.is_file():
            raise ValueError(f"El PDF de seguimiento no es valido: {source}")
        destination = package_dir / source.name
        if destination.exists():
            destination = package_dir / f"{source.stem}-{index}{source.suffix}"
        shutil.copy2(source, destination)
        copied.append(str(destination))
    return copied


def _followup_details() -> dict[str, object]:
    try:
        payload = json.loads(FOLLOWUP_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Falta la configuracion local del seguimiento post-pago en "
            ".runtime/whatsapp-followup/followup-details.json."
        ) from exc
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("La configuracion de seguimiento post-pago esta incompleta.")
    return payload


def _insert_followup_message(
    *,
    message_id: str,
    order_id: str | None,
    recipient_phone: str,
    steps: list[dict[str, object]],
    test_mode: bool,
    settings: Settings | None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = _now()
    with _connection(_database_url(effective_settings)) as connection:
        connection.execute(
            """
            INSERT INTO whatsapp_followup_messages (
                message_id, order_id, recipient_phone, steps, status, test_mode,
                prepared_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, 'prepared', %s, %s, %s, %s)
            """,
            (
                message_id,
                order_id,
                recipient_phone,
                json.dumps(steps, ensure_ascii=False),
                test_mode,
                now,
                now,
                now,
            ),
        )

    enriched_steps: list[dict[str, object]] = []
    for step_index, step in enumerate(steps):
        attachments = [
            prepare_followup_attachment_path(message_id, step_index, attachment_index)
            for attachment_index, _ in enumerate(_step_attachments(step))
        ]
        enriched_steps.append(
            {
                "title": str(step.get("title") or ""),
                "text": str(step.get("text") or ""),
                "attachment_urls": attachments,
            }
        )

    return {
        "message_id": message_id,
        "order_id": order_id,
        "test_mode": test_mode,
        "status": "prepared",
        "recipient_phone": recipient_phone,
        "recipient_phone_masked": _mask_phone(recipient_phone),
        "steps": enriched_steps,
        "prepared_at": now,
        "sent_at": None,
    }


def _load_steps(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        decoded = json.loads(value)
        if isinstance(decoded, list):
            return [dict(item) for item in decoded if isinstance(item, dict)]
    raise ValueError("El paquete de seguimiento post-pago esta corrupto.")


def _combined_followup_text(steps: list[dict[str, object]]) -> str:
    full_text = "\n\n".join(str(step.get("text") or "").strip() for step in steps)
    reservation = _extract_followup_line(full_text, "Reserva")
    site = _extract_followup_line(full_text, "Sede")
    extra_lines = [value for value in (reservation, site) if value]
    details = "\n" + "\n".join(extra_lines) if extra_lines else ""
    return (
        "✅ *¡Pago confirmado!*\n"
        "Cita reservada. Llegue 30 min antes y vaya con el vehículo ya polarizado."
        f"{details}\n\n"
        "📄 Lleve los PDFs adjuntos impresos, llenados y firmados. Revise requisitos "
        "y copias.\n\n"
        "🔍 Peritaje: aprox. 5 min. En 2 días consulte su autorización virtual en la "
        "misma web de reserva.\n\n"
        "Gracias por confiar en nosotros. TikTok: @citaspolarizadasperu"
    )


def _extract_followup_line(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, flags=re.MULTILINE)
    return f"{label}: {match.group(1).strip()}" if match else ""


def _step_attachments(step: dict[str, object]) -> list[str]:
    attachments = step.get("attachment_paths")
    if isinstance(attachments, list):
        return [str(item) for item in attachments if str(item).strip()]
    return []


__all__ = [
    "get_followup_attachment",
    "get_followup_web_draft",
    "mark_followup_message_sent",
    "prepare_post_payment_whatsapp_message",
    "prepare_test_post_payment_whatsapp_message",
]
