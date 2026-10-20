from __future__ import annotations

import logging

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.presentation import (
    _format_opportunity_control,
    format_worker_status,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _send_worker_panel(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        worker = admin_api.get_worker()
    except TelegramControlError as exc:
        logger.warning("Could not prepare worker panel: %s", exc)
        telegram.send_message(chat_id, "No pude consultar el worker.")
        return
    paused = bool(worker.get("paused"))
    action_row = (
        [{"text": "Reanudar", "callback_data": "wk:resume:ask"}]
        if paused
        else [{"text": "Pausar", "callback_data": "wk:pause:ask"}]
    )
    action_row.append({"text": "Reiniciar", "callback_data": "wk:restart:ask"})
    telegram.send_message(
        chat_id,
        format_worker_status(worker),
        reply_markup={
            "inline_keyboard": [
                action_row,
                [{"text": "Ver errores recientes", "callback_data": "ui:errors:show"}],
                [
                    {"text": "Actualizar", "callback_data": "ui:worker:show"},
                    {"text": "Menu", "callback_data": "ui:menu:main"},
                ],
            ]
        },
    )


def _send_opportunity_panel(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
) -> None:
    try:
        control = admin_api.get_opportunity_control()
    except TelegramControlError as exc:
        logger.warning("Could not prepare opportunity panel: %s", exc)
        telegram.send_message(chat_id, "No pude consultar los controles de oportunidad.")
        return
    revision = control.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int):
        telegram.send_message(chat_id, "El Admin API devolvio una revision de control invalida.")
        return

    rows: list[list[dict[str, str]]] = []
    pending_application = bool(control.get("pending_application"))
    active_burst = control.get("active_burst")
    if not pending_application:
        for target, label in (("obs006", "Rafaga"), ("obs007", "Optimizada")):
            target_control = control.get(target)
            if not isinstance(target_control, dict):
                continue
            effective = str(target_control.get("effective_mode") or "disabled")
            if target == "obs006" and isinstance(active_burst, dict):
                action = "drain"
                action_label = "Drenar"
            elif effective == "enabled":
                action = "deactivate"
                action_label = "Desactivar"
            else:
                action = "activate"
                action_label = "Activar"
            rows.append(
                [
                    {
                        "text": f"{action_label} {label}",
                        "callback_data": f"op:{target}:{action}-r{revision}",
                    }
                ]
            )

    breaker = control.get("breaker")
    if isinstance(breaker, dict) and str(breaker.get("state") or "closed") != "closed":
        rows.append([{
            "text": "Revisar y resetear breaker",
            "callback_data": f"op:obs006:reset_breaker-r{revision}",
        }])
    rows.append([
        {"text": "Actualizar", "callback_data": "ui:opportunity:show"},
        {"text": "Menu", "callback_data": "ui:menu:main"},
    ])
    telegram.send_message(
        chat_id,
        _format_opportunity_control(control),
        reply_markup={"inline_keyboard": rows},
    )
