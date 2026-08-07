from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from playwright.sync_api import sync_playwright

from appointment_bot.config import Settings
from appointment_bot.core.contacts import resolve_whatsapp_recipient
from appointment_bot.db.common import (
    _connection,
    _database_url,
    _mask_phone,
    _now,
    _settings,
    init_database,
)
from appointment_bot.services.reservation_messages import (
    format_confirmed_reservation_message,
)
from appointment_bot.utils.file_deduplication import copy_deduplicated_file

MESSAGE_KIND = "reservation_confirmation_payment"
OUTGOING_ROOT = Path("screenshots/whatsapp-outgoing")
PAYMENT_CONFIG_PATH = Path(".runtime/whatsapp-payment/payment-details.json")
SAFE_EVIDENCE_LABELS = ("programado", "etapas", "confirmacion")


def prepare_test_whatsapp_message(
    recipient_phone: str,
    *,
    settings: Settings | None = None,
) -> dict[str, object]:
    phone = _international_phone(recipient_phone)
    message_id = f"whatsapp-{uuid4().hex}"
    greeting = format_confirmed_reservation_message(
        person_name="CLIENTE DE PRUEBA",
        date="15/08/2026",
        hour="10:00",
        site="LIMA-LA VICTORIA",
    )
    payment = _payment_message("50.00")
    attachment = _render_demo_constancia(message_id)
    payment_attachment = _copy_payment_attachment(message_id)
    return _insert_message(
        message_id=message_id,
        order_id=None,
        message_kind="test",
        recipient_phone=phone,
        recipient_username=None,
        greeting=greeting,
        evidence_caption="",
        payment_message=payment,
        attachment_path=attachment,
        payment_attachment_path=payment_attachment,
        test_mode=True,
        settings=settings,
    )


