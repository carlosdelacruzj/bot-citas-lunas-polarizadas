from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import BrowserContext, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.whatsapp.album import (
    _attach_album_with_safe_page_retry as _attach_album_with_safe_page_retry,
)
from appointment_bot.browser.whatsapp.album import _prepare_album as _prepare_album
from appointment_bot.browser.whatsapp.album import _send_album as _send_album
from appointment_bot.browser.whatsapp.attachments import _attach_document as _attach_document
from appointment_bot.browser.whatsapp.attachments import _attach_image as _attach_image
from appointment_bot.browser.whatsapp.attachments import (
    _choose_document_files as _choose_document_files,
)
from appointment_bot.browser.whatsapp.attachments import (
    _click_attachment_button as _click_attachment_button,
)
from appointment_bot.browser.whatsapp.attachments import (
    _wait_for_attachment_menu as _wait_for_attachment_menu,
)
from appointment_bot.browser.whatsapp.common import (
    CHAT_READY_TIMEOUT_SECONDS as CHAT_READY_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    COMMAND_TIMEOUT_SECONDS as COMMAND_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    DAILY_SUMMARY_IMAGE_BATCH_SIZE as DAILY_SUMMARY_IMAGE_BATCH_SIZE,
)
from appointment_bot.browser.whatsapp.common import (
    PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS as PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS,
)
from appointment_bot.browser.whatsapp.common import (
    PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS as PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS,
)
from appointment_bot.browser.whatsapp.common import PROFILE_DIR as PROFILE_DIR
from appointment_bot.browser.whatsapp.common import WhatsAppSendUncertain as WhatsAppSendUncertain
from appointment_bot.browser.whatsapp.common import (
    _AttachmentBeforeFileSelectionError as _AttachmentBeforeFileSelectionError,
)
from appointment_bot.browser.whatsapp.common import _result as _result
from appointment_bot.browser.whatsapp.common import logger as logger
from appointment_bot.browser.whatsapp.composition import (
    _click_and_replace_text as _click_and_replace_text,
)
from appointment_bot.browser.whatsapp.composition import _fill_caption as _fill_caption
from appointment_bot.browser.whatsapp.composition import (
    _fill_selected_album_caption as _fill_selected_album_caption,
)
from appointment_bot.browser.whatsapp.composition import _paste_text_message as _paste_text_message
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_confirmed_status as _message_container_has_confirmed_status,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_large_image as _message_container_has_large_image,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_has_pending_status as _message_container_has_pending_status,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_is_outgoing as _message_container_is_outgoing,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _message_container_signature as _message_container_signature,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_image_message_records as _outgoing_image_message_records,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_message_signatures as _outgoing_message_signatures,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _plain_text_send_is_confirmed as _plain_text_send_is_confirmed,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_outgoing_images_uploaded as _wait_until_outgoing_images_uploaded,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_plain_text_send_finishes as _wait_until_plain_text_send_finishes,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _wait_until_send_attempt_finishes as _wait_until_send_attempt_finishes,
)
from appointment_bot.browser.whatsapp.documents import _prepare_documents as _prepare_documents
from appointment_bot.browser.whatsapp.dom import _album_control_summary as _album_control_summary
from appointment_bot.browser.whatsapp.dom import _album_thumbnails as _album_thumbnails
from appointment_bot.browser.whatsapp.dom import (
    _attachment_control_summary as _attachment_control_summary,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_menu_summary as _attachment_menu_summary,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_menu_visible as _attachment_menu_visible,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_option_container as _attachment_option_container,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_preview_visible as _attachment_preview_visible,
)
from appointment_bot.browser.whatsapp.dom import _caption_editor as _caption_editor
from appointment_bot.browser.whatsapp.dom import _caption_editor_summary as _caption_editor_summary
from appointment_bot.browser.whatsapp.dom import (
    _compact_alphanumeric_text as _compact_alphanumeric_text,
)
from appointment_bot.browser.whatsapp.dom import _document_file_input as _document_file_input
from appointment_bot.browser.whatsapp.dom import (
    _document_preview_visible as _document_preview_visible,
)
from appointment_bot.browser.whatsapp.dom import _file_input_summary as _file_input_summary
from appointment_bot.browser.whatsapp.dom import (
    _file_input_summary_from as _file_input_summary_from,
)
from appointment_bot.browser.whatsapp.dom import _image_file_input as _image_file_input
from appointment_bot.browser.whatsapp.dom import (
    _locator_has_visible_match as _locator_has_visible_match,
)
from appointment_bot.browser.whatsapp.dom import (
    _normal_chat_composer_visible as _normal_chat_composer_visible,
)
from appointment_bot.browser.whatsapp.dom import _plain_text_ready as _plain_text_ready
from appointment_bot.browser.whatsapp.dom import _safe_get_attribute as _safe_get_attribute
from appointment_bot.browser.whatsapp.dom import _safe_text_content as _safe_text_content
from appointment_bot.browser.whatsapp.dom import _same_editor_text as _same_editor_text
from appointment_bot.browser.whatsapp.dom import _visible as _visible
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name as _safe_whatsapp_artifact_name,
)
from appointment_bot.browser.whatsapp.evidence import (
    _save_context_failure_screenshot as _save_context_failure_screenshot,
)
from appointment_bot.browser.whatsapp.evidence import (
    _save_whatsapp_debug_screenshot as _save_whatsapp_debug_screenshot,
)
from appointment_bot.browser.whatsapp.evidence import (
    _whatsapp_qr_image_data_url as _whatsapp_qr_image_data_url,
)
from appointment_bot.browser.whatsapp.navigation import (
    _chat_not_ready_result as _chat_not_ready_result,
)
from appointment_bot.browser.whatsapp.navigation import (
    _click_username_chat_result as _click_username_chat_result,
)
from appointment_bot.browser.whatsapp.navigation import (
    _dismiss_safe_whatsapp_dialog as _dismiss_safe_whatsapp_dialog,
)
from appointment_bot.browser.whatsapp.navigation import (
    _dismiss_whatsapp_updates_dialog as _dismiss_whatsapp_updates_dialog,
)
from appointment_bot.browser.whatsapp.navigation import (
    _invalid_recipient_visible as _invalid_recipient_visible,
)
from appointment_bot.browser.whatsapp.navigation import _open_recipient_chat as _open_recipient_chat
from appointment_bot.browser.whatsapp.navigation import (
    _row_belongs_to_chat_results as _row_belongs_to_chat_results,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_username_chat_result_rows as _visible_username_chat_result_rows,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_whatsapp_dialogs as _visible_whatsapp_dialogs,
)
from appointment_bot.browser.whatsapp.navigation import (
    _visible_whatsapp_search as _visible_whatsapp_search,
)
from appointment_bot.browser.whatsapp.navigation import _wait_for_chat as _wait_for_chat
from appointment_bot.browser.whatsapp.navigation import (
    _wait_for_stable_username_chat_results as _wait_for_stable_username_chat_results,
)
from appointment_bot.browser.whatsapp.navigation import (
    _whatsapp_chat_row_label as _whatsapp_chat_row_label,
)
from appointment_bot.browser.whatsapp.sending import (
    _click_bottom_right_send_button as _click_bottom_right_send_button,
)
from appointment_bot.browser.whatsapp.sending import _click_send_button as _click_send_button
from appointment_bot.browser.whatsapp.sending import (
    _click_visible_send_button as _click_visible_send_button,
)
from appointment_bot.browser.whatsapp.sending import (
    _send_plain_text_message as _send_plain_text_message,
)
from appointment_bot.browser.whatsapp.session import (
    _HEADLESS_WHATSAPP_USER_AGENT as _HEADLESS_WHATSAPP_USER_AGENT,
)
from appointment_bot.browser.whatsapp.session import _close_context as _close_context
from appointment_bot.browser.whatsapp.session import _ensure_context as _ensure_context
from appointment_bot.browser.whatsapp.session import _fresh_whatsapp_page as _fresh_whatsapp_page
from appointment_bot.browser.whatsapp.session import (
    _headless_whatsapp_user_agent as _headless_whatsapp_user_agent,
)
from appointment_bot.browser.whatsapp.session import (
    _is_closed_target_error as _is_closed_target_error,
)
from appointment_bot.browser.whatsapp.session import (
    _validate_whatsapp_session as _validate_whatsapp_session,
)
from appointment_bot.browser.whatsapp.session import (
    _whatsapp_session_ready as _whatsapp_session_ready,
)


