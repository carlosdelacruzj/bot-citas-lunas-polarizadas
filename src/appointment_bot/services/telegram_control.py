from __future__ import annotations

import argparse
import logging
import secrets
import signal
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from threading import Event, Lock, Timer
from typing import Any
from urllib.error import HTTPError, URLError

from appointment_bot.config import load_settings
from appointment_bot.services import telegram_program_resolution
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
from appointment_bot.services.telegram.worker_panels import (
    _send_opportunity_panel as _send_opportunity_panel,
)
from appointment_bot.services.telegram.worker_panels import _send_worker_panel as _send_worker_panel

logger = logging.getLogger("appointment_bot.services.telegram_control")


@dataclass
class WorkerHealthMonitor:
    enabled: bool
    next_check_at: float = 0.0
    consecutive_failures: int = 0
    alert_sent: bool = False
    last_failure_kind: str | None = None

    def tick(
        self,
        *,
        now: datetime,
        monotonic_now: float,
        admin_api: AdminApiClient,
        telegram: TelegramBotApi,
        chat_ids: frozenset[str],
    ) -> None:
        if not self.enabled:
            return
        minute = now.hour * 60 + now.minute
        if not WORKER_MONITOR_START_MINUTE <= minute < WORKER_MONITOR_END_MINUTE:
            self._reset()
            self.next_check_at = monotonic_now + WORKER_MONITOR_INTERVAL_SECONDS
            return
        if monotonic_now < self.next_check_at:
            return
        self.next_check_at = monotonic_now + WORKER_MONITOR_INTERVAL_SECONDS

        failure_kind = self._failure_kind(admin_api)
        if failure_kind is None:
            if self.consecutive_failures:
                logger.info(
                    "Telegram worker monitor recovered after %s failed checks.",
                    self.consecutive_failures,
                )
            self._reset()
            return

        self.consecutive_failures += 1
        self.last_failure_kind = failure_kind
        logger.warning(
            "Telegram worker monitor check failed (%s/%s): %s",
            self.consecutive_failures,
            WORKER_MONITOR_FAILURE_THRESHOLD,
            failure_kind,
        )
        if self.consecutive_failures < WORKER_MONITOR_FAILURE_THRESHOLD or self.alert_sent:
            return

        message = (
            "ALERTA OPERATIVA\n\n"
            "El worker lleva tres revisiones consecutivas sin estado saludable.\n"
            f"Causa: {failure_kind}.\n\n"
            "Accion: revisa Estado del sistema.\n"
            "No se ejecuto ningun reinicio automatico."
        )
        markup = {
            "inline_keyboard": [
                [{"text": "Estado del sistema", "callback_data": "ui:status:show"}]
            ]
        }
        try:
            for chat_id in sorted(chat_ids):
                telegram.send_message(chat_id, message, reply_markup=markup)
        except TelegramControlError as exc:
            logger.warning("Telegram worker monitor could not send alert: %s", exc)
            return
        self.alert_sent = True

    def _failure_kind(self, admin_api: AdminApiClient) -> str | None:
        try:
            payload = admin_api.get_worker()
        except TelegramControlError:
            try:
                admin_api.get_health()
            except TelegramControlError:
                return "Admin API inaccesible"
            return "consulta administrativa rechazada"
        if payload.get("worker_running") is not True:
            return "worker sin lease activo"
        logger.info("Telegram worker monitor check healthy.")
        return None

    def _reset(self) -> None:
        self.consecutive_failures = 0
        self.alert_sent = False
        self.last_failure_kind = None


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


