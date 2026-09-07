from __future__ import annotations

import argparse
import logging
import signal
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event, Lock
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.telegram.access import TelegramRateLimiter as TelegramRateLimiter
from appointment_bot.services.telegram.access import _callback_is_mutation as _callback_is_mutation
from appointment_bot.services.telegram.access import _command_parts as _command_parts
from appointment_bot.services.telegram.access import (
    _mutation_user_authorized as _mutation_user_authorized,
)
from appointment_bot.services.telegram.admin_api_client import AdminApiClient as AdminApiClient
from appointment_bot.services.telegram.audit import _audit_target as _audit_target
from appointment_bot.services.telegram.audit import _record_audit_safe as _record_audit_safe
from appointment_bot.services.telegram.audit import _telegram_actor as _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi as TelegramBotApi
from appointment_bot.services.telegram.bot_api import _multipart_form_data as _multipart_form_data
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_model_short_label as _captcha_model_short_label,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_prediction_choices as _captcha_prediction_choices,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_review_markup as _captcha_review_markup,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _captcha_review_reason as _captcha_review_reason,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _clear_captcha_review_buttons as _clear_captcha_review_buttons,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _next_pending_captcha as _next_pending_captcha,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _process_captcha_review_callback as _process_captcha_review_callback,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _process_captcha_review_message as _process_captcha_review_message,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _save_captcha_review_answer as _save_captcha_review_answer,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _send_next_captcha_review as _send_next_captcha_review,
)
from appointment_bot.services.telegram.captcha_conversation import (
    _start_captcha_review as _start_captcha_review,
)
from appointment_bot.services.telegram.client_conversation import (
    _client_creation_error_reason as _client_creation_error_reason,
)
from appointment_bot.services.telegram.client_conversation import (
    _continue_new_client_conversation as _continue_new_client_conversation,
)
from appointment_bot.services.telegram.client_conversation import (
    _delete_message_safe as _delete_message_safe,
)
from appointment_bot.services.telegram.client_conversation import (
    _delete_sensitive_message as _delete_sensitive_message,
)
from appointment_bot.services.telegram.client_conversation import (
    _execute_client_creation as _execute_client_creation,
)
from appointment_bot.services.telegram.client_conversation import (
    _persisted_client_creation_matches as _persisted_client_creation_matches,
)
from appointment_bot.services.telegram.client_conversation import (
    _process_new_client_message as _process_new_client_message,
)
from appointment_bot.services.telegram.client_conversation import (
    _recover_persisted_client_creation as _recover_persisted_client_creation,
)
from appointment_bot.services.telegram.client_conversation import (
    _send_client_creation_message_safe as _send_client_creation_message_safe,
)
from appointment_bot.services.telegram.client_conversation import (
    _start_new_client_conversation as _start_new_client_conversation,
)
from appointment_bot.services.telegram.client_forms import (
    _apply_manual_client_value as _apply_manual_client_value,
)
from appointment_bot.services.telegram.client_forms import (
    _apply_new_client_value as _apply_new_client_value,
)
from appointment_bot.services.telegram.client_forms import (
    _fixed_service_package_values as _fixed_service_package_values,
)
from appointment_bot.services.telegram.client_forms import (
    _manual_client_step_prompt as _manual_client_step_prompt,
)
from appointment_bot.services.telegram.client_forms import (
    _new_client_prompt_markup as _new_client_prompt_markup,
)
from appointment_bot.services.telegram.client_forms import _rewind_new_client as _rewind_new_client
from appointment_bot.services.telegram.client_forms import (
    _telegram_service_package_option as _telegram_service_package_option,
)
from appointment_bot.services.telegram.config import _positive_int as _positive_int
from appointment_bot.services.telegram.config import (
    _validated_admin_api_url as _validated_admin_api_url,
)
from appointment_bot.services.telegram.config import load_control_config as load_control_config
from appointment_bot.services.telegram.constants import (
    CAPTCHA_REVIEW_TTL_SECONDS as CAPTCHA_REVIEW_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import CLIENTS_PAGE_SIZE as CLIENTS_PAGE_SIZE
from appointment_bot.services.telegram.constants import (
    CONFIRMATION_TTL_SECONDS as CONFIRMATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    CONVERSATION_TTL_SECONDS as CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    DEFAULT_ADMIN_API_URL as DEFAULT_ADMIN_API_URL,
)
from appointment_bot.services.telegram.constants import (
    DEFAULT_POLL_TIMEOUT_SECONDS as DEFAULT_POLL_TIMEOUT_SECONDS,
)
from appointment_bot.services.telegram.constants import GENERAL_RATE_LIMIT as GENERAL_RATE_LIMIT
from appointment_bot.services.telegram.constants import HELP_TEXT as HELP_TEXT
from appointment_bot.services.telegram.constants import LIMA_TIMEZONE as LIMA_TIMEZONE
from appointment_bot.services.telegram.constants import MUTATING_COMMANDS as MUTATING_COMMANDS
from appointment_bot.services.telegram.constants import MUTATION_RATE_LIMIT as MUTATION_RATE_LIMIT
from appointment_bot.services.telegram.constants import (
    NEW_CLIENT_CONFIRMATION_TTL_SECONDS as NEW_CLIENT_CONFIRMATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    NEW_CLIENT_CONVERSATION_TTL_SECONDS as NEW_CLIENT_CONVERSATION_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    ORDER_TARGET_COMMANDS as ORDER_TARGET_COMMANDS,
)
from appointment_bot.services.telegram.constants import (
    RATE_LIMIT_WINDOW_SECONDS as RATE_LIMIT_WINDOW_SECONDS,
)
from appointment_bot.services.telegram.constants import RETRY_DELAY_SECONDS as RETRY_DELAY_SECONDS
from appointment_bot.services.telegram.constants import (
    SENSITIVE_MESSAGE_TTL_SECONDS as SENSITIVE_MESSAGE_TTL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_COMMAND_TIMEOUT_SECONDS as WORKER_COMMAND_TIMEOUT_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_END_MINUTE as WORKER_MONITOR_END_MINUTE,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_FAILURE_THRESHOLD as WORKER_MONITOR_FAILURE_THRESHOLD,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_INTERVAL_SECONDS as WORKER_MONITOR_INTERVAL_SECONDS,
)
from appointment_bot.services.telegram.constants import (
    WORKER_MONITOR_START_MINUTE as WORKER_MONITOR_START_MINUTE,
)
from appointment_bot.services.telegram.errors import TelegramControlError as TelegramControlError
from appointment_bot.services.telegram.interface_callbacks import (
    _process_interface_callback as _process_interface_callback,
)
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation as CaptchaReviewConversation,
)
from appointment_bot.services.telegram.models import NewClientConversation as NewClientConversation
from appointment_bot.services.telegram.models import PendingClientCreation as PendingClientCreation
from appointment_bot.services.telegram.models import PendingOrderChange as PendingOrderChange
from appointment_bot.services.telegram.models import (
    PendingWorkerConfirmation as PendingWorkerConfirmation,
)
from appointment_bot.services.telegram.models import RulesConversation as RulesConversation
from appointment_bot.services.telegram.models import SearchConversation as SearchConversation
from appointment_bot.services.telegram.models import TelegramControlConfig as TelegramControlConfig
from appointment_bot.services.telegram.order_changes import (
    _execute_order_change as _execute_order_change,
)
from appointment_bot.services.telegram.order_changes import (
    _execute_order_revalidation as _execute_order_revalidation,
)
from appointment_bot.services.telegram.order_changes import (
    _order_change_matches as _order_change_matches,
)
from appointment_bot.services.telegram.order_changes import (
    _request_credentials_change as _request_credentials_change,
)
from appointment_bot.services.telegram.order_changes import (
    _request_payment_change as _request_payment_change,
)
from appointment_bot.services.telegram.order_changes import (
    _request_priority_change as _request_priority_change,
)
from appointment_bot.services.telegram.order_changes import (
    _send_order_change_confirmation as _send_order_change_confirmation,
)
from appointment_bot.services.telegram.order_changes import (
    _store_order_change as _store_order_change,
)
from appointment_bot.services.telegram.order_queries import (
    _wait_for_order_preflight as _wait_for_order_preflight,
)
from appointment_bot.services.telegram.panels import _parse_list_page as _parse_list_page
from appointment_bot.services.telegram.panels import _send_clients as _send_clients
from appointment_bot.services.telegram.panels import _send_daily_summary as _send_daily_summary
from appointment_bot.services.telegram.panels import _send_main_menu as _send_main_menu
from appointment_bot.services.telegram.panels import (
    _send_operational_order_list as _send_operational_order_list,
)
from appointment_bot.services.telegram.panels import _send_order_panel as _send_order_panel
from appointment_bot.services.telegram.panels import _send_order_query as _send_order_query
from appointment_bot.services.telegram.panels import _send_payment_menu as _send_payment_menu
from appointment_bot.services.telegram.panels import (
    _send_pending_attention as _send_pending_attention,
)
from appointment_bot.services.telegram.panels import (
    _send_pending_payments as _send_pending_payments,
)
from appointment_bot.services.telegram.panels import _send_priority_menu as _send_priority_menu
from appointment_bot.services.telegram.panels import _send_queue as _send_queue
from appointment_bot.services.telegram.panels import _send_recent_errors as _send_recent_errors
from appointment_bot.services.telegram.panels import _send_search_results as _send_search_results
from appointment_bot.services.telegram.panels import _send_tools_menu as _send_tools_menu
from appointment_bot.services.telegram.presentation import (
    _applicant_display_name as _applicant_display_name,
)
from appointment_bot.services.telegram.presentation import _change_value as _change_value
from appointment_bot.services.telegram.presentation import _display_text as _display_text
from appointment_bot.services.telegram.presentation import (
    _format_excluded_date_ranges as _format_excluded_date_ranges,
)
from appointment_bot.services.telegram.presentation import (
    _format_lima_datetime as _format_lima_datetime,
)
from appointment_bot.services.telegram.presentation import (
    _format_manual_client_details as _format_manual_client_details,
)
from appointment_bot.services.telegram.presentation import (
    _format_new_client_confirmation as _format_new_client_confirmation,
)
from appointment_bot.services.telegram.presentation import (
    _format_operator_date as _format_operator_date,
)
from appointment_bot.services.telegram.presentation import (
    _format_opportunity_control as _format_opportunity_control,
)
from appointment_bot.services.telegram.presentation import (
    _format_order_change_comparison as _format_order_change_comparison,
)
from appointment_bot.services.telegram.presentation import (
    _format_worker_command_success as _format_worker_command_success,
)
from appointment_bot.services.telegram.presentation import _is_failed_run as _is_failed_run
from appointment_bot.services.telegram.presentation import _main_menu_markup as _main_menu_markup
from appointment_bot.services.telegram.presentation import _money_text as _money_text
from appointment_bot.services.telegram.presentation import (
    _order_status_counts as _order_status_counts,
)
from appointment_bot.services.telegram.presentation import (
    _order_status_label as _order_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _payment_status_label as _payment_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _preflight_status_label as _preflight_status_label,
)
from appointment_bot.services.telegram.presentation import (
    _reservation_status_label as _reservation_status_label,
)
from appointment_bot.services.telegram.presentation import _safe_run_message as _safe_run_message
from appointment_bot.services.telegram.presentation import (
    _service_scope_text as _service_scope_text,
)
from appointment_bot.services.telegram.presentation import (
    _service_type_label as _service_type_label,
)
from appointment_bot.services.telegram.presentation import _short_text as _short_text
from appointment_bot.services.telegram.presentation import _weekday_name as _weekday_name
from appointment_bot.services.telegram.presentation import (
    _worker_command_label as _worker_command_label,
)
from appointment_bot.services.telegram.presentation import (
    format_order_detail as format_order_detail,
)
from appointment_bot.services.telegram.presentation import format_order_rules as format_order_rules
from appointment_bot.services.telegram.presentation import (
    format_worker_status as format_worker_status,
)
from appointment_bot.services.telegram.rules_conversation import (
    _continue_rules_conversation as _continue_rules_conversation,
)
from appointment_bot.services.telegram.rules_conversation import (
    _process_rules_conversation_message as _process_rules_conversation_message,
)
from appointment_bot.services.telegram.rules_conversation import (
    _rules_prompt_markup as _rules_prompt_markup,
)
from appointment_bot.services.telegram.rules_conversation import (
    _rules_step_prompt as _rules_step_prompt,
)
from appointment_bot.services.telegram.rules_conversation import (
    _start_rules_conversation as _start_rules_conversation,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_client_state as _cancel_chat_client_state,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_confirmations as _cancel_chat_confirmations,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_confirmations_unlocked as _cancel_chat_confirmations_unlocked,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_order_state as _cancel_chat_order_state,
)
from appointment_bot.services.telegram.state import (
    _cancel_chat_order_state_unlocked as _cancel_chat_order_state_unlocked,
)
from appointment_bot.services.telegram.state import (
    _cancel_pending_client_creation_unlocked as _cancel_pending_client_creation_unlocked,
)
from appointment_bot.services.telegram.state import _load_next_offset as _load_next_offset
from appointment_bot.services.telegram.state import (
    _remove_expired_captcha_state as _remove_expired_captcha_state,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_client_state as _remove_expired_client_state,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_confirmations as _remove_expired_confirmations,
)
from appointment_bot.services.telegram.state import (
    _remove_expired_order_state as _remove_expired_order_state,
)
from appointment_bot.services.telegram.state import _store_next_offset as _store_next_offset
from appointment_bot.services.telegram.state import _update_id as _update_id
from appointment_bot.services.telegram.transport import (
    MAX_TELEGRAM_RESPONSE_BYTES as MAX_TELEGRAM_RESPONSE_BYTES,
)
from appointment_bot.services.telegram.transport import (
    _read_json_response as _read_json_response,
)
from appointment_bot.services.telegram.validation import _money_value as _money_value
from appointment_bot.services.telegram.validation import _parse_rules_step as _parse_rules_step
from appointment_bot.services.telegram.validation import (
    _parse_single_weekday as _parse_single_weekday,
)
from appointment_bot.services.telegram.validation import _payment_balance as _payment_balance
from appointment_bot.services.telegram.validation import _rules_payload as _rules_payload
from appointment_bot.services.telegram.validation import _valid_order_id as _valid_order_id
from appointment_bot.services.telegram.validation import (
    _validate_rules_payload as _validate_rules_payload,
)
from appointment_bot.services.telegram.validation import (
    _validated_payment_amount as _validated_payment_amount,
)
from appointment_bot.services.telegram.worker_controls import (
    WorkerHealthMonitor as WorkerHealthMonitor,
)
from appointment_bot.services.telegram.worker_controls import (
    _execute_opportunity_control as _execute_opportunity_control,
)
from appointment_bot.services.telegram.worker_controls import (
    _execute_worker_command as _execute_worker_command,
)
from appointment_bot.services.telegram.worker_controls import (
    _request_opportunity_confirmation as _request_opportunity_confirmation,
)
from appointment_bot.services.telegram.worker_controls import (
    _request_worker_confirmation as _request_worker_confirmation,
)
from appointment_bot.services.telegram.worker_controls import (
    _wait_for_worker_command as _wait_for_worker_command,
)
from appointment_bot.services.telegram.worker_controls import (
    _wait_for_worker_effect as _wait_for_worker_effect,
)
from appointment_bot.services.telegram.worker_panels import (
    _send_opportunity_panel as _send_opportunity_panel,
)
from appointment_bot.services.telegram.worker_panels import _send_worker_panel as _send_worker_panel

