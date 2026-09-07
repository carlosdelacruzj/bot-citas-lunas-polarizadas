from __future__ import annotations

import logging
import secrets
import time
from collections import deque
from threading import Lock
from typing import Any

from appointment_bot.services import telegram_program_resolution
from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.captcha_conversation import (
    _clear_captcha_review_buttons,
    _start_captcha_review,
)
from appointment_bot.services.telegram.client_conversation import (
    _continue_new_client_conversation,
    _start_new_client_conversation,
)
from appointment_bot.services.telegram.client_forms import (
    _new_client_prompt_markup,
    _rewind_new_client,
)
from appointment_bot.services.telegram.constants import (
    CONFIRMATION_TTL_SECONDS,
    CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation,
    NewClientConversation,
    PendingClientCreation,
    PendingOrderChange,
    PendingWorkerConfirmation,
    RulesConversation,
    SearchConversation,
)
from appointment_bot.services.telegram.order_changes import (
    _request_payment_change,
    _request_priority_change,
)
from appointment_bot.services.telegram.panels import (
    _send_clients,
    _send_daily_summary,
    _send_main_menu,
    _send_order_panel,
    _send_order_query,
    _send_payment_menu,
    _send_pending_attention,
    _send_pending_payments,
    _send_priority_menu,
    _send_queue,
    _send_recent_errors,
    _send_tools_menu,
)
from appointment_bot.services.telegram.presentation import _main_menu_markup
from appointment_bot.services.telegram.rules_conversation import (
    _continue_rules_conversation,
    _rules_prompt_markup,
    _rules_step_prompt,
    _start_rules_conversation,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_client_state,
    _cancel_chat_confirmations_unlocked,
    _cancel_chat_order_state,
    _cancel_pending_client_creation_unlocked,
)
from appointment_bot.services.telegram.validation import _valid_order_id
from appointment_bot.services.telegram.worker_controls import (
    _request_opportunity_confirmation,
    _request_worker_confirmation,
)
from appointment_bot.services.telegram.worker_panels import (
    _send_opportunity_panel,
    _send_worker_panel,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _process_interface_callback(
    callback_id: str,
    data: str,
    message: Any,
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    pending_client_creations: dict[str, PendingClientCreation],
    new_client_conversations: dict[str, NewClientConversation],
    rules_conversations: dict[str, RulesConversation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    confirmation_lock: Lock,
) -> bool:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {
        "ui", "om", "op", "pq", "py", "wk", "nf", "rf", "pr"
    }:
        return False
    prefix, subject, action = parts
    telegram.answer_callback_query(callback_id, "Procesando...")
    if prefix == "pr":
        if action in {"informed", "keep"}:
            telegram_program_resolution.set_communication_decision(
                chat_id, subject, action, telegram,
                pending_order_changes, confirmation_lock,
            )
        elif not _valid_order_id(subject):
            telegram.send_message(chat_id, "La orden seleccionada no es valida.")
        elif action == "show":
            telegram_program_resolution.send_panel(chat_id, subject, telegram, admin_api)
        else:
            telegram_program_resolution.request_resolution(
                chat_id, subject, action, telegram, admin_api,
                pending_order_changes, confirmation_lock, PendingOrderChange,
                confirmation_ttl_seconds=CONFIRMATION_TTL_SECONDS,
            )
        return True
    if prefix == "ui":
        if subject == "menu":
            _send_main_menu(chat_id, telegram, admin_api)
        elif subject == "status":
            _send_worker_panel(chat_id, telegram, admin_api)
        elif subject == "clients":
            _send_clients(chat_id, action, telegram, admin_api)
        elif subject == "pending":
            _send_pending_attention(chat_id, action, telegram, admin_api)
        elif subject == "queue":
            _send_queue(chat_id, action, telegram, admin_api)
        elif subject == "payments":
            _send_pending_payments(chat_id, action, telegram, admin_api)
        elif subject == "manual":
            search_conversations.pop(chat_id, None)
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            _start_new_client_conversation(
                chat_id,
                "",
                telegram,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
        elif subject == "search":
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS
            )
            telegram.send_message(
                chat_id,
                "BUSCAR CLIENTE\n\nEscribe el nombre, documento, WhatsApp u orden. "
                "Puedes cancelar con /cancelar.",
            )
        elif subject == "captcha":
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            search_conversations.pop(chat_id, None)
            _start_captcha_review(chat_id, telegram, admin_api, captcha_conversations)
        elif subject == "summary":
            _send_daily_summary(chat_id, telegram, admin_api)
        elif subject == "worker":
            _send_worker_panel(chat_id, telegram, admin_api)
        elif subject == "tools":
            _send_tools_menu(chat_id, telegram, admin_api)
        elif subject == "opportunity":
            _send_opportunity_panel(chat_id, telegram, admin_api)
        elif subject == "errors":
            _send_recent_errors(chat_id, telegram, admin_api)
        elif subject == "delete":
            message_id = message.get("message_id") if isinstance(message, dict) else None
            if isinstance(message_id, int):
                try:
                    telegram.delete_message(chat_id, message_id)
                except TelegramControlError:
                    telegram.send_message(chat_id, "No pude eliminar ese mensaje.")
        elif subject == "cancel":
            with confirmation_lock:
                removed = new_client_conversations.pop(chat_id, None) is not None
                removed = _cancel_pending_client_creation_unlocked(
                    chat_id, pending_client_creations
                ) or removed
                removed = rules_conversations.pop(chat_id, None) is not None or removed
                removed = search_conversations.pop(chat_id, None) is not None or removed
                removed = captcha_conversations.pop(chat_id, None) is not None or removed
            telegram.send_message(
                chat_id,
                "Operacion cancelada." if removed else "No habia una operacion activa.",
                reply_markup=_main_menu_markup(),
            )
        else:
            telegram.send_message(chat_id, "Accion de menu no reconocida.")
        return True
    if prefix == "op":
        action_text, separator, revision_text = action.rpartition("-r")
        if (
            subject not in {"obs006", "obs007"}
            or action_text not in {"activate", "deactivate", "drain", "reset_breaker"}
            or not separator
            or not revision_text.isdigit()
        ):
            telegram.send_message(chat_id, "Ese control de oportunidad ya no es valido.")
            return True
        _request_opportunity_confirmation(
            chat_id,
            action_text,
            subject,
            int(revision_text),
            telegram,
            admin_api,
            pending_confirmations,
            confirmation_lock,
        )
        return True
    if prefix == "om":
        order_id = subject
        if not _valid_order_id(order_id):
            telegram.send_message(chat_id, "La orden seleccionada no es valida.")
        elif action == "show" or action.startswith("show_"):
            return_subject = action.removeprefix("show_") if action != "show" else "clients"
            _send_order_panel(
                chat_id,
                order_id,
                telegram,
                admin_api,
                recent_orders,
                return_subject=return_subject,
            )
        elif action == "rules":
            _send_order_query(chat_id, "reglas", order_id, telegram, admin_api)
        elif action == "priority":
            _send_priority_menu(chat_id, order_id, telegram, admin_api)
        elif action == "access":
            try:
                current = admin_api.get_service_order(order_id)
            except TelegramControlError as exc:
                logger.warning("Could not prepare Telegram credential correction: %s", exc)
                telegram.send_message(chat_id, "No pude revisar el acceso de ese cliente.")
                return True
            preflight_details = current.get("preflight_details")
            error_type = (
                str(preflight_details.get("error_type") or "")
                if isinstance(preflight_details, dict)
                else ""
            )
            if (
                str(current.get("preflight_status") or "") != "failed"
                or error_type != "invalid_credentials"
            ):
                telegram.send_message(
                    chat_id,
                    "El acceso ya no figura como credenciales rechazadas. "
                    "Actualiza el cliente antes de continuar.",
                )
                return True
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _cancel_chat_order_state(
                chat_id,
                pending_order_changes,
                rules_conversations,
                confirmation_lock,
            )
            captcha_conversations.pop(chat_id, None)
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
                mode="credentials",
                order_id=order_id,
                return_subject="pending",
            )
            telegram.send_message(
                chat_id,
                "CORREGIR ACCESO\n\n"
                f"Cliente: {current.get('applicant_name') or 'sin nombre'}\n"
                f"Orden: {order_id}\n"
                f"Motivo: {current.get('preflight_message') or 'credenciales rechazadas'}\n\n"
                "Escribe la nueva contrasena del portal. El mensaje se intentara borrar "
                "inmediatamente y nada cambiara hasta que confirmes.\n\n"
                "Puedes cancelar con /cancelar.",
            )
        elif action == "validate":
            try:
                current = admin_api.get_service_order(order_id)
            except TelegramControlError as exc:
                logger.warning("Could not review order before revalidation: %s", exc)
                telegram.send_message(chat_id, "No pude revisar el estado actual.")
                return True
            if str(current.get("preflight_status") or "") != "failed":
                telegram.send_message(
                    chat_id,
                    "La validacion ya no esta fallida. Actualiza el cliente antes de continuar.",
                )
                return True
            operation_id = secrets.token_hex(6)
            with confirmation_lock:
                _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
                pending_confirmations[operation_id] = PendingWorkerConfirmation(
                    operation_id=operation_id,
                    chat_id=chat_id,
                    command=f"revalidate:{order_id}",
                    expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
                    opportunity_target=order_id,
                )
            telegram.send_message(
                chat_id,
                "CONFIRMAR NUEVA VALIDACION\n\n"
                f"Orden: {order_id}\n"
                f"Motivo actual: {current.get('preflight_message') or 'sin detalle'}\n\n"
                "Se iniciara una nueva comprobacion de acceso.",
                reply_markup={
                    "inline_keyboard": [[
                        {"text": "Volver a validar", "callback_data": f"wc:{operation_id}:yes"},
                        {"text": "Cancelar", "callback_data": f"wc:{operation_id}:no"},
                    ]]
                },
            )
        elif action == "editrules":
            search_conversations.pop(chat_id, None)
            captcha_conversations.pop(chat_id, None)
            _cancel_chat_client_state(
                chat_id,
                new_client_conversations,
                pending_client_creations,
                confirmation_lock,
            )
            _start_rules_conversation(
                chat_id,
                order_id,
                telegram,
                admin_api,
                rules_conversations,
                pending_order_changes,
                confirmation_lock,
            )
        else:
            telegram.send_message(chat_id, "Accion de cliente no reconocida.")
        return True
    if prefix == "pq":
        _request_priority_change(
            chat_id,
            f"{subject} {action}",
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return True
    if prefix == "py":
        action_name, separator, return_subject = action.partition("_")
        if action == "default":
            action_name, return_subject = "full", "menu"
        if (
            not separator
            and action != "default"
            or action_name not in {"choose", "full", "partial"}
            or return_subject
            not in {"menu", "pending", "payments", "queue", "summary", "clients"}
        ):
            telegram.send_message(chat_id, "Opcion de pago no reconocida.")
        elif action_name == "choose":
            _send_payment_menu(
                chat_id,
                subject,
                return_subject,
                telegram,
                admin_api,
            )
        elif action_name == "partial":
            search_conversations[chat_id] = SearchConversation(
                expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
                mode="payment",
                order_id=subject,
                return_subject=return_subject,
            )
            telegram.send_message(
                chat_id,
                "REGISTRAR ABONO\n\nEscribe el total acumulado pagado, no solo "
                "el ultimo abono. Ejemplo: 40.00\n\nPuedes cancelar con /cancelar.",
            )
        else:
            _request_payment_change(
                chat_id,
                subject,
                telegram,
                admin_api,
                pending_order_changes,
                confirmation_lock,
                return_subject=return_subject,
            )
        return True
    if prefix == "wk":
        if subject not in {"pause", "resume", "restart"}:
            telegram.send_message(chat_id, "Accion de worker no reconocida.")
        else:
            _request_worker_confirmation(
                chat_id,
                subject,
                telegram,
                pending_confirmations,
                confirmation_lock,
            )
        return True
    if prefix == "rf":
        conversation = rules_conversations.get(chat_id)
        if conversation is None:
            telegram.send_message(chat_id, "La edicion de reglas ya no esta activa.")
            return True
        if subject == "nav" and action == "back":
            if conversation.step > 0:
                conversation.step -= 1
                field = (
                    "minimum_reservation_date",
                    "maximum_reservation_date",
                    "allowed_weekdays",
                    "excluded_date_ranges",
                )[conversation.step]
                conversation.updated[field] = conversation.original.get(field)
            conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
            _clear_captcha_review_buttons(chat_id, message, telegram)
            telegram.send_message(
                chat_id,
                _rules_step_prompt(conversation.step),
                reply_markup=_rules_prompt_markup(conversation.step),
            )
            return True
        values = {
            ("value", "keep"): "igual",
            ("value", "clear"): "quitar",
            ("days", "mon_fri"): "1,2,3,4,5",
            ("days", "mon_sat"): "1,2,3,4,5,6",
            ("days", "sat"): "6",
        }
        value = values.get((subject, action))
        if value is None:
            telegram.send_message(chat_id, "Opcion de reglas no reconocida.")
            return True
        _clear_captcha_review_buttons(chat_id, message, telegram)
        _continue_rules_conversation(
            conversation,
            value,
            telegram,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        )
        return True
    conversation = new_client_conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        _cancel_chat_client_state(
            chat_id,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        telegram.send_message(
            chat_id,
            "Ese boton ya vencio. Inicia otra vez desde el menu.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if conversation.session_id != subject:
        telegram.send_message(
            chat_id,
            "Ese boton pertenece a otro registro y ya no es valido.",
        )
        return True
    if action == "back":
        prompt = _rewind_new_client(conversation)
        _clear_captcha_review_buttons(chat_id, message, telegram)
        telegram.send_message(
            chat_id,
            f"{prompt}\nTienes 3 minutos para completar este paso.",
            reply_markup=_new_client_prompt_markup(conversation),
        )
        return True
    values = {
        "type_dni": "dni",
        "type_ce": "ce",
        "source_tiktok": "tiktok",
        "source_facebook": "facebook",
        "source_whatsapp": "whatsapp",
        "phone_number": "WHATSAPP_NUMERO",
        "phone_username": "WHATSAPP_USUARIO",
        "phone_omit": "OMITIR",
        "service_standard": "SERVICIO_ESTANDAR",
        "service_weekday": "SERVICIO_DIA_ELEGIDO",
        "service_integral": "SERVICIO_INTEGRAL",
        "service_custom": "SERVICIO_PERSONALIZADO",
        "rules_none": "SIN_RESTRICCIONES",
        "rules_yes": "CON_RESTRICCIONES",
        "value_clear": "quitar",
        "days_mon_fri": "1,2,3,4,5",
        "days_mon_sat": "1,2,3,4,5,6",
        "days_sat": "6",
        "weekday_1": "1",
        "weekday_2": "2",
        "weekday_3": "3",
        "weekday_4": "4",
        "weekday_5": "5",
        "weekday_6": "6",
        "weekday_7": "7",
    }
    value = values.get(action)
    if value is None:
        telegram.send_message(chat_id, "Opcion de registro no reconocida.")
        return True
    _clear_captcha_review_buttons(chat_id, message, telegram)
    _continue_new_client_conversation(
        conversation,
        value,
        telegram,
        new_client_conversations,
        pending_client_creations,
        confirmation_lock,
    )
    return True