def _start_rules_conversation(
    chat_id: str,
    arguments: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> None:
    order_id = arguments.strip()
    if not _valid_order_id(order_id):
        telegram.send_message(chat_id, "Uso: /reglas_editar ORDER_ID")
        return
    try:
        order = next(
            (item for item in admin_api.get_service_orders() if item.get("order_id") == order_id),
            None,
        )
    except TelegramControlError as exc:
        logger.warning("Could not start rules conversation: %s", exc)
        telegram.send_message(chat_id, "No pude consultar esa orden.")
        return
    if order is None:
        telegram.send_message(chat_id, "No pude encontrar esa orden.")
        return
    original = _rules_payload(order)
    conversation = RulesConversation(
        chat_id=chat_id,
        order_id=order_id,
        original=original,
        updated=dict(original),
        step=0,
        expires_at=time.monotonic() + CONVERSATION_TTL_SECONDS,
    )
    with confirmation_lock:
        _cancel_chat_order_state_unlocked(
            chat_id,
            pending_order_changes,
            rules_conversations,
        )
        rules_conversations[chat_id] = conversation
    telegram.send_message(
        chat_id,
        f"EDITAR REGLAS\n\n{format_order_rules(order)}\n\n{_rules_step_prompt(0)}",
        reply_markup=_rules_prompt_markup(0),
    )


def _process_rules_conversation_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    with confirmation_lock:
        conversation = rules_conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(chat_id, "La edicion de reglas vencio. Inicia nuevamente.")
        return True
    return _continue_rules_conversation(
        conversation,
        text,
        telegram,
        rules_conversations,
        pending_order_changes,
        confirmation_lock,
    )


def _continue_rules_conversation(
    conversation: RulesConversation,
    text: str,
    telegram: TelegramBotApi,
    rules_conversations: dict[str, RulesConversation],
    pending_order_changes: dict[str, PendingOrderChange],
    confirmation_lock: Lock,
) -> bool:
    chat_id = conversation.chat_id
    try:
        field, value = _parse_rules_step(conversation.step, text, conversation.updated)
    except ValueError as exc:
        telegram.send_message(
            chat_id,
            f"{exc}\n\n{_rules_step_prompt(conversation.step)}",
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    conversation.updated[field] = value
    conversation.step += 1
    conversation.expires_at = time.monotonic() + CONVERSATION_TTL_SECONDS
    if conversation.step < 4:
        telegram.send_message(
            chat_id,
            _rules_step_prompt(conversation.step),
            reply_markup=_rules_prompt_markup(conversation.step),
        )
        return True
    try:
        _validate_rules_payload(conversation.updated)
    except ValueError as exc:
        with confirmation_lock:
            rules_conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            f"No se guardo ningun cambio: {exc}\nInicia nuevamente con /reglas_editar.",
        )
        return True
    with confirmation_lock:
        rules_conversations.pop(chat_id, None)
    if conversation.updated == conversation.original:
        telegram.send_message(chat_id, "No hay cambios en las reglas.")
        return True
    change = PendingOrderChange(
        operation_id=secrets.token_hex(6),
        chat_id=chat_id,
        action="rules",
        order_id=conversation.order_id,
        original=conversation.original,
        updated=conversation.updated,
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    _store_order_change(change, pending_order_changes, confirmation_lock)
    _send_order_change_confirmation(change, telegram)
    return True


def _rules_step_prompt(step: int) -> str:
    return (
        "Paso 1/4 - Fecha minima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 2/4 - Fecha maxima. Responde DD-MM-YYYY, mantener o sin limite.",
        "Paso 3/4 - Dias permitidos. Usa los botones o responde 1,2,...7.",
        "Paso 4/4 - Fechas excluidas. Usa DD-MM-YYYY al DD-MM-YYYY; "
        "separa varios rangos con ; o elige Sin exclusiones.",
    )[step]


def _rules_prompt_markup(step: int) -> dict[str, Any]:
    if step in {0, 1}:
        rows = [[
            {"text": "Mantener", "callback_data": "rf:value:keep"},
            {"text": "Quitar limite", "callback_data": "rf:value:clear"},
        ]]
    elif step == 2:
        rows = [
            [
                {"text": "Lun-Vie", "callback_data": "rf:days:mon_fri"},
                {"text": "Lun-Sab", "callback_data": "rf:days:mon_sat"},
            ],
            [{"text": "Solo sabado", "callback_data": "rf:days:sat"}],
            [
                {"text": "Todos", "callback_data": "rf:value:clear"},
                {"text": "Mantener", "callback_data": "rf:value:keep"},
            ],
        ]
    else:
        rows = [[
            {"text": "Sin exclusiones", "callback_data": "rf:value:clear"},
            {"text": "Mantener", "callback_data": "rf:value:keep"},
        ]]
    if step > 0:
        rows.append([{"text": "Atras", "callback_data": "rf:nav:back"}])
    rows.append([{"text": "Cancelar", "callback_data": "ui:cancel:guided"}])
    return {"inline_keyboard": rows}


def _request_worker_confirmation(
    chat_id: str,
    command: str,
    telegram: TelegramBotApi,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    operation_id = secrets.token_hex(6)
    confirmation = PendingWorkerConfirmation(
        operation_id=operation_id,
        chat_id=chat_id,
        command=command,
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
    )
    with confirmation_lock:
        _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
        pending_confirmations[operation_id] = confirmation
    label = _worker_command_label(command)
    telegram.send_message(
        chat_id,
        f"Confirmar: {label}.\n\nLa confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [
                [
                    {
                        "text": "Confirmar",
                        "callback_data": f"wc:{operation_id}:yes",
                    },
                    {
                        "text": "Cancelar",
                        "callback_data": f"wc:{operation_id}:no",
                    },
                ]
            ]
        },
    )


def _request_opportunity_confirmation(
    chat_id: str,
    action: str,
    target: str,
    expected_revision: int,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    pending_confirmations: dict[str, PendingWorkerConfirmation],
    confirmation_lock: Lock,
) -> None:
    try:
        current = admin_api.get_opportunity_control()
    except TelegramControlError as exc:
        logger.warning("Could not review opportunity control before confirmation: %s", exc)
        telegram.send_message(chat_id, "No pude revisar el estado actual. Actualiza el panel.")
        return
    if current.get("revision") != expected_revision:
        telegram.send_message(
            chat_id,
            "El control cambio desde que abriste el panel. Revisa el estado actualizado.",
        )
        _send_opportunity_panel(chat_id, telegram, admin_api)
        return

    reason = {
        "activate": "Activacion confirmada por el operador desde Telegram.",
        "deactivate": "Desactivacion confirmada por el operador desde Telegram.",
        "drain": "Drenaje controlado confirmado por el operador desde Telegram.",
        "reset_breaker": "Reset manual del breaker confirmado tras revision en Telegram.",
    }[action]
    operation_id = secrets.token_hex(6)
    confirmation = PendingWorkerConfirmation(
        operation_id=operation_id,
        chat_id=chat_id,
        command=f"opportunity:{action}",
        expires_at=time.monotonic() + CONFIRMATION_TTL_SECONDS,
        opportunity_target=target,
        expected_revision=expected_revision,
        reason=reason,
    )
    with confirmation_lock:
        _cancel_chat_confirmations_unlocked(chat_id, pending_confirmations)
        pending_confirmations[operation_id] = confirmation
    label = {
        "activate": "activar",
        "deactivate": "desactivar",
        "drain": "drenar sin abrir nuevas sesiones",
        "reset_breaker": "resetear el breaker revisado",
    }[action]
    consequence = (
        " Al resetear, volvera a regir el modo deseado actual y las admisiones "
        "podran reanudarse."
        if action == "reset_breaker"
        else ""
    )
    telegram.send_message(
        chat_id,
        f"Confirmar: {label} {target}.\n\n"
        f"Revision revisada: {expected_revision}.{consequence} "
        "La confirmacion vence en 2 minutos.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "Confirmar", "callback_data": f"wc:{operation_id}:yes"},
                {"text": "Cancelar", "callback_data": f"wc:{operation_id}:no"},
            ]]
        },
    )


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