@dataclass
class _DraftCommand:
    draft: dict[str, object]
    response: queue.Queue[dict[str, object]]


class WhatsAppWebDraftManager:
    def __init__(self) -> None:
        self._commands: queue.Queue[_DraftCommand] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def prepare(self, draft: dict[str, object]) -> dict[str, object]:
        self._ensure_started()
        response: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        self._commands.put(_DraftCommand(draft=draft, response=response))
        try:
            return response.get(timeout=COMMAND_TIMEOUT_SECONDS)
        except queue.Empty:
            return _result(
                "web_unavailable",
                "WhatsApp Web no respondio a tiempo. "
                "Revisa la ventana abierta y vuelve a intentar.",
            )

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                name="whatsapp-web-draft-manager",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        context: BrowserContext | None = None
        context_headless: bool | None = None
        with sync_playwright() as playwright:
            while True:
                command = self._commands.get()
                requested_headless = bool(command.draft.get("headless"))
                try:
                    if context is not None and context_headless != requested_headless:
                        context = _close_context(context)
                        context_headless = None
                    context = _ensure_context(
                        playwright,
                        context,
                        headless=requested_headless,
                    )
                    context_headless = requested_headless
                    result = _prepare_draft(context, command.draft)
                except PlaywrightError as exc:
                    failure_evidence = _save_context_failure_screenshot(
                        context,
                        command.draft,
                    )
                    if _is_closed_target_error(exc):
                        if command.draft.get("disable_closed_target_retry"):
                            logger.warning(
                                "WhatsApp Web window closed while preparing draft; not retrying"
                            )
                            context = _close_context(context)
                            context_headless = None
                            result = _result(
                                "web_unavailable",
                                "WhatsApp Web se cerro durante la preparacion. "
                                "Si ya enviaste el mensaje, confirma el envio manualmente; "
                                "si no, vuelve a preparar el borrador.",
                                message_id=str(command.draft.get("message_id") or ""),
                                delivery_phase="send_state_unknown",
                                evidence_path=failure_evidence,
                            )
                            command.response.put(result)
                            continue
                        logger.warning(
                            "WhatsApp Web window closed while preparing draft; reopening once"
                        )
                        context = _close_context(context)
                        context_headless = None
                        try:
                            context = _ensure_context(
                                playwright,
                                context,
                                headless=requested_headless,
                            )
                            context_headless = requested_headless
                            result = _prepare_draft(context, command.draft)
                        except PlaywrightError as retry_exc:
                            retry_evidence = _save_context_failure_screenshot(
                                context,
                                command.draft,
                            )
                            logger.exception(
                                "Could not prepare WhatsApp Web draft after reopening"
                            )
                            context = _close_context(context)
                            context_headless = None
                            result = _result(
                                "web_unavailable",
                                f"No se pudo preparar WhatsApp Web: {retry_exc}",
                                delivery_phase="send_state_unknown",
                                evidence_path=retry_evidence,
                            )
                    else:
                        logger.exception("Could not prepare WhatsApp Web draft")
                        context = _close_context(context)
                        context_headless = None
                        result = _result(
                            "web_unavailable",
                            f"No se pudo preparar WhatsApp Web: {exc}",
                            delivery_phase="send_state_unknown",
                            evidence_path=failure_evidence,
                        )
                except Exception as exc:
                    failure_evidence = _save_context_failure_screenshot(
                        context,
                        command.draft,
                    )
                    logger.exception("Could not prepare WhatsApp Web draft")
                    if command.draft.get("close_on_error"):
                        context = _close_context(context)
                        context_headless = None
                    result = _result(
                        "web_unavailable",
                        f"No se pudo preparar WhatsApp Web: {exc}",
                        delivery_phase="send_state_unknown",
                        evidence_path=failure_evidence,
                    )
                command.response.put(result)


