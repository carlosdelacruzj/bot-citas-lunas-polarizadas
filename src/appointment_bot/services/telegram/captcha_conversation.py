from __future__ import annotations

import logging
import mimetypes
import re
import secrets
import time
from typing import Any

from appointment_bot.services.telegram.admin_api_client import AdminApiClient
from appointment_bot.services.telegram.audit import _record_audit_safe, _telegram_actor
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.constants import CAPTCHA_REVIEW_TTL_SECONDS
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import CaptchaReviewConversation
from appointment_bot.services.telegram.presentation import _main_menu_markup
from appointment_bot.services.telegram.transport import (
    MAX_TELEGRAM_RESPONSE_BYTES,
)

logger = logging.getLogger("appointment_bot.services.telegram_control")


def _start_captcha_review(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> None:
    conversations[chat_id] = CaptchaReviewConversation(
        chat_id=chat_id,
        session_id=secrets.token_hex(4),
        expires_at=time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS,
    )
    _send_next_captcha_review(chat_id, telegram, admin_api, conversations)


def _send_next_captcha_review(
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> None:
    conversation = conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio por inactividad. Abrela nuevamente desde el menu.",
            reply_markup=_main_menu_markup(),
        )
        return
    try:
        event, pending = _next_pending_captcha(admin_api, conversation.skipped_event_ids)
        summary = admin_api.get_captcha_summary()
    except TelegramControlError as exc:
        logger.warning("Could not load Telegram CAPTCHA review queue: %s", exc)
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "No pude abrir la cola de CAPTCHA. Verifica el servicio sombra e intenta otra vez.",
            reply_markup=_main_menu_markup(),
        )
        return
    if event is None:
        conversations.pop(chat_id, None)
        if pending == 0:
            message = (
                "REVISION PRIORITARIA COMPLETA\n\n"
                "No quedan CAPTCHA del canario V6, anomalias, desacuerdos ni "
                "muestras de control pendientes. El resto permanece guardado en Historial."
            )
        else:
            message = (
                "No quedan CAPTCHA sin revisar en esta sesion.\n\n"
                f"Omitiste {len(conversation.skipped_event_ids)}. "
                "Vuelve a entrar para verlos otra vez."
            )
        telegram.send_message(chat_id, message, reply_markup=_main_menu_markup())
        return
    event_id = str(event.get("event_id") or "")
    image_sha256 = str(event.get("image_sha256") or "")
    if not event_id or len(image_sha256) != 64:
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La cola devolvio un CAPTCHA incompleto. Intenta nuevamente mas tarde.",
            reply_markup=_main_menu_markup(),
        )
        return
    choices = _captcha_prediction_choices(event)
    try:
        image, content_type = admin_api.get_captcha_image(event_id)
    except TelegramControlError as exc:
        logger.warning("Could not load Telegram CAPTCHA image event_id=%s error=%s", event_id, exc)
        conversation.skipped_event_ids.add(event_id)
        telegram.send_message(chat_id, "No pude abrir esa imagen; pase al siguiente CAPTCHA.")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return
    if len(image) > MAX_TELEGRAM_RESPONSE_BYTES:
        conversation.skipped_event_ids.add(event_id)
        telegram.send_message(
            chat_id,
            "La imagen excede el limite permitido; pase al siguiente CAPTCHA.",
        )
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return
    conversation.item_token = secrets.token_hex(3)
    conversation.current_event_id = event_id
    conversation.current_image_sha256 = image_sha256
    conversation.choice_answers = tuple(answer for answer, _models in choices)
    conversation.awaiting_manual_answer = False
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    stats = summary.get("stats") if isinstance(summary.get("stats"), dict) else {}
    total = max(0, int(stats.get("events") or 0))
    labeled = max(0, int(stats.get("human_labeled") or 0))
    caption = (
        "ETIQUETAR CAPTCHA PRIORITARIO\n\n"
        f"Motivo: {_captcha_review_reason(event)}\n"
        f"Validados: {labeled}/{total} | Prioritarios: {pending}\n"
        "Elige una respuesta de los modelos o escribe la tuya.\n"
        "La sesion vence despues de 10 minutos sin actividad."
    )
    telegram.send_photo(
        chat_id,
        image,
        f"captcha-{event_id[:12]}.png",
        caption,
        content_type=content_type or mimetypes.types_map.get(".png", "image/png"),
        reply_markup=_captcha_review_markup(conversation, choices),
    )


