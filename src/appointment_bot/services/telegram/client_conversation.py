from __future__ import annotations

import logging
import secrets
import time
from threading import Lock, Timer
from typing import Any
from urllib.error import HTTPError, URLError

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe, _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.client_forms import (
    _apply_new_client_value,
    _new_client_prompt_markup,
)
from appointment_bot.services.telegram.constants import (
    NEW_CLIENT_CONFIRMATION_TTL_SECONDS,
    NEW_CLIENT_CONVERSATION_TTL_SECONDS,
    SENSITIVE_MESSAGE_TTL_SECONDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import NewClientConversation, PendingClientCreation
from appointment_bot.services.telegram.order_queries import _wait_for_order_preflight
from appointment_bot.services.telegram.presentation import (
    _format_manual_client_details,
    _format_new_client_confirmation,
    _order_status_label,
    _preflight_status_label,
)
from appointment_bot.services.telegram.state import _cancel_pending_client_creation_unlocked

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _start_new_client_conversation(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> None:
    if arguments:
        telegram.send_message(chat_id, "Uso: /cliente_nuevo")
        return
    with confirmation_lock:
        _cancel_pending_client_creation_unlocked(chat_id, pending_creations)
        conversations[chat_id] = NewClientConversation(
            chat_id=chat_id,
            session_id=secrets.token_hex(4),
            values={},
            step=0,
            expires_at=time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS,
        )
    conversation = conversations[chat_id]
    message = (
        "ALTA MANUAL\n\nPaso 1: elige el tipo de documento.\n"
        "La contrasena se ocultara y el mensaje donde la escribas se intentara borrar. "
        "Puedes cancelar con /cancelar."
    )
    telegram.send_message(
        chat_id,
        message,
        reply_markup=_new_client_prompt_markup(conversation),
    )


def _process_new_client_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        conversation = conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        with confirmation_lock:
            conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "El registro vencio. Inicia nuevamente con /cliente_nuevo.",
        )
        return True
    return _continue_new_client_conversation(
        conversation,
        text.strip(),
        telegram,
        conversations,
        pending_creations,
        confirmation_lock,
    )


def _continue_new_client_conversation(
    conversation: NewClientConversation,
    value: str,
    telegram: TelegramBotApi,
    conversations: dict[str, NewClientConversation],
    pending_creations: dict[str, PendingClientCreation],
    confirmation_lock: Lock,
) -> bool:
    chat_id = conversation.chat_id
    try:
        prompt = _apply_new_client_value(conversation, value)
    except ValueError as exc:
        conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
        telegram.send_message(chat_id, str(exc))
        return True
    conversation.expires_at = time.monotonic() + NEW_CLIENT_CONVERSATION_TTL_SECONDS
    if prompt is not None:
        telegram.send_message(
            chat_id,
            f"{prompt}\nTienes 3 minutos para completar este paso.",
            reply_markup=_new_client_prompt_markup(conversation),
        )
        return True
    with confirmation_lock:
        conversations.pop(chat_id, None)
        _cancel_pending_client_creation_unlocked(chat_id, pending_creations)
        creation = PendingClientCreation(
            operation_id=secrets.token_hex(6),
            chat_id=chat_id,
            values=dict(conversation.values),
            expires_at=time.monotonic() + NEW_CLIENT_CONFIRMATION_TTL_SECONDS,
        )
        pending_creations[creation.operation_id] = creation
    telegram.send_message(
        chat_id,
        _format_new_client_confirmation(creation.values),
        reply_markup={
            "inline_keyboard": [[
                {
                    "text": "Crear cliente",
                    "callback_data": f"nc:{creation.operation_id}:yes",
                },
                {"text": "Cancelar", "callback_data": f"nc:{creation.operation_id}:no"},
            ]]
        },
    )
    return True


def _execute_client_creation(
    creation: PendingClientCreation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    actor = _telegram_actor(creation.chat_id)
    confirmation = "direct"
    try:
        created = admin_api.create_service_order(creation.values, actor=actor)
        order_id = str(created.get("order_id") or "")
        if not order_id:
            raise TelegramControlError("Admin API did not return an order_id.")
    except TelegramControlError as exc:
        reason = _client_creation_error_reason(exc)
        recovered = (
            _recover_persisted_client_creation(admin_api, creation.values)
            if reason in {
                "admin_api_timeout",
                "admin_api_unreachable",
                "admin_api_invalid_response",
            }
            else None
        )
        if recovered is None:
            logger.warning("Telegram manual client creation failed: %s", exc)
            _send_client_creation_message_safe(
                telegram,
                creation.chat_id,
                "No pude confirmar el alta. Consulta Clientes antes de volver a intentarlo.",
            )
            _record_audit_safe(
                actor=actor,
                action="client_create",
                status="failed",
                operation_id=creation.operation_id,
                detail=f"stage=create; reason={reason}",
            )
            return
        created = recovered
        order_id = str(recovered["order_id"])
        confirmation = f"recovered_after_{reason}"
        logger.warning(
            "Recovered persisted Telegram client creation after %s order_id=%s",
            reason,
            order_id,
        )

    try:
        telegram.send_message(
            creation.chat_id,
            f"CLIENTE CREADO\n\nOrden: {order_id}\nValidando el acceso al portal...",
        )
        order = _wait_for_order_preflight(admin_api, order_id)
        preflight = str(order.get("preflight_status") or "pending")
        credentials_note = ""
        try:
            credentials = admin_api.get_service_order_credentials(order_id)
        except TelegramControlError as exc:
            logger.warning("Could not reread credentials after manual creation: %s", exc)
            credentials = {}
            credentials_note = (
                "\nNota: no pude releer las credenciales desde la API; "
                "el comprobante usa los valores confirmados durante el alta."
            )
        persisted_values = {
            "document_type": credentials.get("document_type")
            or order.get("document_type")
            or creation.values.get("document_type"),
            "document_number": credentials.get("username")
            or order.get("document_number")
            or creation.values.get("document_number"),
            "password": credentials.get("password") or creation.values.get("password"),
            "contact_name": order.get("contact_name")
            or creation.values.get("contact_name"),
            "contact_source": order.get("contact_source")
            or creation.values.get("contact_source"),
            "contact_whatsapp": order.get("contact_whatsapp")
            or creation.values.get("contact_whatsapp"),
            "contact_whatsapp_username": order.get("contact_whatsapp_username")
            or creation.values.get("contact_whatsapp_username"),
            "service_type": order.get("service_type")
            or creation.values.get("service_type"),
            "reservation_price": order.get("reservation_price")
            or creation.values.get("reservation_price"),
            "minimum_reservation_date": order.get("minimum_reservation_date")
            if "minimum_reservation_date" in order
            else creation.values.get("minimum_reservation_date"),
            "maximum_reservation_date": order.get("maximum_reservation_date")
            if "maximum_reservation_date" in order
            else creation.values.get("maximum_reservation_date"),
            "allowed_weekdays": order.get("allowed_weekdays")
            if "allowed_weekdays" in order
            else creation.values.get("allowed_weekdays"),
            "excluded_date_ranges": order.get("excluded_date_ranges")
            if "excluded_date_ranges" in order
            else creation.values.get("excluded_date_ranges"),
        }
        if preflight == "validated":
            result = "Acceso correcto. La orden ya puede buscar cupos."
        elif preflight == "failed":
            result = "El acceso requiere revision. La orden quedo pausada."
        else:
            result = "La validacion sigue en curso. Consulta el cliente en unos segundos."
        telegram.send_message(
            creation.chat_id,
            _format_manual_client_details(
                persisted_values,
                title="ALTA MANUAL REGISTRADA",
            )
            + "\n\n"
            + f"Orden: {order_id}\n"
            + f"Titular del portal: {order.get('applicant_name') or 'aun no identificado'}\n"
            + f"Estado: {_order_status_label(order.get('status') or created.get('status'))}\n"
            + f"Preflight: {_preflight_status_label(preflight)}\n"
            + f"Detalle: {order.get('preflight_message') or result}"
            + credentials_note,
            reply_markup={
                "inline_keyboard": [
                    [{"text": "Ver cliente", "callback_data": f"om:{order_id}:show"}],
                    [{"text": "Menu", "callback_data": "ui:menu:main"}],
                ]
            },
        )
        persisted_password = str(persisted_values.get("password") or "")
        if persisted_password:
            sensitive_message = telegram.send_message(
                creation.chat_id,
                "CREDENCIAL TEMPORAL\n\n"
                f"Contrasena: {persisted_password}\n\n"
                "Guardala y pulsa Borrar credencial para retirarla del chat.",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "Borrar credencial", "callback_data": "ui:delete:message"}
                    ]]
                },
            )
            sensitive_result = sensitive_message.get("result")
            sensitive_message_id = (
                sensitive_result.get("message_id")
                if isinstance(sensitive_result, dict)
                else None
            )
            if isinstance(sensitive_message_id, int):
                timer = Timer(
                    SENSITIVE_MESSAGE_TTL_SECONDS,
                    _delete_sensitive_message,
                    args=(telegram, creation.chat_id, sensitive_message_id),
                )
                timer.daemon = True
                timer.start()
        logger.info("Created service order from Telegram actor=%s order_id=%s", actor, order_id)
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=f"preflight_status={preflight}; confirmation={confirmation}",
        )
    except TelegramControlError as exc:
        reason = _client_creation_error_reason(exc)
        logger.warning(
            "Telegram client creation persisted but follow-up failed: %s",
            exc,
        )
        _send_client_creation_message_safe(
            telegram,
            creation.chat_id,
            f"El alta quedo registrada como {order_id}, pero no pude completar "
            "la comprobacion posterior. Consulta Clientes; no repitas el alta.",
        )
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=(
                f"confirmation={confirmation}; followup=incomplete; reason={reason}"
            ),
        )
    except Exception:
        logger.exception("Unexpected Telegram manual client creation failure")
        _send_client_creation_message_safe(
            telegram,
            creation.chat_id,
            f"El alta quedo registrada como {order_id}, pero ocurrio un error "
            "durante la comprobacion posterior. Consulta Clientes; no repitas el alta.",
        )
        _record_audit_safe(
            actor=actor,
            action="client_create",
            status="applied",
            target_type="service_order",
            target_id=order_id,
            operation_id=creation.operation_id,
            detail=f"confirmation={confirmation}; followup=unexpected_error",
        )