def prepare_order_whatsapp_message(
    order_id: str,
    *,
    allow_resend: bool = False,
    automatic: bool = False,
    settings: Settings | None = None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    if not automatic:
        from appointment_bot.db.whatsapp_automation import whatsapp_automation_in_progress

        if whatsapp_automation_in_progress(
            order_id,
            "reservation_album",
            settings=effective_settings,
        ):
            raise ValueError(
                "El envio automatico de evidencia y cobro ya esta en curso."
            )
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT so.order_id, so.status, so.charge_required,
                   a.full_name AS applicant_name,
                   wc.display_name AS contact_name, wc.phone AS contact_phone,
                   wc.username AS contact_username,
                   r.status AS reservation_status, r.site, r.appointment_date,
                   r.appointment_hour, r.evidence_path, r.run_id,
                   p.status AS payment_status, p.amount_agreed,
                   ARRAY(
                       SELECT rs.path
                       FROM run_screenshots rs
                       WHERE rs.run_id = r.run_id
                       ORDER BY rs.id
                   ) AS evidence_paths
            FROM service_orders so
            JOIN applicants a ON a.applicant_id = so.applicant_id
            LEFT JOIN applicant_contacts ac
                ON ac.applicant_id = a.applicant_id AND ac.is_primary = true
            LEFT JOIN whatsapp_contacts wc ON wc.contact_id = ac.contact_id
            LEFT JOIN LATERAL (
                SELECT status, site, appointment_date, appointment_hour,
                       evidence_path, run_id
                FROM reservations
                WHERE order_id = so.order_id
                ORDER BY created_at DESC
                LIMIT 1
            ) r ON true
            LEFT JOIN LATERAL (
                SELECT status, amount_agreed
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
            SELECT message_id, sent_at
            FROM whatsapp_messages
            WHERE order_id = %s AND test_mode = false AND status = 'sent'
            ORDER BY sent_at DESC
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()

    if previous is not None and not allow_resend:
        raise ValueError(
            "La confirmacion de WhatsApp ya fue marcada como enviada. "
            "Confirma explicitamente el reenvio para preparar otra copia."
        )
    if row["status"] != "reserved_payment_pending":
        raise ValueError("La orden debe estar en reserved_payment_pending.")
    if not row["charge_required"]:
        raise ValueError("La orden no requiere cobro.")
    if row["reservation_status"] != "confirmed":
        raise ValueError("La reserva todavia no esta confirmada.")
    if row["payment_status"] != "pending" or row["amount_agreed"] is None:
        raise ValueError("La orden no tiene un pago pendiente con monto acordado.")

    phone, recipient_username = resolve_whatsapp_recipient(
        row["contact_phone"], row["contact_username"]
    )
    if phone is not None:
        phone = _international_phone(phone)
    source = _select_safe_evidence(
        [*(row["evidence_paths"] or []), row["evidence_path"]]
    )
    message_id = f"whatsapp-{uuid4().hex}"
    attachment = _copy_attachment(source, message_id)
    payment_attachment = _copy_payment_attachment(message_id)
    applicant_name = str(row["applicant_name"] or "").strip()
    greeting = format_confirmed_reservation_message(
        person_name=applicant_name,
        date=row["appointment_date"],
        hour=row["appointment_hour"],
        site=row["site"],
    )
    amount = f"{row['amount_agreed']:.2f}"
    payment = _payment_message(amount)
    return _insert_message(
        message_id=message_id,
        order_id=order_id,
        message_kind=MESSAGE_KIND,
        recipient_phone=phone,
        recipient_username=recipient_username,
        greeting=greeting,
        evidence_caption="",
        payment_message=payment,
        attachment_path=attachment,
        payment_attachment_path=payment_attachment,
        test_mode=False,
        settings=effective_settings,
    )


def mark_whatsapp_message_sent(
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
            UPDATE whatsapp_messages
            SET status = 'sent', sent_at = COALESCE(sent_at, %s), updated_at = %s
            WHERE message_id = %s
            RETURNING message_id, order_id, status, sent_at, test_mode
            """,
            (now, now, message_id),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp message not found: {message_id}")
    return {
        "status": str(row["status"]),
        "message_id": str(row["message_id"]),
        "order_id": row["order_id"],
        "sent_at": str(row["sent_at"]),
        "test_mode": bool(row["test_mode"]),
    }


def get_whatsapp_attachment(
    message_id: str,
    *,
    settings: Settings | None = None,
) -> Path:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            "SELECT attachment_path FROM whatsapp_messages WHERE message_id = %s",
            (message_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp message not found: {message_id}")
    path = Path(str(row["attachment_path"])).resolve()
    root = OUTGOING_ROOT.resolve()
    if root not in path.parents or path.suffix.lower() != ".png" or not path.is_file():
        raise ValueError("La constancia de WhatsApp no esta disponible.")
    return path


def get_whatsapp_payment_attachment(
    message_id: str,
    *,
    settings: Settings | None = None,
) -> Path:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            "SELECT payment_attachment_path FROM whatsapp_messages WHERE message_id = %s",
            (message_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp message not found: {message_id}")
    return _authorized_outgoing_path(
        row["payment_attachment_path"],
        allowed_suffixes={".png", ".jpg", ".jpeg"},
        missing_message="La imagen de pago de WhatsApp no esta disponible.",
    )


def get_whatsapp_web_draft(
    message_id: str,
    *,
    draft_kind: str = "confirmation",
    settings: Settings | None = None,
) -> dict[str, object]:
    if draft_kind not in {"confirmation", "payment"}:
        raise ValueError("Tipo de borrador de WhatsApp no soportado.")
    effective_settings = _settings(settings)
    init_database(effective_settings)
    with _connection(_database_url(effective_settings)) as connection:
        row = connection.execute(
            """
            SELECT message_id, order_id, recipient_phone, recipient_username, greeting,
                   evidence_caption, payment_message, payment_attachment_path,
                   status, test_mode
            FROM whatsapp_messages
            WHERE message_id = %s
            """,
            (message_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"WhatsApp message not found: {message_id}")
    if row["status"] != "prepared":
        raise ValueError("El paquete debe estar en estado prepared antes de abrir el borrador.")
    if draft_kind == "payment":
        attachment = _authorized_outgoing_path(
            row["payment_attachment_path"],
            allowed_suffixes={".png", ".jpg", ".jpeg"},
            missing_message="La imagen de pago de WhatsApp no esta disponible.",
        )
        text = str(row["payment_message"] or "").strip()
    else:
        attachment = get_whatsapp_attachment(message_id, settings=effective_settings)
        text = "\n\n".join(
            part
            for part in (
                str(row["greeting"] or "").strip(),
                str(row["evidence_caption"] or "").strip(),
            )
            if part
        )
    return {
        "message_id": str(row["message_id"]),
        "order_id": row["order_id"],
        "recipient_phone": (
            str(row["recipient_phone"]) if row["recipient_phone"] is not None else None
        ),
        "recipient_username": row["recipient_username"],
        "attachment_path": attachment,
        "caption": text,
        "draft_kind": draft_kind,
        "test_mode": bool(row["test_mode"]),
    }


def archive_whatsapp_evidence(order_id: str, values: list[object]) -> Path | None:
    try:
        source = _select_safe_evidence(values)
    except ValueError:
        return None
    OUTGOING_ROOT.mkdir(parents=True, exist_ok=True)
    safe_order = "".join(
        character
        for character in order_id
        if character.isalnum() or character == "-"
    )
    destination = OUTGOING_ROOT / f"source-{safe_order}-programado-{uuid4().hex[:8]}.png"
    return copy_deduplicated_file(source, destination)


def _insert_message(
    *,
    message_id: str,
    order_id: str | None,
    message_kind: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    greeting: str,
    evidence_caption: str,
    payment_message: str,
    attachment_path: Path,
    payment_attachment_path: Path,
    test_mode: bool,
    settings: Settings | None,
) -> dict[str, object]:
    effective_settings = _settings(settings)
    init_database(effective_settings)
    now = _now()
    with _connection(_database_url(effective_settings)) as connection:
        connection.execute(
            """
            INSERT INTO whatsapp_messages (
                message_id, order_id, message_kind, recipient_phone, recipient_username, greeting,
                evidence_caption, payment_message, attachment_path, status,
                payment_attachment_path, test_mode, prepared_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'prepared', %s, %s, %s, %s, %s)
            """,
            (
                message_id,
                order_id,
                message_kind,
                recipient_phone,
                recipient_username,
                greeting,
                evidence_caption,
                payment_message,
                str(attachment_path),
                str(payment_attachment_path),
                test_mode,
                now,
                now,
                now,
            ),
        )
    return {
        "message_id": message_id,
        "order_id": order_id,
        "test_mode": test_mode,
        "status": "prepared",
        "recipient_phone": recipient_phone,
        "recipient_phone_masked": _mask_phone(recipient_phone),
        "recipient_username": recipient_username,
        "recipient_label": recipient_phone or recipient_username,
        "greeting": greeting,
        "evidence_caption": evidence_caption,
        "payment_message": payment_message,
        "whatsapp_url": (
            f"https://wa.me/{recipient_phone[1:]}?text={quote(greeting)}"
            if recipient_phone
            else None
        ),
        "attachment_url": f"/api/v1/whatsapp-messages/{message_id}/attachment",
        "payment_attachment_url": (
            f"/api/v1/whatsapp-messages/{message_id}/payment-attachment"
        ),
        "prepared_at": now,
        "sent_at": None,
    }


def _international_phone(value: str) -> str:
    normalized = "".join(character for character in value.strip() if character.isdigit())
    if not value.strip().startswith("+") or not 8 <= len(normalized) <= 15:
        raise ValueError(
            "El WhatsApp debe usar formato internacional con + y código de país, "
            "por ejemplo +51987654321."
        )
    return f"+{normalized}"


def _select_safe_evidence(values: list[object]) -> Path:
    candidates: list[Path] = []
    for value in values:
        if not value:
            continue
        path = Path(str(value))
        name = path.name.casefold()
        if path.suffix.lower() == ".png" and any(label in name for label in SAFE_EVIDENCE_LABELS):
            candidates.append(path)
    for label in SAFE_EVIDENCE_LABELS:
        for path in candidates:
            if label in path.name.casefold() and path.is_file():
                return path
    raise ValueError(
        "No existe una constancia PNG segura de Programado para esta reserva."
    )


def _copy_attachment(source: Path, message_id: str) -> Path:
    OUTGOING_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTGOING_ROOT / f"{message_id}-constancia.png"
    return copy_deduplicated_file(source, destination)


def _copy_payment_attachment(message_id: str) -> Path:
    details = _payment_details()
    config_root = PAYMENT_CONFIG_PATH.resolve().parent
    source = (config_root / details["image"]).resolve()
    if (
        config_root not in source.parents
        or source.suffix.lower() not in {".png", ".jpg", ".jpeg"}
    ):
        raise ValueError("La imagen de pago configurada no es valida.")
    if not source.is_file():
        raise ValueError(
            "No existe la imagen de pago local. Configurala en "
            ".runtime/whatsapp-payment/payment-details.json."
        )
    OUTGOING_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTGOING_ROOT / f"{message_id}-payment{source.suffix.lower()}"
    return copy_deduplicated_file(source, destination)


def _payment_message(amount: str) -> str:
    details = _payment_details()
    return (
        "Ahora ya podemos proceder con el pago del servicio, "
        f"el monto es de {amount} soles.\n"
        f"El número es {details['phone']} a nombre de *{details['account_name']}*"
    )


def _payment_details() -> dict[str, str]:
    try:
        payload = json.loads(PAYMENT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Falta la configuracion local del cobro de WhatsApp en "
            ".runtime/whatsapp-payment/payment-details.json."
        ) from exc
    values = {
        "phone": str(payload.get("phone") or "").strip(),
        "account_name": str(payload.get("account_name") or "").strip(),
        "image": str(payload.get("image") or "").strip(),
    }
    if not values["phone"].isdigit() or not all(values.values()):
        raise ValueError("La configuracion local del cobro de WhatsApp esta incompleta.")
    return values


def _authorized_outgoing_path(
    value: object,
    *,
    allowed_suffixes: set[str],
    missing_message: str,
) -> Path:
    path = Path(str(value or "")).resolve()
    root = OUTGOING_ROOT.resolve()
    if (
        root not in path.parents
        or path.suffix.lower() not in allowed_suffixes
        or not path.is_file()
    ):
        raise ValueError(missing_message)
    return path


def _render_demo_constancia(message_id: str) -> Path:
    OUTGOING_ROOT.mkdir(parents=True, exist_ok=True)
    destination = OUTGOING_ROOT / f"{message_id}-constancia.png"
    markup = """
    <html><body style="margin:0;background:#e7f5ef;font-family:Arial,sans-serif">
      <main style="width:760px;height:760px;padding:64px;box-sizing:border-box;background:#fff">
        <p style="color:#128c7e;font-weight:700;letter-spacing:2px">PRUEBA WHATSAPP</p>
        <h1 style="font-size:46px;margin:48px 0 24px">Cita programada</h1>
        <p style="font-size:26px">Cliente de prueba</p>
        <section style="margin-top:48px;padding:32px;background:#e7f5ef;
          border-radius:24px;font-size:26px;line-height:1.7">
          <strong>Fecha:</strong> 15/08/2026<br>
          <strong>Hora:</strong> 10:00<br>
          <strong>Sede:</strong> LIMA-LA VICTORIA
        </section>
        <p style="margin-top:56px;color:#52645e;font-size:20px">
          Constancia ficticia. No corresponde a una orden real.
        </p>
      </main>
    </body></html>
    """
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 760, "height": 760})
            page.set_content(html.unescape(markup))
            page.locator("main").screenshot(path=str(destination))
        finally:
            browser.close()
    return destination


__all__ = [
    "archive_whatsapp_evidence",
    "get_whatsapp_attachment",
    "mark_whatsapp_message_sent",
    "prepare_order_whatsapp_message",
    "prepare_test_whatsapp_message",
]