def _captcha_review_reason(event: dict[str, Any]) -> str:
    return {
        "canary_v6": "decision del canario V6",
        "anomaly": "anomalia o baja confianza",
        "model_disagreement": "desacuerdo V3/V6",
        "control_sample": "muestra aleatoria de control",
    }.get(str(event.get("review_priority_reason") or ""), "revision dirigida")


def _next_pending_captcha(
    admin_api: AdminApiClient,
    skipped_event_ids: set[str],
) -> tuple[dict[str, Any] | None, int]:
    page = 1
    pending = 0
    while True:
        payload = admin_api.get_pending_captcha_events(page=page)
        events = payload.get("events")
        pagination = payload.get("pagination")
        if not isinstance(events, list) or not isinstance(pagination, dict):
            raise TelegramControlError("Admin API returned an invalid CAPTCHA queue.")
        pending = max(0, int(pagination.get("total") or 0))
        for event in events:
            if not isinstance(event, dict):
                continue
            event_id = str(event.get("event_id") or "")
            if event_id and event_id not in skipped_event_ids:
                return event, pending
        if page >= max(1, int(pagination.get("total_pages") or 1)):
            return None, pending
        page += 1


def _captcha_prediction_choices(
    event: dict[str, Any],
) -> list[tuple[str, tuple[str, ...]]]:
    predictions = event.get("predictions")
    if not isinstance(predictions, list):
        return []
    selected_model = str(event.get("selected_model_name") or "")
    ordered = sorted(
        (item for item in predictions if isinstance(item, dict)),
        key=lambda item: str(item.get("model_name") or "") != selected_model,
    )
    grouped: dict[str, list[str]] = {}
    for prediction in ordered:
        answer = str(prediction.get("prediction") or "").strip().upper()
        if re.fullmatch(r"[A-Z0-9]{5}", answer) is None:
            continue
        model = _captcha_model_short_label(str(prediction.get("model_name") or "modelo"))
        models = grouped.setdefault(answer, [])
        if model not in models:
            models.append(model)
    return [(answer, tuple(models)) for answer, models in grouped.items()]


def _captcha_model_short_label(model_name: str) -> str:
    return {
        "v1_real": "v1",
        "v2_scratch": "v2 scratch",
        "v2_selected": "v2",
        "v3_selected": "v3",
        "v4_candidate": "v4",
        "v5_candidate": "v5",
        "v6_sequence_candidate": "v6",
    }.get(model_name, model_name[:16])


def _captcha_review_markup(
    conversation: CaptchaReviewConversation,
    choices: list[tuple[str, tuple[str, ...]]],
) -> dict[str, Any]:
    prefix = f"cp:{conversation.session_id}:{conversation.item_token}:"
    rows = [
        [{
            "text": f"{answer} - {' + '.join(models)}"[:60],
            "callback_data": f"{prefix}a{index}",
        }]
        for index, (answer, models) in enumerate(choices)
    ]
    rows.extend(
        [
            [{"text": "Escribir otra respuesta", "callback_data": f"{prefix}manual"}],
            [
                {"text": "Omitir", "callback_data": f"{prefix}skip"},
                {"text": "Salir", "callback_data": f"{prefix}exit"},
            ],
        ]
    )
    return {"inline_keyboard": rows}