_MANAGER = WhatsAppWebDraftManager()


def prepare_whatsapp_web_draft(draft: dict[str, object]) -> dict[str, object]:
    return _MANAGER.prepare(draft)


def validate_whatsapp_web_session() -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "validate_session",
            "headless": True,
            "close_on_error": False,
            "disable_closed_target_retry": True,
        }
    )


def prepare_whatsapp_web_album(
    confirmation_draft: dict[str, object],
    payment_draft: dict[str, object],
    *,
    auto_send: bool = False,
) -> dict[str, object]:
    album_draft = {
        **confirmation_draft,
        "album_items": [confirmation_draft, payment_draft],
        "auto_send": auto_send,
        "close_on_error": False,
        "disable_closed_target_retry": auto_send,
        "headless": auto_send,
    }
    return _MANAGER.prepare(album_draft)


def prepare_whatsapp_web_documents(draft: dict[str, object]) -> dict[str, object]:
    document_draft = {
        **draft,
        "document_items": list(draft["attachment_paths"]),
        "disable_closed_target_retry": True,
        "close_on_error": True,
        "auto_send": True,
        "headless": True,
    }
    return _MANAGER.prepare(document_draft)


def send_whatsapp_web_daily_slot_summary(
    *,
    message_id: str,
    recipient_phone: str,
    message_text: str,
    publication_text: str,
    attachment_paths: list[str],
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "daily_slot_summary",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "message_text": message_text,
            "publication_text": publication_text,
            "attachment_paths": attachment_paths,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )


def send_whatsapp_web_registration_notice(
    *,
    message_id: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "registration_notice",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "recipient_username": recipient_username,
            "message_text": message_text,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )


def send_whatsapp_web_appointment_reminder(
    *,
    message_id: str,
    recipient_phone: str | None,
    recipient_username: str | None,
    message_text: str,
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "appointment_reminder",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
            "recipient_username": recipient_username,
            "message_text": message_text,
            "disable_closed_target_retry": True,
            "close_on_error": True,
            "headless": True,
        }
    )


def _prepare_draft(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    if draft.get("action") == "validate_session":
        return _validate_whatsapp_session(context)
    if draft.get("action") == "daily_slot_summary":
        return _send_daily_slot_summary(context, draft)
    if draft.get("action") == "registration_notice":
        return _send_registration_notice(context, draft)
    if draft.get("action") == "appointment_reminder":
        return _send_appointment_reminder(context, draft)
    if draft.get("album_items"):
        return _prepare_album(context, draft)
    if draft.get("document_items"):
        return _prepare_documents(context, draft)
    page = context.pages[0] if context.pages else context.new_page()
    message_id = str(draft["message_id"])
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-confirmation-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error

    attachment = Path(str(draft["attachment_path"])).resolve()
    if not attachment.is_file():
        raise FileNotFoundError("La constancia preparada ya no esta disponible.")
    try:
        _attach_image(page, attachment)
    except RuntimeError as exc:
        if "control para adjuntar" not in str(exc):
            raise
        recipient_error = _open_recipient_chat(
            page, draft, message_id, "whatsapp-confirmation-chat-retry-not-ready"
        )
        if recipient_error is not None:
            raise RuntimeError(str(recipient_error["message"])) from exc
        _attach_image(page, attachment)
    draft_mode = _fill_caption(page, str(draft["caption"]))
    if draft_mode == "queued_text":
        recipient_error = _open_recipient_chat(
            page, draft, message_id, "whatsapp-confirmation-text-retry-not-ready"
        )
        if recipient_error is not None:
            raise RuntimeError(str(recipient_error["message"]))
        _attach_image(page, attachment)
        draft_mode = _fill_caption(page, str(draft["caption"]))
        if draft_mode != "caption":
            raise RuntimeError(
                "WhatsApp no permitio unir el texto a la imagen; el borrador no se considera listo."
            )
    logger.info(
        "WhatsApp Web draft ready: message_id=%s test_mode=%s",
        message_id,
        draft["test_mode"],
    )
    return _result(
        "draft_ready",
        (
            "Imagen y texto listos. Revisa la ventana de WhatsApp y pulsa Enviar manualmente."
            if draft_mode == "caption"
            else "La imagen esta lista y el texto quedo preparado detras de la vista previa. "
            "Envia primero la imagen y luego pulsa Enviar una segunda vez para el texto."
        ),
        message_id=message_id,
        draft_mode=draft_mode,
    )


def _send_daily_slot_summary(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    attachments = [
        Path(str(path)).resolve()
        for path in list(draft.get("attachment_paths") or [])
    ]
    if attachments and not all(path.is_file() for path in attachments):
        raise FileNotFoundError(
            "Una de las imagenes marcadas del resumen diario ya no esta disponible."
        )

    page = _fresh_whatsapp_page(context)
    phone = "".join(
        character
        for character in str(draft["recipient_phone"])
        if character.isdigit()
    )
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name="whatsapp-daily-summary-chat-not-ready",
        )

    delivery_components = {
        "summary": "not_attempted",
        "images": "not_attempted" if attachments else "skipped",
        "publication": "not_attempted",
    }
    message_text = str(draft["message_text"])
    if message_text:
        text_sent = _send_plain_text_message(
            page,
            message_text,
            evidence_prefix=f"whatsapp-daily-summary-{evidence_id}-summary",
        )
        if not text_sent:
            delivery_components["summary"] = "uncertain"
            return _result(
                "send_uncertain",
                "WhatsApp no confirmo el mensaje del resumen diario.",
                message_id=message_id,
                delivery_phase="send_attempted",
                evidence_path=(
                    f".runtime/whatsapp-daily-summary-{evidence_id}-summary-"
                    "text-send-uncertain.png"
                ),
                delivery_components=delivery_components,
            )
        delivery_components["summary"] = "confirmed"
    else:
        delivery_components["summary"] = "skipped"

    if attachments:
        batches = [
            attachments[index : index + DAILY_SUMMARY_IMAGE_BATCH_SIZE]
            for index in range(0, len(attachments), DAILY_SUMMARY_IMAGE_BATCH_SIZE)
        ]
        confirmed_image_count = 0
        for batch_number, batch in enumerate(batches, start=1):
            batch_evidence_id = f"{evidence_id}-batch-{batch_number}-of-{len(batches)}"
            _attach_image(page, batch)
            page.wait_for_timeout(1_000)
            if len(_album_thumbnails(page)) != len(batch):
                _save_whatsapp_debug_screenshot(
                    page,
                    f"whatsapp-daily-summary-images-not-ready-{batch_evidence_id}",
                )
                raise RuntimeError(
                    "WhatsApp no mostro todas las imagenes del paquete "
                    f"{batch_number} de {len(batches)}."
                )
            _save_whatsapp_debug_screenshot(
                page,
                f"whatsapp-daily-summary-before-send-{batch_evidence_id}",
            )
            try:
                _send_album(
                    page,
                    expected_count=len(batch),
                    uncertain_screenshot_name=(
                        "whatsapp-daily-summary-upload-uncertain-"
                        f"{batch_evidence_id}"
                    ),
                )
            except WhatsAppSendUncertain as exc:
                delivery_components["images"] = "uncertain"
                context.close()
                return _result(
                    "send_uncertain",
                    (
                        f"{exc} Paquete {batch_number} de {len(batches)}; "
                        f"{confirmed_image_count} de {len(attachments)} "
                        "imagenes confirmadas antes de detener el envio."
                    ),
                    message_id=message_id,
                    delivery_phase="interaction_started",
                    evidence_path=exc.evidence_path,
                    delivery_components=delivery_components,
                )
            confirmed_image_count += len(batch)
            _save_whatsapp_debug_screenshot(
                page,
                f"whatsapp-daily-summary-images-sent-{batch_evidence_id}",
            )
        delivery_components["images"] = "confirmed"

    publication_sent = _send_plain_text_message(
        page,
        str(draft["publication_text"]),
        evidence_prefix=f"whatsapp-daily-summary-{evidence_id}-publication",
    )
    if not publication_sent:
        delivery_components["publication"] = "uncertain"
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo la publicacion diaria para TikTok.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-daily-summary-{evidence_id}-publication-"
                "text-send-uncertain.png"
            ),
            delivery_components=delivery_components,
        )
    delivery_components["publication"] = "confirmed"
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        "whatsapp-daily-summary-sent",
    )
    context.close()
    return _result(
        "sent",
        (
            "Resumen diario, imagenes y publicacion de TikTok "
            "enviados automaticamente."
        ),
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
        delivery_components=delivery_components,
    )


