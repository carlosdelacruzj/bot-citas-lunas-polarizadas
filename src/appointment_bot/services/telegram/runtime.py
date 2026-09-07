from __future__ import annotations

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
from appointment_bot.services.telegram.access import TelegramRateLimiter
from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.config import load_control_config
from appointment_bot.services.telegram.constants import LIMA_TIMEZONE, RETRY_DELAY_SECONDS
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
from appointment_bot.services.telegram.router import _process_update
from appointment_bot.services.telegram.state import (
    _load_next_offset,
    _remove_expired_captcha_state,
    _remove_expired_client_state,
    _remove_expired_confirmations,
    _remove_expired_order_state,
    _store_next_offset,
    _update_id,
)
from appointment_bot.services.telegram.worker_controls import WorkerHealthMonitor

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


def _install_signal_handlers(stop_event: Event) -> None:
    def request_stop(_signum: int, _frame: Any) -> None:
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_value = getattr(signal, signal_name, None)
        if signal_value is not None:
            signal.signal(signal_value, request_stop)