def _process_captcha_review_message(
    chat_id: str,
    text: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    conversation = conversations.get(chat_id)
    if conversation is None:
        return False
    if conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "La sesion de CAPTCHA vencio por inactividad. La respuesta no fue guardada.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if not conversation.awaiting_manual_answer:
        telegram.send_message(
            chat_id,
            "Usa uno de los botones del CAPTCHA o pulsa Escribir otra respuesta.",
        )
        return True
    answer = text.strip().upper()
    if re.fullmatch(r"[A-Z0-9]{5}", answer) is None:
        conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
        telegram.send_message(
            chat_id,
            "Respuesta invalida. Envia exactamente 5 letras o numeros, sin espacios.",
        )
        return True
    if _save_captcha_review_answer(chat_id, answer, telegram, admin_api, conversations):
        telegram.send_message(chat_id, f"Guardado: {answer}. Abriendo el siguiente CAPTCHA...")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
    return True


def _process_captcha_review_callback(
    callback_id: str,
    data: str,
    message: Any,
    chat_id: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "cp":
        return False
    _prefix, session_id, item_token, action = parts
    conversation = conversations.get(chat_id)
    if conversation is None or conversation.expires_at <= time.monotonic():
        conversations.pop(chat_id, None)
        telegram.answer_callback_query(callback_id, "La sesion ya vencio.")
        return True
    if conversation.session_id != session_id or conversation.item_token != item_token:
        telegram.answer_callback_query(
            callback_id,
            "Ese boton ya no corresponde al CAPTCHA actual.",
        )
        return True
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    if action == "manual":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        conversation.awaiting_manual_answer = True
        telegram.answer_callback_query(callback_id, "Escribe los 5 caracteres.")
        telegram.send_message(
            chat_id,
            "Escribe la respuesta correcta con exactamente 5 letras o numeros. "
            "Usa /cancelar para salir.",
        )
        return True
    if action == "skip":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        if conversation.current_event_id:
            conversation.skipped_event_ids.add(conversation.current_event_id)
        telegram.answer_callback_query(callback_id, "CAPTCHA omitido en esta sesion.")
        _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
        return True
    if action == "exit":
        _clear_captcha_review_buttons(chat_id, message, telegram)
        conversations.pop(chat_id, None)
        telegram.answer_callback_query(callback_id, "Etiquetado pausado.")
        telegram.send_message(
            chat_id,
            "Etiquetado pausado. Las respuestas guardadas se conservaron.",
            reply_markup=_main_menu_markup(),
        )
        return True
    if not action.startswith("a") or not action[1:].isdigit():
        telegram.answer_callback_query(callback_id, "Accion de CAPTCHA no reconocida.")
        return True
    choice_index = int(action[1:])
    if choice_index >= len(conversation.choice_answers):
        telegram.answer_callback_query(callback_id, "La respuesta elegida ya no esta disponible.")
        return True
    answer = conversation.choice_answers[choice_index]
    if not _save_captcha_review_answer(chat_id, answer, telegram, admin_api, conversations):
        telegram.answer_callback_query(callback_id, "No se pudo guardar.")
        return True
    _clear_captcha_review_buttons(chat_id, message, telegram)
    telegram.answer_callback_query(callback_id, f"Guardado: {answer}")
    _send_next_captcha_review(chat_id, telegram, admin_api, conversations)
    return True


def _clear_captcha_review_buttons(
    chat_id: str,
    message: Any,
    telegram: TelegramBotApi,
) -> None:
    message_id = message.get("message_id") if isinstance(message, dict) else None
    if not isinstance(message_id, int):
        return
    try:
        telegram.clear_inline_keyboard(chat_id, message_id)
    except TelegramControlError:
        logger.warning("Could not clear stale CAPTCHA review buttons message_id=%s", message_id)


def _save_captcha_review_answer(
    chat_id: str,
    answer: str,
    telegram: TelegramBotApi,
    admin_api: AdminApiClient,
    conversations: dict[str, CaptchaReviewConversation],
) -> bool:
    conversation = conversations.get(chat_id)
    if (
        conversation is None
        or conversation.current_event_id is None
        or conversation.current_image_sha256 is None
    ):
        telegram.send_message(chat_id, "El CAPTCHA actual ya no esta disponible.")
        return False
    event_id = conversation.current_event_id
    try:
        admin_api.save_captcha_human_label(
            event_id,
            answer,
            conversation.current_image_sha256,
            actor=_telegram_actor(chat_id),
        )
    except TelegramControlError as exc:
        logger.warning("Could not save Telegram CAPTCHA label event_id=%s error=%s", event_id, exc)
        conversations.pop(chat_id, None)
        telegram.send_message(
            chat_id,
            "No pude guardar la respuesta. Puede que el CAPTCHA ya haya sido "
            "revisado desde otra interfaz.",
            reply_markup=_main_menu_markup(),
        )
        return False
    _record_audit_safe(
        actor=_telegram_actor(chat_id),
        action="captcha_label",
        status="applied",
        target_type="captcha",
        target_id=event_id,
    )
    conversation.item_token = None
    conversation.current_event_id = None
    conversation.current_image_sha256 = None
    conversation.choice_answers = ()
    conversation.awaiting_manual_answer = False
    conversation.expires_at = time.monotonic() + CAPTCHA_REVIEW_TTL_SECONDS
    return True