def _send_registration_notice(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-registration-notice-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    if not _send_plain_text_message(
        page,
        str(draft["message_text"]),
        evidence_prefix=f"whatsapp-registration-notice-{evidence_id}",
    ):
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo el aviso automatico de registro.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-registration-notice-{evidence_id}-"
                "text-send-uncertain.png"
            ),
        )
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        f"whatsapp-registration-notice-sent-{evidence_id}",
    )
    context.close()
    return _result(
        "sent",
        "Aviso automatico de registro enviado.",
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
    )


def _send_appointment_reminder(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    evidence_id = _safe_whatsapp_artifact_name(message_id)
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-appointment-reminder-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    if not _send_plain_text_message(
        page,
        str(draft["message_text"]),
        evidence_prefix=f"whatsapp-appointment-reminder-{evidence_id}",
    ):
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo el recordatorio automatico de cita.",
            message_id=message_id,
            delivery_phase="send_attempted",
            evidence_path=(
                f".runtime/whatsapp-appointment-reminder-{evidence_id}-"
                "text-send-uncertain.png"
            ),
        )
    sent_evidence_path = _save_whatsapp_debug_screenshot(
        page,
        f"whatsapp-appointment-reminder-sent-{evidence_id}",
    )
    context.close()
    return _result(
        "sent",
        "Recordatorio automatico de cita enviado.",
        message_id=message_id,
        sent=True,
        delivery_phase="confirmation_observed",
        evidence_path=sent_evidence_path,
    )