def _execute_opportunity_control(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    actor = _telegram_actor(confirmation.chat_id)
    action = confirmation.command.removeprefix("opportunity:")
    target = confirmation.opportunity_target
    revision = confirmation.expected_revision
    if target not in {"obs006", "obs007"} or revision is None or confirmation.reason is None:
        logger.error(
            "Incomplete opportunity confirmation operation_id=%s",
            confirmation.operation_id,
        )
        return
    try:
        current = admin_api.get_opportunity_control()
        if current.get("revision") != revision:
            telegram.send_message(
                confirmation.chat_id,
                "El control cambio antes de aplicar la solicitud. No se modifico nada.",
            )
            _record_audit_safe(
                actor=actor,
                action=confirmation.command,
                status="failed",
                target_type="opportunity_control",
                target_id=target,
                operation_id=confirmation.operation_id,
                detail="stale_revision",
            )
            _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)
            return
        result = admin_api.update_opportunity_control(
            action=action,
            target=target,
            reason=confirmation.reason,
            expected_revision=revision,
            actor=actor,
        )
        telegram.send_message(
            confirmation.chat_id,
            str(result.get("message") or "Control de oportunidad actualizado."),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="applied",
            target_type="opportunity_control",
            target_id=target,
            operation_id=confirmation.operation_id,
            detail=f"revision={result.get('revision', 'unknown')}",
        )
        _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)
    except TelegramControlError as exc:
        stale = "HTTP 409" in str(exc)
        logger.warning("Opportunity control %s failed: %s", action, exc)
        telegram.send_message(
            confirmation.chat_id,
            (
                "El estado cambio o la operacion ya no es segura. Revisa el panel actualizado."
                if stale
                else "No pude aplicar el control de oportunidad. No confirmo cambios."
            ),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="failed",
            target_type="opportunity_control",
            target_id=target,
            operation_id=confirmation.operation_id,
            detail="stale_or_unsafe" if stale else "admin_api_error",
        )
        if stale:
            _send_opportunity_panel(confirmation.chat_id, telegram, admin_api)


