from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe, _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.constants import (
    CONFIRMATION_TTL_SECONDS,
    WORKER_COMMAND_TIMEOUT_SECONDS,
    WORKER_MONITOR_END_MINUTE,
    WORKER_MONITOR_FAILURE_THRESHOLD,
    WORKER_MONITOR_INTERVAL_SECONDS,
    WORKER_MONITOR_START_MINUTE,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import PendingWorkerConfirmation
from appointment_bot.services.telegram.presentation import (
    _format_worker_command_success,
    _worker_command_label,
)
from appointment_bot.services.telegram.state import _cancel_chat_confirmations_unlocked
from appointment_bot.services.telegram.worker_panels import _send_opportunity_panel

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
