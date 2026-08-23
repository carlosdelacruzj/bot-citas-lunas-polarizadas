from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from appointment_bot.core.models import ServiceOrderSummary
from appointment_bot.db.orders import list_service_order_summaries


def operator_inbox_payload() -> dict[str, Any]:
    items = [
        task
        for order in list_service_order_summaries()
        if (task := _order_task(order)) is not None
    ]
    access_count = sum(item["kind"] == "preflight" for item in items)
    paused_count = sum(item["kind"] == "paused" for item in items)
    payment_count = sum(item["kind"] == "payment" for item in items)
    contact_count = sum(item["kind"] == "contact" for item in items)
    whatsapp_count = sum(
        item["kind"] == "whatsapp" or item["action"] == "review_whatsapp"
        for item in items
    )
    postpayment_count = sum(
        item["action"] == "review_post_payment_whatsapp" for item in items
    )
    message_count = sum(
        item["kind"] in {"contact", "whatsapp", "followup", "review"}
        for item in items
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "total": len(items),
            "access": access_count,
            "paused": paused_count,
            "contact": contact_count,
            "whatsapp": whatsapp_count,
            "payment": payment_count,
            "postpayment": postpayment_count,
            "messages": message_count,
            "captcha": 0,
        },
        "items": items,
        "captcha": {
            "included": False,
            "pending": 0,
        },
    }


def _order_task(order: ServiceOrderSummary) -> dict[str, Any] | None:
    if order.status == "archived":
        return None
    if order.preflight_status == "failed":
        return _task(
            order,
            key_prefix="preflight",
            kind="preflight",
            title="Validación de acceso fallida",
            description=order.preflight_message
            or "Vuelve a comprobar el acceso al portal.",
            label="Bloqueo",
            action="revalidate",
            action_label="Volver a validar",
            tone="bad",
            state=order.preflight_status,
        )
    if order.status == "paused":
        return _task(
            order,
            key_prefix="paused",
            kind="paused",
            title="Cliente pausado",
            description="Revisa el motivo antes de reactivar la busqueda.",
            label="Pausado",
            action="view_order",
            action_label="Ver cliente",
            tone="warn",
            state=order.status,
        )

    has_pending_reservation_payment = (
        order.status == "reserved_payment_pending"
        and order.reservation_status == "confirmed"
        and order.payment_status == "pending"
    )
    has_operational_contact = bool(
        order.contact_whatsapp_masked or order.contact_whatsapp_username_masked
    )
    if has_pending_reservation_payment and not has_operational_contact:
        return _task(
            order,
            key_prefix="contact",
            kind="contact",
            title="Completar contacto del cliente",
            description=(
                "La reserva está confirmada, pero falta un teléfono o @usuario válido."
            ),
            label="Contacto",
            action="edit_contact",
            action_label="Corregir contacto",
            tone="bad",
            state="missing",
        )
    if (
        has_pending_reservation_payment
        and order.whatsapp_message_action_state == "manual_required"
    ):
        return _task(
            order,
            key_prefix="whatsapp",
            kind="whatsapp",
            title="Enviar constancia y cobro",
            description=(
                "La reserva está confirmada y todavía falta preparar el mensaje inicial."
            ),
            label="WhatsApp",
            action="prepare_whatsapp",
            action_label="Preparar mensaje",
            tone="warn",
            state=order.whatsapp_message_action_state,
        )
    if has_pending_reservation_payment and order.whatsapp_message_action_state in {
        "failed",
        "uncertain",
    }:
        uncertain = order.whatsapp_message_action_state == "uncertain"
        return _task(
            order,
            key_prefix="review-whatsapp",
            kind="review",
            title=(
                "Confirmar resultado de WhatsApp"
                if uncertain
                else "Revisar fallo de WhatsApp"
            ),
            description=(
                "El envío inicial terminó de forma ambigua y no debe repetirse "
                "automáticamente."
                if uncertain
                else "El envío automático falló y requiere una decisión del operador."
            ),
            label="WhatsApp",
            action="review_whatsapp",
            action_label="Revisar orden",
            tone="bad",
            state=order.whatsapp_message_action_state,
        )
    if order.payment_status == "pending" and order.reservation_status == "confirmed":
        task = _task(
            order,
            key_prefix="payment",
            kind="payment",
            title="Registrar pago pendiente",
            description=(
                "El contacto inicial ya fue atendido y la reserva sigue pendiente de cobro."
            ),
            label="Pago",
            action="register_payment",
            action_label="Registrar pago",
            tone="warn",
            state=order.payment_status,
        )
        task["amount_agreed"] = order.amount_agreed
        task["amount_paid"] = order.amount_paid
        return task
    if (
        _is_post_payment_whatsapp_candidate(order)
        and order.whatsapp_followup_action_state in {"failed", "uncertain"}
    ):
        uncertain = order.whatsapp_followup_action_state == "uncertain"
        return _task(
            order,
            key_prefix="review-followup",
            kind="review",
            title=(
                "Confirmar resultado post-pago"
                if uncertain
                else "Revisar fallo post-pago"
            ),
            description=(
                "El envío terminó de forma ambigua y no debe repetirse automáticamente."
                if uncertain
                else "El seguimiento automático falló y requiere una decisión del operador."
            ),
            label="Post-pago",
            action="review_post_payment_whatsapp",
            action_label="Revisar orden",
            tone="bad",
            state=order.whatsapp_followup_action_state,
        )
    return None


def _task(
    order: ServiceOrderSummary,
    *,
    key_prefix: str,
    kind: str,
    title: str,
    description: str,
    label: str,
    action: str,
    action_label: str,
    tone: str,
    state: str,
) -> dict[str, Any]:
    return {
        "key": f"{key_prefix}-{order.order_id}",
        "kind": kind,
        "order_id": order.order_id,
        "applicant_name": order.applicant_name,
        "document_number_masked": order.document_number_masked,
        "contact_name": order.contact_name,
        "contact_whatsapp_masked": order.contact_whatsapp_masked,
        "contact_whatsapp_username_masked": order.contact_whatsapp_username_masked,
        "title": title,
        "description": description,
        "label": label,
        "action": action,
        "action_label": action_label,
        "tone": tone,
        "severity": tone,
        "state": state,
        "updated_at": order.updated_at,
    }


def _is_post_payment_whatsapp_candidate(order: ServiceOrderSummary) -> bool:
    return (
        order.status == "paid"
        and order.reservation_status == "confirmed"
        and order.payment_status == "paid"
    )


__all__ = ["operator_inbox_payload"]