def _execute_worker_command(
    confirmation: PendingWorkerConfirmation,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    operation_short = confirmation.operation_id[:8]
    actor = _telegram_actor(confirmation.chat_id)
    try:
        queued = admin_api.enqueue_worker_command(confirmation.command, actor=actor)
        command_id = queued.get("command_id")
        if not isinstance(command_id, str) or not command_id:
            raise TelegramControlError("Admin API did not return a command_id.")
        telegram.send_message(
            confirmation.chat_id,
            f"Solicitud {operation_short} encolada. Verificando resultado real...",
        )
        command = _wait_for_worker_command(admin_api, command_id)
        status = command.get("status")
        if status != "applied":
            detail = "fallo" if status == "failed" else "no termino a tiempo"
            telegram.send_message(
                confirmation.chat_id,
                f"La solicitud {operation_short} {detail}. No confirmo el cambio.",
            )
            _record_audit_safe(
                actor=actor,
                action=confirmation.command,
                status="failed",
                operation_id=confirmation.operation_id,
                detail=f"worker_command_status={status or 'unknown'}",
            )
            return
        worker = _wait_for_worker_effect(admin_api, confirmation.command)
        telegram.send_message(
            confirmation.chat_id,
            _format_worker_command_success(confirmation.command, operation_short, worker),
        )
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="applied",
            operation_id=confirmation.operation_id,
            detail=f"worker_phase={worker.get('phase') or 'unknown'}",
        )
    except TelegramControlError as exc:
        logger.warning("Worker command %s failed: %s", confirmation.command, exc)
        try:
            telegram.send_message(
                confirmation.chat_id,
                f"No pude completar la solicitud {operation_short}. El cambio no fue confirmado.",
            )
        except TelegramControlError:
            logger.warning("Could not deliver the worker command failure message.")
        _record_audit_safe(
            actor=actor,
            action=confirmation.command,
            status="failed",
            operation_id=confirmation.operation_id,
            detail="Worker command could not be completed.",
        )
    except Exception:
        logger.exception("Unexpected worker command execution failure")


def _wait_for_worker_command(
    admin_api: AdminApiClient,
    command_id: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_command: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        last_command = admin_api.get_worker_command(command_id)
        if last_command is not None and last_command.get("status") in {"applied", "failed"}:
            return last_command
        time.sleep(1)
    return last_command or {"status": "timeout"}


def _wait_for_worker_effect(admin_api: AdminApiClient, command: str) -> dict[str, Any]:
    deadline = time.monotonic() + WORKER_COMMAND_TIMEOUT_SECONDS
    last_worker: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            last_worker = admin_api.get_worker()
        except TelegramControlError:
            time.sleep(1)
            continue
        paused = bool(last_worker.get("paused"))
        running = bool(last_worker.get("worker_running"))
        phase = str(last_worker.get("phase") or "")
        if command == "pause" and paused:
            return last_worker
        if command == "resume" and running and not paused:
            return last_worker
        if command == "restart" and running and phase != "restarting":
            return last_worker
        time.sleep(1)
    raise TelegramControlError("Worker state did not reach the expected result.")


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