def _delete_sensitive_message(
    telegram: TelegramBotApi,
    chat_id: str,
    message_id: int,
) -> None:
    try:
        telegram.delete_message(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not automatically delete a sensitive Telegram message.")


def _delete_message_safe(
    telegram: TelegramBotApi,
    chat_id: str,
    message_id: Any,
) -> None:
    if not isinstance(message_id, int):
        return
    try:
        telegram.delete_message(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not delete Telegram password input message.")


def _recover_persisted_client_creation(
    admin_api: AdminApiClient,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    document_number = str(values.get("document_number") or "").strip()
    if not document_number:
        return None
    try:
        candidates = admin_api.search_service_orders(document_number)
    except TelegramControlError as exc:
        logger.warning("Could not verify persisted Telegram client creation: %s", exc)
        return None

    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        if str(candidate.get("document_number") or "").strip() != document_number:
            continue
        if candidate.get("parent_order_id") or candidate.get("program_expediente"):
            continue
        if candidate.get("program_plate"):
            continue
        order_id = str(candidate.get("order_id") or "").strip()
        if not order_id:
            continue
        try:
            credentials = admin_api.get_service_order_credentials(order_id)
        except TelegramControlError as exc:
            logger.warning(
                "Could not verify credentials for recovered order_id=%s: %s",
                order_id,
                exc,
            )
            continue
        if not _persisted_client_creation_matches(values, candidate, credentials):
            continue
        matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _persisted_client_creation_matches(
    values: dict[str, Any],
    order: dict[str, Any],
    credentials: dict[str, Any],
) -> bool:
    expected_credentials = {
        "username": str(values.get("document_number") or "").strip(),
        "document_type": str(values.get("document_type") or "").strip(),
        "password": str(values.get("password") or ""),
    }
    if any(credentials.get(field) != expected for field, expected in expected_credentials.items()):
        return False

    comparable_fields = (
        "contact_name",
        "contact_source",
        "contact_whatsapp",
        "contact_whatsapp_username",
        "service_type",
        "service_package",
        "reservation_price",
        "minimum_reservation_date",
        "maximum_reservation_date",
        "allowed_weekdays",
        "excluded_date_ranges",
    )
    return all(
        field not in values
        or values[field] is None
        or order.get(field) == values[field]
        for field in comparable_fields
    )


def _client_creation_error_reason(exc: TelegramControlError) -> str:
    if str(exc).startswith("Telegram "):
        return "telegram_delivery_error"
    cause = exc.__cause__
    nested_reason = getattr(cause, "reason", None)
    if isinstance(cause, TimeoutError) or isinstance(nested_reason, TimeoutError):
        return "admin_api_timeout"
    if isinstance(cause, HTTPError):
        return f"admin_api_http_{cause.code}"
    if isinstance(cause, URLError):
        return "admin_api_unreachable"
    if "did not return an order_id" in str(exc) or "invalid JSON" in str(exc):
        return "admin_api_invalid_response"
    return "admin_api_confirmation_error"


def _send_client_creation_message_safe(
    telegram: TelegramBotApi,
    chat_id: str,
    message: str,
) -> bool:
    try:
        telegram.send_message(chat_id, message)
    except TelegramControlError as exc:
        logger.warning("Could not send Telegram client creation status: %s", exc)
        return False
    return True