logger = logging.getLogger("appointment_bot.services.telegram_control")


def run_control(*, check_only: bool = False) -> int:
    settings = load_settings(require_login=False)
    setup_logging(settings)
    config = load_control_config(settings)
    telegram = TelegramBotApi(config.bot_token)
    admin_api = AdminApiClient(config.admin_api_url, config.admin_api_token)
    identity = telegram.get_me().get("result", {})
    webhook = telegram.get_webhook_info().get("result", {})
    if webhook.get("url"):
        raise TelegramControlError("Telegram has a webhook configured; long polling cannot start.")
    worker = admin_api.get_worker()
    logger.info(
        "Telegram control validated for bot_id=%s, authorized_chats=%s, worker_phase=%s",
        identity.get("id"),
        len(config.authorized_chat_ids),
        worker.get("phase"),
    )
    if check_only:
        return 0

    stop_event = Event()
    _install_signal_handlers(stop_event)
    next_offset = _load_next_offset(config.offset_path)
    pending_confirmations: dict[str, PendingWorkerConfirmation] = {}
    pending_order_changes: dict[str, PendingOrderChange] = {}
    rules_conversations: dict[str, RulesConversation] = {}
    new_client_conversations: dict[str, NewClientConversation] = {}
    pending_client_creations: dict[str, PendingClientCreation] = {}
    search_conversations: dict[str, SearchConversation] = {}
    captcha_conversations: dict[str, CaptchaReviewConversation] = {}
    recent_orders: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=8))
    rate_limiter = TelegramRateLimiter()
    worker_monitor = WorkerHealthMonitor(enabled=config.worker_monitor_enabled)
    confirmation_lock = Lock()
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="telegram-worker-command")
    telegram.set_operator_commands()
    _record_audit_safe(actor="telegram-control", action="receiver", status="started")
    logger.info("Telegram control long polling started.")
    try:
        while not stop_event.is_set():
            try:
                worker_monitor.tick(
                    now=datetime.now(LIMA_TIMEZONE),
                    monotonic_now=time.monotonic(),
                    admin_api=admin_api,
                    telegram=telegram,
                    chat_ids=config.authorized_chat_ids,
                )
                updates = telegram.get_updates(
                    offset=next_offset,
                    timeout_seconds=config.poll_timeout_seconds,
                )
                _remove_expired_confirmations(pending_confirmations, confirmation_lock)
                _remove_expired_order_state(
                    pending_order_changes,
                    rules_conversations,
                    confirmation_lock,
                )
                for update in updates:
                    update_id = _update_id(update)
                    if update_id is None:
                        continue
                    _process_update(
                        update,
                        config,
                        telegram,
                        admin_api,
                        pending_confirmations=pending_confirmations,
                        pending_order_changes=pending_order_changes,
                        rules_conversations=rules_conversations,
                        new_client_conversations=new_client_conversations,
                        pending_client_creations=pending_client_creations,
                        search_conversations=search_conversations,
                        captcha_conversations=captcha_conversations,
                        recent_orders=recent_orders,
                        rate_limiter=rate_limiter,
                        confirmation_lock=confirmation_lock,
                        executor=executor,
                    )
                    next_offset = update_id + 1
                    _store_next_offset(config.offset_path, next_offset)
                _remove_expired_client_state(
                    new_client_conversations,
                    pending_client_creations,
                    telegram,
                    confirmation_lock,
                )
                _remove_expired_captcha_state(captcha_conversations, telegram)
            except TelegramControlError as exc:
                logger.warning("Telegram control polling failed: %s", exc)
                stop_event.wait(RETRY_DELAY_SECONDS)
            except Exception:
                logger.exception("Unexpected Telegram control polling failure")
                stop_event.wait(RETRY_DELAY_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    logger.info("Telegram control stopped.")
    return 0


def _process_update(
    update: dict[str, Any],
    config: TelegramControlConfig,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    *,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    pending_order_changes: dict[str, PendingOrderChange],
    rules_conversations: dict[str, RulesConversation],
    new_client_conversations: dict[str, NewClientConversation],
    pending_client_creations: dict[str, PendingClientCreation],
    search_conversations: dict[str, SearchConversation],
    captcha_conversations: dict[str, CaptchaReviewConversation],
    recent_orders: dict[str, deque[str]],
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        _process_callback_query(
            callback_query,
            config,
            telegram,
            admin_api,
            pending_confirmations,
            pending_order_changes,
            pending_client_creations,
            new_client_conversations,
            rules_conversations,
            search_conversations,
            captcha_conversations,
            recent_orders,
            rate_limiter,
            confirmation_lock,
            executor,
        )
        return
    message = update.get("message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = message.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram update from an unauthorized chat.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="message", status="denied"
        )
        return
    text = message.get("text")
    if not isinstance(text, str):
        return
    if not text.strip().startswith("/"):
        active_search = search_conversations.get(chat_id)
        guided_mutation = (
            chat_id in captcha_conversations
            or chat_id in new_client_conversations
            or chat_id in rules_conversations
            or (
                active_search is not None
                and active_search.mode in {"credentials", "payment"}
            )
        )
        if not rate_limiter.allow(chat_id, mutation=guided_mutation):
            _record_audit_safe(
                actor=_telegram_actor(chat_id),
                action="conversation_reply",
                status="rate_limited",
            )
            telegram.send_message(
                chat_id,
                "Estas respondiendo demasiado rapido. Espera un minuto para continuar.",
            )
            return
        search = search_conversations.get(chat_id)
        if chat_id in captcha_conversations and not _mutation_user_authorized(
            config, chat, sender
        ):
            telegram.send_message(
                chat_id,
                "El etiquetado solo se permite al operador autorizado en chat privado.",
            )
            return
        if _process_captcha_review_message(
            chat_id,
            text,
            telegram,
            admin_api,
            captcha_conversations,
        ):
            return
        if search is not None:
            if search.expires_at <= time.monotonic():
                search_conversations.pop(chat_id, None)
                telegram.send_message(
                    chat_id,
                    (
                        "La correccion de acceso vencio. Abre nuevamente el cliente."
                        if search.mode == "credentials"
                        else "El registro del abono vencio. Abre nuevamente el cobro."
                        if search.mode == "payment"
                        else "La busqueda vencio. Pulsa Buscar para intentar otra vez."
                    ),
                )
                return
            if search.mode == "credentials" and search.order_id:
                if not _mutation_user_authorized(config, chat, sender):
                    telegram.send_message(
                        chat_id,
                        "La contrasena solo se puede corregir por el operador autorizado "
                        "desde un chat privado.",
                    )
                    return
                if not 1 <= len(text) <= 200:
                    search.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
                    telegram.send_message(
                        chat_id,
                        "La contrasena debe tener entre 1 y 200 caracteres. Intenta otra vez.",
                    )
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                    return
                search_conversations.pop(chat_id, None)
                try:
                    _request_credentials_change(
                        chat_id,
                        search.order_id,
                        text,
                        telegram,
                        admin_api,
                        pending_order_changes,
                        confirmation_lock,
                        return_subject=search.return_subject,
                    )
                finally:
                    _delete_message_safe(telegram, chat_id, message.get("message_id"))
                return
            if search.mode == "payment" and search.order_id:
                search_conversations.pop(chat_id, None)
                _request_payment_change(
                    chat_id,
                    f"{search.order_id} {text}",
                    telegram,
                    admin_api,
                    pending_order_changes,
                    confirmation_lock,
                    return_subject=search.return_subject,
                )
                return
            search_conversations.pop(chat_id, None)
            _send_search_results(chat_id, text, telegram, admin_api)
            return
        new_client = new_client_conversations.get(chat_id)
        password_message = new_client is not None and new_client.step == 2
        if _process_new_client_message(
            chat_id,
            text,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        ):
            if password_message:
                message_id = message.get("message_id")
                if isinstance(message_id, int):
                    try:
                        telegram.delete_message(chat_id, message_id)
                    except TelegramControlError:
                        logger.warning("Could not delete Telegram password input message.")
            return
        if _process_rules_conversation_message(
            chat_id,
            text,
            telegram,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        ):
            return
    command, arguments = _command_parts(text)
    if command is None:
        telegram.send_message(
            chat_id,
            "No entendi ese mensaje. Usa /menu para elegir una opcion o /buscar TEXTO.",
            reply_markup=_main_menu_markup(),
        )
        return
    mutation = command in MUTATING_COMMANDS
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            actor=_telegram_actor(chat_id, user_id),
            action=command,
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.send_message(
            chat_id,
            "Por seguridad, esta accion solo se permite al operador autorizado "
            "desde un chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            actor=_telegram_actor(chat_id),
            action=command,
            status="rate_limited",
            target_id=(
                _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
            ),
        )
        telegram.send_message(
            chat_id,
            "Recibi demasiadas solicitudes seguidas. Espera un minuto y vuelve a intentar.",
        )
        return
    audit_target = _audit_target(arguments) if command in ORDER_TARGET_COMMANDS else None
    _record_audit_safe(
        actor=_telegram_actor(chat_id, user_id),
        action=command,
        status="accepted",
        target_type="service_order" if audit_target else None,
        target_id=audit_target,
    )
    if command in {"menu", "start"}:
        _send_main_menu(chat_id, telegram, admin_api)
        return
    if command in {"ayuda", "help"}:
        telegram.send_message(chat_id, HELP_TEXT, reply_markup=_main_menu_markup())
        return
    if command == "cancelar":
        removed = _cancel_chat_confirmations(chat_id, pending_confirmations, confirmation_lock)
        order_removed = _cancel_chat_order_state(
            chat_id,
            pending_order_changes,
            rules_conversations,
            confirmation_lock,
        )
        with confirmation_lock:
            client_removed = new_client_conversations.pop(chat_id, None) is not None
            client_removed = _cancel_pending_client_creation_unlocked(
                chat_id, pending_client_creations
            ) or client_removed
            search_removed = search_conversations.pop(chat_id, None) is not None
            captcha_removed = captcha_conversations.pop(chat_id, None) is not None
        response = (
            "Operacion pendiente cancelada."
            if removed
            or order_removed
            or client_removed
            or search_removed
            or captcha_removed
            else "No hay una operacion guiada activa."
        )
        telegram.send_message(chat_id, response)
        return
    if command == "estado":
        _send_worker_panel(chat_id, telegram, admin_api)
        return
    if command == "oportunidad":
        if arguments:
            telegram.send_message(chat_id, "Uso: /oportunidad")
            return
        _send_opportunity_panel(chat_id, telegram, admin_api)
        return
    if command == "clientes":
        _send_clients(chat_id, arguments, telegram, admin_api)
        return
    if command == "pendientes":
        _send_pending_attention(chat_id, arguments, telegram, admin_api)
        return
    if command == "cola":
        _send_queue(chat_id, arguments, telegram, admin_api)
        return
    if command == "cobros":
        _send_pending_payments(chat_id, arguments, telegram, admin_api)
        return
    if command == "buscar":
        _send_search_results(chat_id, arguments, telegram, admin_api)
        return
    if command == "resumen":
        _send_daily_summary(chat_id, telegram, admin_api)
        return
    if command == "captchas":
        try:
            captcha_enabled = bool(admin_api.get_health().get("captcha_shadow_enabled"))
        except TelegramControlError:
            captcha_enabled = False
        if not captcha_enabled:
            telegram.send_message(
                chat_id,
                "El etiquetado CAPTCHA no esta activo en este momento.",
                reply_markup=_main_menu_markup(),
            )
            return
        search_conversations.pop(chat_id, None)
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
        _start_captcha_review(chat_id, telegram, admin_api, captcha_conversations)
        return
    if command in {"cliente", "reglas"}:
        _send_order_query(chat_id, command, arguments, telegram, admin_api)
        return
    if command == "cliente_nuevo":
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
            arguments,
            telegram,
            new_client_conversations,
            pending_client_creations,
            confirmation_lock,
        )
        return
    if command == "prioridad":
        _request_priority_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "pago":
        _request_payment_change(
            chat_id,
            arguments,
            telegram,
            admin_api,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "reglas_editar":
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
            arguments,
            telegram,
            admin_api,
            rules_conversations,
            pending_order_changes,
            confirmation_lock,
        )
        return
    if command == "ultimos_errores":
        _send_recent_errors(chat_id, telegram, admin_api)
        return
    if command in {"pausar", "reanudar", "reiniciar"}:
        if arguments:
            telegram.send_message(chat_id, f"Uso: /{command}")
            return
        worker_command = {
            "pausar": "pause",
            "reanudar": "resume",
            "reiniciar": "restart",
        }[command]
        _request_worker_confirmation(
            chat_id,
            worker_command,
            telegram,
            pending_confirmations,
            confirmation_lock,
        )
        return
    telegram.send_message(chat_id, "Comando no reconocido. Usa /ayuda.")


def _process_callback_query(
    callback_query: dict[str, Any],
    config: TelegramControlConfig,
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
    rate_limiter: TelegramRateLimiter,
    confirmation_lock: Lock,
    executor: ThreadPoolExecutor,
) -> None:
    callback_id = callback_query.get("id")
    data = callback_query.get("data")
    message = callback_query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    if not isinstance(callback_id, str) or not isinstance(data, str):
        return
    if not isinstance(chat, dict) or chat.get("id") is None:
        return
    chat_id = str(chat["id"])
    sender = callback_query.get("from")
    user_id = str(sender.get("id") or "") if isinstance(sender, dict) else ""
    if chat_id not in config.authorized_chat_ids:
        logger.warning("Ignored Telegram callback from an unauthorized chat.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="denied"
        )
        return
    mutation = _callback_is_mutation(data)
    if mutation and not _mutation_user_authorized(config, chat, sender):
        _record_audit_safe(
            actor=_telegram_actor(chat_id, user_id),
            action="callback",
            status="denied",
            detail="Mutation requires an authorized user in a private chat.",
        )
        telegram.answer_callback_query(
            callback_id,
            "Accion permitida solo al operador autorizado en chat privado.",
        )
        return
    if not rate_limiter.allow(chat_id, mutation=mutation):
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="callback", status="rate_limited"
        )
        telegram.answer_callback_query(callback_id, "Espera un minuto y vuelve a intentar.")
        return
    if _process_captcha_review_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        captcha_conversations,
    ):
        return
    if _process_interface_callback(
        callback_id,
        data,
        message,
        chat_id,
        telegram,
        admin_api,
        pending_confirmations,
        pending_order_changes,
        pending_client_creations,
        new_client_conversations,
        rules_conversations,
        search_conversations,
        captcha_conversations,
        recent_orders,
        confirmation_lock,
    ):
        return
    parts = data.split(":")
    if len(parts) != 3 or parts[0] not in {"wc", "oc", "nc"} or parts[2] not in {"yes", "no"}:
        telegram.answer_callback_query(callback_id, "Accion no reconocida.")
        return
    operation_id = parts[1]
    if parts[0] == "nc":
        with confirmation_lock:
            creation = pending_client_creations.pop(operation_id, None)
        if (
            creation is None
            or creation.chat_id != chat_id
            or creation.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                actor=_telegram_actor(chat_id), action="client_create",
                status="cancelled", operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Registro cancelado. No se guardo nada.")
            return
        telegram.answer_callback_query(callback_id, "Registro confirmado.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action="client_create",
            status="accepted", operation_id=operation_id,
        )
        executor.submit(_execute_client_creation, creation, telegram, admin_api)
        return
    if parts[0] == "oc":
        with confirmation_lock:
            change = pending_order_changes.pop(operation_id, None)
        if (
            change is None
            or change.chat_id != chat_id
            or change.expires_at <= time.monotonic()
        ):
            telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
            return
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if parts[2] == "no":
            _record_audit_safe(
                actor=_telegram_actor(chat_id), action=change.action,
                status="cancelled", target_type="service_order",
                target_id=change.order_id, operation_id=operation_id,
            )
            telegram.answer_callback_query(callback_id, "Operacion cancelada.")
            telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
            return
        telegram.answer_callback_query(callback_id, "Cambio confirmado.")
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action=change.action,
            status="accepted", target_type="service_order",
            target_id=change.order_id, operation_id=operation_id,
        )
        executor.submit(_execute_order_change, change, telegram, admin_api)
        return
    with confirmation_lock:
        confirmation = pending_confirmations.pop(operation_id, None)
    if (
        confirmation is None
        or confirmation.chat_id != chat_id
        or confirmation.expires_at <= time.monotonic()
    ):
        telegram.answer_callback_query(callback_id, "La confirmacion ya vencio.")
        return
    _clear_captcha_review_buttons(chat_id, message, telegram)
    if parts[2] == "no":
        _record_audit_safe(
            actor=_telegram_actor(chat_id), action=confirmation.command,
            status="cancelled", operation_id=operation_id,
        )
        telegram.answer_callback_query(callback_id, "Operacion cancelada.")
        telegram.send_message(chat_id, "Operacion cancelada. No se realizaron cambios.")
        return
    telegram.answer_callback_query(callback_id, "Solicitud confirmada.")
    is_opportunity_control = confirmation.command.startswith("opportunity:")
    _record_audit_safe(
        actor=_telegram_actor(chat_id), action=confirmation.command,
        status="accepted",
        target_type="opportunity_control" if is_opportunity_control else None,
        target_id=confirmation.opportunity_target,
        operation_id=operation_id,
    )
    if is_opportunity_control:
        executor.submit(
            _execute_opportunity_control,
            confirmation,
            telegram,
            admin_api,
        )
        return
    if confirmation.command.startswith("revalidate:"):
        executor.submit(
            _execute_order_revalidation,
            confirmation,
            telegram,
            admin_api,
        )
        return
    executor.submit(
        _execute_worker_command,
        confirmation,
        telegram,
        admin_api,
    )


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_value = getattr(signal, signal_name, None)
        if signal_value is not None:
            signal.signal(signal_value, request_stop)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram remote-control receiver.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate Telegram and Admin API connectivity without consuming updates.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        raise SystemExit(run_control(check_only=args.check))
    except TelegramControlError as exc:
        logger.error("Telegram control could not start: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
