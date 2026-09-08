from __future__ import annotations

import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

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

_HEADLESS_WHATSAPP_USER_AGENT: str | None = None


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


def _is_closed_target_error(exc: PlaywrightError) -> bool:
    message = str(exc).casefold()
    return exc.__class__.__name__ == "TargetClosedError" or (
        "target" in message and "has been closed" in message
    )


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


def _ensure_context(
    playwright,
    context: BrowserContext | None,
    *,
    headless: bool = False,
) -> BrowserContext:
    if context is not None:
        try:
            if context.pages:
                return context
        except PlaywrightError:
            context = _close_context(context)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context_options: dict[str, object] = {
        "headless": headless,
        "viewport": {"width": 1440, "height": 1000} if headless else None,
        "args": [] if headless else ["--start-maximized"],
    }
    if headless:
        context_options["user_agent"] = _headless_whatsapp_user_agent(playwright)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR.resolve()),
        **context_options,
    )


def _headless_whatsapp_user_agent(playwright) -> str:
    global _HEADLESS_WHATSAPP_USER_AGENT
    if _HEADLESS_WHATSAPP_USER_AGENT is not None:
        return _HEADLESS_WHATSAPP_USER_AGENT
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        user_agent = str(page.evaluate("navigator.userAgent"))
    finally:
        browser.close()
    _HEADLESS_WHATSAPP_USER_AGENT = user_agent.replace(
        "HeadlessChrome/",
        "Chrome/",
    )
    return _HEADLESS_WHATSAPP_USER_AGENT


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


def _prepare_album(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    items = list(draft["album_items"])
    if len(items) != 2:
        raise ValueError("El album de WhatsApp requiere exactamente dos imagenes.")
    attachments = [Path(str(item["attachment_path"])).resolve() for item in items]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Una de las imagenes preparadas ya no esta disponible.")
    page_or_error = _attach_album_with_safe_page_retry(context, draft, attachments)
    if isinstance(page_or_error, dict):
        return page_or_error
    page = page_or_error
    page.wait_for_timeout(1_000)
    thumbnails = _album_thumbnails(page)
    if len(thumbnails) != len(items):
        logger.info("WhatsApp Web album controls: %s", _album_control_summary(page))
        raise RuntimeError("WhatsApp no mostro las dos miniaturas del album.")
    captions = [str(item["caption"]) for item in items]
    combined_caption = "\n\n".join(caption for caption in captions if caption.strip())
    caption_ready = True
    try:
        _fill_selected_album_caption(page, combined_caption)
    except RuntimeError:
        caption_ready = False
        _save_whatsapp_debug_screenshot(page, "whatsapp-album-caption-not-ready")
        logger.exception("Could not write WhatsApp album caption")
    if draft.get("auto_send"):
        if not caption_ready:
            raise RuntimeError(
                "WhatsApp no confirmo el texto del album; no se realizo el envio automatico."
            )
        _save_whatsapp_debug_screenshot(page, "whatsapp-album-before-send")
        message_id = str(draft["message_id"])
        evidence_id = _safe_whatsapp_artifact_name(message_id)
        try:
            _send_album(
                page,
                uncertain_screenshot_name=(
                    f"whatsapp-album-upload-uncertain-{evidence_id}"
                ),
            )
        except WhatsAppSendUncertain as exc:
            context.close()
            logger.warning(
                "WhatsApp Web album delivery is uncertain: message_id=%s",
                message_id,
            )
            return _result(
                "send_uncertain",
                str(exc),
                message_id=message_id,
                draft_mode="album",
                manual_send_required=True,
                sent=False,
                delivery_phase="interaction_started",
                evidence_path=exc.evidence_path,
            )
        sent_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            "whatsapp-album-sent",
        )
        context.close()
        logger.info(
            "WhatsApp Web album sent automatically: message_id=%s items=%s",
            draft["message_id"],
            len(items),
        )
        return _result(
            "sent",
            "Constancia y cobro enviados automaticamente.",
            message_id=str(draft["message_id"]),
            draft_mode="album",
            manual_send_required=False,
            sent=True,
            delivery_phase="confirmation_observed",
            evidence_path=sent_evidence_path,
        )
    ready_screenshot = Path(".runtime/whatsapp-album-ready.png").resolve()
    ready_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ready_screenshot))
    logger.info(
        "WhatsApp Web album ready: message_id=%s items=%s",
        draft["message_id"],
        len(items),
    )
    return _result(
        "draft_ready",
        (
            "Las dos imagenes y el texto quedaron listos. "
            "Revisa el album y pulsa Enviar una sola vez."
            if caption_ready
            else "Las dos imagenes quedaron cargadas. "
            "WhatsApp no confirmo el texto; revisa el album antes de enviar."
        ),
        message_id=str(draft["message_id"]),
        draft_mode="album",
    )


def _attach_album_with_safe_page_retry(
    context: BrowserContext,
    draft: dict[str, object],
    attachments: list[Path],
) -> Page | dict[str, object]:
    for page_attempt in range(1, 3):
        page = _fresh_whatsapp_page(context)
        recipient_error = _open_recipient_chat(
            page, draft, str(draft["message_id"]), "whatsapp-album-chat-not-ready"
        )
        if recipient_error is not None:
            return recipient_error
        try:
            _attach_image(page, attachments)
            return page
        except _AttachmentBeforeFileSelectionError:
            if page_attempt == 2:
                raise
            logger.info(
                "WhatsApp album safe page retry before file selection: "
                "message_id=%s",
                draft["message_id"],
            )
    raise RuntimeError("WhatsApp no pudo preparar el album despues del reintento seguro.")


def _prepare_documents(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    message_id = str(draft["message_id"])
    recipient_error = _open_recipient_chat(
        page, draft, message_id, "whatsapp-followup-chat-not-ready"
    )
    if recipient_error is not None:
        return recipient_error
    attachments = [Path(str(item)).resolve() for item in draft["document_items"]]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Uno de los PDFs preparados ya no esta disponible.")
    _attach_document(page, attachments)
    if draft.get("auto_send"):
        documents_confirmed = _click_send_button(page, attachments)
        text_sent = _send_plain_text_message(
            page,
            str(draft["caption"]),
            evidence_prefix=(
                "whatsapp-followup-"
                f"{_safe_whatsapp_artifact_name(message_id)}"
            ),
        )
        delivery_components = {
            "documents": "confirmed" if documents_confirmed else "uncertain",
            "payment_confirmation": "confirmed" if text_sent else "uncertain",
        }
        if not documents_confirmed or not text_sent:
            evidence_path = _save_whatsapp_debug_screenshot(
                page,
                (
                    "whatsapp-followup-"
                    f"{_safe_whatsapp_artifact_name(message_id)}-components-uncertain"
                ),
            )
            logger.warning(
                "WhatsApp Web follow-up was not fully confirmed: "
                "message_id=%s documents_confirmed=%s text_confirmed=%s",
                message_id,
                documents_confirmed,
                text_sent,
            )
            if documents_confirmed:
                message = (
                    "Los PDFs salieron, pero WhatsApp no confirmo el texto post-pago. "
                    "No se marcara el paquete completo como enviado ni se reintentara "
                    "automaticamente."
                )
            elif text_sent:
                message = (
                    "WhatsApp cerro la vista previa de los PDFs sin permitir confirmar "
                    "automaticamente todas sus burbujas. El mensaje de pago confirmado "
                    "si fue enviado y confirmado; no se repetiran los PDFs."
                )
            else:
                message = (
                    "WhatsApp cerro la vista previa de los PDFs sin permitir confirmar "
                    "automaticamente todas sus burbujas y tampoco confirmo el mensaje "
                    "de pago. No se reintentara automaticamente."
                )
            if documents_confirmed:
                delivery_phase = "documents_confirmed_text_unconfirmed"
            elif text_sent:
                delivery_phase = "documents_unconfirmed_text_confirmed"
            else:
                delivery_phase = "documents_and_text_unconfirmed"
            return _result(
                "send_uncertain",
                message,
                message_id=message_id,
                draft_mode="documents",
                manual_send_required=True,
                delivery_phase=delivery_phase,
                evidence_path=evidence_path,
                delivery_components=delivery_components,
            )
        sent_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"whatsapp-followup-{_safe_whatsapp_artifact_name(message_id)}-sent",
        )
        context.close()
        logger.info(
            "WhatsApp Web follow-up sent automatically: message_id=%s documents=%s",
            message_id,
            len(attachments),
        )
        return _result(
            "sent",
            "PDFs y texto post-pago enviados automaticamente.",
            message_id=message_id,
            draft_mode="documents",
            manual_send_required=False,
            sent=True,
            delivery_phase="confirmation_observed",
            evidence_path=sent_evidence_path,
            delivery_components=delivery_components,
        )
    draft_mode = _fill_caption(
        page,
        str(draft["caption"]),
        require_full_match=True,
        allow_footer_editor=True,
        trust_inserted_text=True,
    )
    if draft_mode != "caption":
        _save_whatsapp_debug_screenshot(page, "whatsapp-followup-caption-not-ready")
        raise RuntimeError(
            "WhatsApp no permitio unir el texto a los documentos; "
            "el borrador no se considera listo."
        )
    ready_screenshot = Path(".runtime/whatsapp-followup-ready.png").resolve()
    ready_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(ready_screenshot))
    logger.info(
        "WhatsApp Web follow-up ready: message_id=%s documents=%s",
        message_id,
        len(attachments),
    )
    return _result(
        "draft_ready",
        "PDFs y texto post-pago listos. Revisa WhatsApp y pulsa Enviar una sola vez.",
        message_id=message_id,
        draft_mode="documents",
    )


def _validate_whatsapp_session(context: BrowserContext) -> dict[str, object]:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(
        "https://web.whatsapp.com/",
        wait_until="domcontentloaded",
        timeout=45_000,
    )
    deadline = time.monotonic() + CHAT_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _whatsapp_session_ready(page):
            logger.info("WhatsApp Web headless session validated")
            return _result(
                "session_ready",
                "WhatsApp esta vinculado y listo para envios automaticos.",
                manual_send_required=False,
            )
        qr_image_data_url = _whatsapp_qr_image_data_url(page)
        if qr_image_data_url is not None:
            return _result(
                "login_required",
                "Escanea el QR y luego pulsa Comprobar vinculacion.",
                qr_image_data_url=qr_image_data_url,
            )
        page.wait_for_timeout(500)
    _save_whatsapp_debug_screenshot(page, "whatsapp-session-validation-timeout")
    return _result(
        "web_unavailable",
        "WhatsApp no termino de cargar la sesion ni mostro un QR.",
    )


def _whatsapp_session_ready(page: Page) -> bool:
    if _normal_chat_composer_visible(page):
        return True
    return any(
        _visible(page, selector)
        for selector in (
            "#pane-side",
            "[data-testid='chat-list']",
            "[aria-label='Chat list']",
            "[aria-label='Lista de chats']",
        )
    )


def _send_album(
    page: Page,
    *,
    expected_count: int = 2,
    uncertain_screenshot_name: str = "whatsapp-album-upload-uncertain",
) -> None:
    if len(_album_thumbnails(page)) != expected_count:
        raise RuntimeError(
            "WhatsApp no mantuvo todas las miniaturas antes del envio."
        )
    initial_image_signatures = {
        signature for signature, _state in _outgoing_image_message_records(page)
    }
    viewport = page.viewport_size or {"width": 0, "height": 0}
    if not viewport["width"] or not viewport["height"]:
        raise RuntimeError("WhatsApp no informo el tamaño de la ventana para enviar el album.")
    if not _click_visible_send_button(page):
        page.mouse.click(viewport["width"] - 48, viewport["height"] - 50)
    deadline = time.monotonic() + 30
    next_send_retry_at = time.monotonic() + 2
    while time.monotonic() < deadline:
        if not _album_thumbnails(page) and _normal_chat_composer_visible(page):
            page.wait_for_timeout(1_000)
            if not _album_thumbnails(page):
                if not _wait_until_outgoing_images_uploaded(
                    page,
                    initial_signatures=initial_image_signatures,
                    expected_count=expected_count,
                ):
                    evidence_path = _save_whatsapp_debug_screenshot(
                        page,
                        uncertain_screenshot_name,
                    )
                    raise WhatsAppSendUncertain(
                        "WhatsApp cerro la vista previa, pero no confirmo "
                        "la carga de todas las imagenes.",
                        evidence_path=evidence_path,
                    )
                return
        elif time.monotonic() >= next_send_retry_at:
            if not _click_visible_send_button(page):
                page.keyboard.press("Enter")
            elif _album_thumbnails(page):
                page.keyboard.press("Enter")
            next_send_retry_at = time.monotonic() + 2
        page.wait_for_timeout(500)
    evidence_path = _save_whatsapp_debug_screenshot(
        page,
        uncertain_screenshot_name,
    )
    raise WhatsAppSendUncertain(
        "WhatsApp no confirmo el envio del album; las miniaturas continuaron visibles.",
        evidence_path=evidence_path,
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


def _fill_selected_album_caption(page: Page, caption: str) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        editor = _caption_editor(page)
        if editor is not None:
            _click_and_replace_text(page, editor, caption)
            page.wait_for_timeout(300)
            if _same_editor_text(_safe_text_content(editor), caption):
                return
            if len(caption) > 80 and any(
                marker in _safe_text_content(editor)
                for marker in ("Pago", "confirmado", "soles", "CLIENTE")
            ):
                return
            _paste_text_message(page, editor, caption)
            page.wait_for_timeout(300)
            if _same_editor_text(_safe_text_content(editor), caption):
                return
        page.wait_for_timeout(300)
    raise RuntimeError("No se pudo escribir la descripcion de una imagen del album.")


def _open_recipient_chat(
    page: Page,
    draft: dict[str, object],
    message_id: str,
    screenshot_name: str,
) -> dict[str, object] | None:
    phone = "".join(
        character
        for character in str(draft.get("recipient_phone") or "")
        if character.isdigit()
    )
    if phone:
        page.goto(
            f"https://web.whatsapp.com/send?phone={phone}",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        if _wait_for_chat(page):
            return None
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )

    username = str(draft.get("recipient_username") or "").strip()
    if not username.startswith("@"):
        return _result(
            "recipient_not_configured",
            "La orden no tiene un numero ni un usuario de WhatsApp valido.",
            message_id=message_id,
        )
    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=45_000)
    _dismiss_whatsapp_updates_dialog(page)
    search = _visible_whatsapp_search(page)
    if search is None:
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )
    search.click()
    search.fill(username)
    page.wait_for_timeout(700)
    rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1:
        logger.info(
            "WhatsApp username search retry before send: phase=username_search_retry"
        )
        visible_dialogs = _visible_whatsapp_dialogs(page)
        if visible_dialogs:
            _dismiss_safe_whatsapp_dialog(page, visible_dialogs)
        search = _visible_whatsapp_search(page)
        if search is not None:
            search.click()
            search.fill("")
            page.wait_for_timeout(800)
            search.fill(username)
            page.wait_for_timeout(1_200)
            rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        status = "recipient_not_found" if not rows else "recipient_ambiguous"
        detail = "no aparecio" if not rows else "aparecio mas de una vez"
        return _result(
            status,
            f"El usuario {username} {detail} como chat unico en WhatsApp. No se envio nada.",
            message_id=message_id,
        )
    expected_chat_label = _whatsapp_chat_row_label(rows[0])
    if not expected_chat_label:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        return _result(
            "recipient_mismatch",
            "WhatsApp no permitio identificar el chat encontrado para "
            f"{username}. No se envio nada.",
            message_id=message_id,
        )
    click_error = _click_username_chat_result(
        page,
        username=username,
        expected_chat_label=expected_chat_label,
        row=rows[0],
        message_id=message_id,
    )
    if click_error is not None:
        return click_error
    try:
        page.locator("header[data-testid='conversation-header']").wait_for(
            state="visible", timeout=10_000
        )
    except PlaywrightError:
        pass
    header = page.locator("header[data-testid='conversation-header']")
    header_text = _safe_text_content(header).casefold() if header.count() else ""
    header_titles = [
        str(header.locator("[title]").nth(index).get_attribute("title") or "").casefold()
        for index in range(header.locator("[title]").count())
    ] if header.count() else []
    expected_label = expected_chat_label.casefold()
    if expected_label not in header_text and expected_label not in header_titles:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        return _result(
            "recipient_mismatch",
            "WhatsApp abrio un chat distinto del resultado unico para "
            f"{username}. No se envio nada.",
            message_id=message_id,
        )
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )
    return None


def _visible_whatsapp_search(page: Page):
    selectors = (
        "input[aria-label='Buscar un chat o iniciar uno nuevo']",
        "input[aria-label='Search or start a new chat']",
        "[data-tab='3'][contenteditable='true']",
    )
    deadline = time.monotonic() + CHAT_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector)
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    return candidate
        page.wait_for_timeout(300)
    return None


def _dismiss_whatsapp_updates_dialog(page: Page) -> None:
    dialogs = page.locator("[role='dialog']")
    for index in range(dialogs.count()):
        dialog = dialogs.nth(index)
        if not dialog.is_visible():
            continue
        text = _safe_text_content(dialog).casefold()
        if "novedades en whatsapp web" not in text and "what's new in whatsapp web" not in text:
            continue
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return


def _click_username_chat_result(
    page: Page,
    *,
    username: str,
    expected_chat_label: str,
    row,
    message_id: str,
) -> dict[str, object] | None:
    try:
        row.click(timeout=4_000)
        return None
    except PlaywrightError as exc:
        evidence_name = (
            "whatsapp-recipient-chat-blocked-"
            f"{_safe_whatsapp_artifact_name(message_id)}"
        )
        evidence_path = _save_whatsapp_debug_screenshot(page, evidence_name)
        visible_dialogs = _visible_whatsapp_dialogs(page)
        logger.warning(
            "WhatsApp username chat click was blocked: message_id=%s dialogs=%s error=%s",
            message_id,
            len(visible_dialogs),
            exc.__class__.__name__,
        )
        if not visible_dialogs or not _dismiss_safe_whatsapp_dialog(page, visible_dialogs):
            return _result(
                "recipient_chat_blocked",
                (
                    f"WhatsApp no permitio abrir el chat unico para {username}. "
                    "No se escribio ni envio ningun mensaje."
                ),
                message_id=message_id,
                delivery_phase="chat_not_opened",
                evidence_path=evidence_path,
            )

    search = _visible_whatsapp_search(page)
    if search is None:
        return _result(
            "recipient_chat_blocked",
            (
                f"WhatsApp cerro el dialogo, pero no recupero la busqueda de {username}. "
                "No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=evidence_path,
        )
    search.click()
    search.fill(username)
    page.wait_for_timeout(700)
    rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1 or _whatsapp_chat_row_label(rows[0]) != expected_chat_label:
        retry_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"{evidence_name}-retry-result-mismatch",
        )
        return _result(
            "recipient_mismatch",
            (
                f"WhatsApp no recupero el mismo chat unico para {username} despues "
                "de cerrar el dialogo. No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=retry_evidence_path,
        )
    try:
        rows[0].click(timeout=4_000)
    except PlaywrightError as exc:
        retry_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"{evidence_name}-retry-failed",
        )
        logger.warning(
            "WhatsApp username chat retry failed before send: message_id=%s error=%s",
            message_id,
            exc.__class__.__name__,
        )
        return _result(
            "recipient_chat_blocked",
            (
                f"WhatsApp volvio a bloquear el chat unico para {username}. "
                "No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=retry_evidence_path,
        )
    return None


def _wait_for_stable_username_chat_results(page: Page) -> list[Any]:
    deadline = time.monotonic() + 15
    rows: list[Any] = []
    previous_labels: tuple[str, ...] | None = None
    stable_reads = 0
    while time.monotonic() < deadline:
        rows = _visible_username_chat_result_rows(page)
        labels = tuple(_whatsapp_chat_row_label(row) for row in rows)
        stable_reads = stable_reads + 1 if labels == previous_labels else 0
        previous_labels = labels
        if rows and stable_reads >= 2:
            break
        page.wait_for_timeout(300)
    return rows


def _visible_whatsapp_dialogs(page: Page) -> list[Any]:
    dialogs = page.locator("[role='dialog'][aria-modal='true'], [role='dialog']")
    return [
        dialogs.nth(index)
        for index in range(dialogs.count())
        if dialogs.nth(index).is_visible()
    ]


def _dismiss_safe_whatsapp_dialog(page: Page, dialogs: list[Any]) -> bool:
    safe_labels = (
        "Cancelar",
        "Cancel",
        "Cerrar",
        "Close",
        "Ahora no",
        "Not now",
        "Entendido",
        "Got it",
    )
    for dialog in dialogs:
        for label in safe_labels:
            button = dialog.get_by_role("button", name=label, exact=True)
            if button.count() and button.first.is_visible():
                button.first.click(timeout=2_000)
                page.wait_for_timeout(500)
                return not _visible_whatsapp_dialogs(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return not _visible_whatsapp_dialogs(page)


def _visible_username_chat_result_rows(page: Page) -> list[Any]:
    rows: list[Any] = []
    seen: set[str] = set()
    candidates = page.locator("[data-testid='cell-frame-container']")
    for index in range(candidates.count()):
        row = candidates.nth(index)
        if not row.is_visible() or not _row_belongs_to_chat_results(row):
            continue
        container = row.locator("xpath=ancestor::*[@role='row'][1]")
        key = str(
            container.get_attribute("data-testid")
            or row.get_attribute("data-id")
            or _whatsapp_chat_row_label(row)
        ).strip()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _row_belongs_to_chat_results(row) -> bool:
    container = row.locator("xpath=ancestor::*[@role='row'][1]")
    if container.count() != 1:
        return False
    section = container.locator("xpath=preceding-sibling::*[1]")
    if section.count() != 1:
        return False
    return _safe_text_content(section).strip().casefold() == "chats"


def _whatsapp_chat_row_label(row) -> str:
    titles = row.locator("span[title]")
    for index in range(titles.count()):
        title = titles.nth(index)
        value = str(title.get_attribute("title") or "").strip()
        if title.is_visible() and value:
            return value
    return ""


def _wait_for_chat(page: Page) -> bool:
    deadline = time.monotonic() + CHAT_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _visible(page, "div[data-testid='conversation-compose-box-input']"):
            return True
        if _whatsapp_qr_image_data_url(page) is not None or _invalid_recipient_visible(page):
            return False
        page.wait_for_timeout(500)
    return _visible(page, "div[data-testid='conversation-compose-box-input']")


def _chat_not_ready_result(
    page: Page,
    *,
    message_id: str,
    screenshot_name: str,
) -> dict[str, object]:
    _save_whatsapp_debug_screenshot(page, f"{screenshot_name}-{message_id}")
    qr_image_data_url = _whatsapp_qr_image_data_url(page)
    if qr_image_data_url is not None:
        return _result(
            "login_required",
            "La sesion de WhatsApp necesita vincularse antes de enviar.",
            message_id=message_id,
            qr_image_data_url=qr_image_data_url,
        )
    if _invalid_recipient_visible(page):
        return _result(
            "invalid_recipient",
            "WhatsApp rechazo el destinatario; verifica que el numero sea valido y tenga WhatsApp.",
            message_id=message_id,
        )
    return _result(
        "chat_unavailable",
        "La sesion esta vinculada, pero el chat del destinatario no quedo listo a tiempo.",
        message_id=message_id,
    )


def _invalid_recipient_visible(page: Page) -> bool:
    try:
        body_text = page.locator("body").inner_text(timeout=1_000)
    except PlaywrightError:
        return False
    normalized = " ".join(body_text.casefold().split())
    return any(
        pattern in normalized
        for pattern in (
            "phone number shared via url is invalid",
            "phone number is not valid",
            "invalid phone number",
            "isn't on whatsapp",
            "isn’t on whatsapp",
            "is not on whatsapp",
            "not on whatsapp",
            "numero de telefono compartido a traves de la direccion url no es valido",
            "número de teléfono compartido a través de la dirección url no es válido",
            "numero de telefono no valido",
            "número de teléfono no válido",
            "el numero no esta en whatsapp",
            "el número no está en whatsapp",
            "no esta en whatsapp",
            "no está en whatsapp",
        )
    )


def _attach_image(page: Page, attachment: Path | list[Path]) -> None:
    files = (
        [str(item) for item in attachment]
        if isinstance(attachment, list)
        else [str(attachment)]
    )
    failure_phase = "attach_control_not_found"
    file_selection_started = False
    for attempt in range(1, 3):
        if attempt == 2:
            logger.info(
                "WhatsApp image attachment safe retry before file selection: "
                "phase=%s",
                failure_phase,
            )
            if not _wait_for_chat(page):
                failure_phase = "chat_not_ready_before_attachment_retry"
                break
        if not _click_attachment_button(page):
            failure_phase = "attach_control_not_found"
            continue
        if not _wait_for_attachment_menu(page):
            failure_phase = "attach_menu_not_opened"
            logger.info(
                "WhatsApp Web attachment menu not ready: attempt=%s phase=%s",
                attempt,
                failure_phase,
            )
            continue

        media_option = page.get_by_text(
            re.compile(r"^(Fotos y v.deos|Photos and videos|Photos & videos)$", re.I)
        ).last
        if media_option.count() and media_option.is_visible():
            container = _attachment_option_container(media_option)
            option_input = container.locator("input[type='file']")
            if option_input.count():
                try:
                    file_selection_started = True
                    option_input.first.set_input_files(files)
                    page.wait_for_timeout(1_000)
                    return
                except PlaywrightError:
                    logger.info("Fotos y videos input did not accept the selected files")
            try:
                with page.expect_file_chooser(timeout=3_000) as chooser_info:
                    container.click()
                file_selection_started = True
                chooser_info.value.set_files(files)
                page.wait_for_timeout(1_000)
                return
            except PlaywrightError:
                logger.info("Fotos y videos did not open a file chooser")

        logger.info("WhatsApp Web attachment menu: %s", _attachment_menu_summary(page))
        file_input = _image_file_input(page, require_multiple=len(files) > 1)
        if file_input is not None:
            file_selection_started = True
            file_input.set_input_files(files)
            page.wait_for_timeout(1_000)
            return
        failure_phase = (
            "non_multiple_input"
            if len(files) > 1 and _image_file_input(page) is not None
            else "media_picker_not_ready"
        )

    logger.info("WhatsApp Web file inputs: %s", _file_input_summary(page))
    logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
    error_message = (
        "No se encontro el control para adjuntar imagenes en WhatsApp Web. "
        f"Fase: {failure_phase}."
    )
    if failure_phase == "non_multiple_input" and not file_selection_started:
        raise _AttachmentBeforeFileSelectionError(error_message)
    raise RuntimeError(error_message)


def _click_attachment_button(page: Page) -> bool:
    selectors = (
        "footer [role='button'][aria-label*='Attach' i]",
        "footer [role='button'][aria-label*='Adjuntar' i]",
        "footer [role='button'][aria-label*='archivo' i]",
        "footer button[aria-label*='Attach' i]",
        "footer button[aria-label*='Adjuntar' i]",
        "footer button[aria-label*='archivo' i]",
        "footer [title*='Attach' i]",
        "footer [title*='Adjuntar' i]",
        "footer [title*='archivo' i]",
        "footer span[data-icon='plus-rounded']",
        "footer span[data-icon='plus']",
        "footer span[data-icon='clip']",
    )
    for selector in selectors:
        locator = page.locator(selector).first
        if not locator.count() or not locator.is_visible():
            continue
        target = locator
        button = locator.locator("xpath=ancestor::button[1]")
        role_button = locator.locator("xpath=ancestor::*[@role='button'][1]")
        if button.count():
            target = button.first
        elif role_button.count():
            target = role_button.first
        target.click(timeout=3_000, force=True)
        page.wait_for_timeout(1_200)
        return True
    return False


def _wait_for_attachment_menu(page: Page, *, timeout_seconds: float = 3) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _attachment_menu_visible(page):
            return True
        page.wait_for_timeout(250)
    return False


def _attach_document(page: Page, attachment: Path | list[Path]) -> None:
    files = (
        [str(item) for item in attachment]
        if isinstance(attachment, list)
        else [str(attachment)]
    )
    deadline = time.monotonic() + 20
    file_input = None
    attachment_opened = False
    while time.monotonic() < deadline and file_input is None:
        direct_input = _document_file_input(page)
        if direct_input is not None:
            direct_input.set_input_files(files)
            page.wait_for_timeout(1_000)
            return
        if not attachment_opened:
            attachment_clicked = _click_attachment_button(page)
            if attachment_clicked:
                attachment_opened = _wait_for_attachment_menu(page)
        elif attachment_opened:
            if _choose_document_files(page, files):
                return
            logger.info("WhatsApp Web attachment menu: %s", _attachment_menu_summary(page))
            logger.info("WhatsApp Web file inputs: %s", _file_input_summary(page))
            file_input = _document_file_input(page)
            if file_input is None and not _attachment_menu_visible(page):
                attachment_opened = False
        page.wait_for_timeout(400)
    if file_input is None:
        _save_whatsapp_debug_screenshot(page, "whatsapp-document-input-missing")
        logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
        raise RuntimeError("No se encontro el control para adjuntar documentos en WhatsApp Web.")
    file_input.set_input_files(files)
    page.wait_for_timeout(1_000)


def _choose_document_files(page: Page, files: list[str]) -> bool:
    candidates = [
        page.locator(
            "[aria-label='Documento'], [aria-label='Document'], "
            "[title='Documento'], [title='Document']"
        ).last,
        page.get_by_text(re.compile(r"^(Documento|Document)$", re.I)).last,
        page.locator(
            "[role='menu'] [aria-label='Documento'], "
            "[role='menu'] [aria-label='Document']"
        ).last,
        page.locator("[role='menuitem']").filter(
            has_text=re.compile(r"^(Documento|Document)$", re.I)
        ).last,
        page.locator("[role='button']").filter(
            has_text=re.compile(r"^(Documento|Document)$", re.I)
        ).last,
        page.locator("li").filter(has_text=re.compile(r"^(Documento|Document)$", re.I)).last,
        page.locator("[tabindex='0']").filter(
            has_text=re.compile(r"^(Documento|Document)$", re.I)
        ).last,
    ]
    for candidate in candidates:
        if not candidate.count() or not candidate.is_visible():
            continue
        if candidate.get_attribute("title") and candidate.get_attribute("title").startswith("Ver "):
            continue
        target = _attachment_option_container(candidate)
        option_input = target.locator("input[type='file']")
        if option_input.count():
            option_input.first.set_input_files(files)
            page.wait_for_timeout(1_000)
            return True
        try:
            with page.expect_file_chooser(timeout=5_000) as chooser_info:
                target.click(timeout=2_000, force=True)
            chooser_info.value.set_files(files)
            page.wait_for_timeout(1_000)
            return True
        except PlaywrightError:
            logger.info("Documento target did not open a file chooser")
    return False


def _fill_caption(
    page: Page,
    caption: str,
    *,
    require_full_match: bool = False,
    allow_footer_editor: bool = False,
    trust_inserted_text: bool = False,
) -> str:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        editor = _caption_editor(page, allow_footer_editor=allow_footer_editor)
        if editor is not None:
            _click_and_replace_text(page, editor, caption)
            page.wait_for_timeout(300)
            if trust_inserted_text and _attachment_preview_visible(page, []):
                return "caption"
            if _same_editor_text(
                _safe_text_content(editor),
                caption,
                require_full_match=require_full_match,
            ):
                return "caption"
        page.wait_for_timeout(400)
    composer = page.locator("div[data-testid='conversation-compose-box-input']").first
    if composer.count() and composer.is_visible():
        _click_and_replace_text(page, composer, caption)
        page.wait_for_timeout(300)
        if trust_inserted_text and _attachment_preview_visible(page, []):
            return "queued_text"
        if _same_editor_text(
            _safe_text_content(composer),
            caption,
            require_full_match=require_full_match,
        ):
            return "queued_text"
    _save_whatsapp_debug_screenshot(page, "whatsapp-caption-field-missing")
    logger.info("WhatsApp Web caption editors: %s", _caption_editor_summary(page))
    raise RuntimeError("La imagen se adjunto, pero no se encontro el campo para el texto.")


def _click_send_button(page: Page, attachments: list[Path]) -> bool:
    attachment_names = [attachment.name for attachment in attachments]
    outgoing_signatures = _outgoing_message_signatures(page)
    if _document_preview_visible(page, attachment_names):
        if _click_bottom_right_send_button(page):
            return _wait_until_send_attempt_finishes(
                page,
                attachment_names=attachment_names,
                outgoing_signatures=outgoing_signatures,
                expected_outgoing_count=len(attachments),
            )
    selectors = (
        "[data-testid='send']",
        "button[aria-label*='Enviar' i]",
        "button[aria-label*='Send' i]",
        "[role='button'][aria-label*='Enviar' i]",
        "[role='button'][aria-label*='Send' i]",
        "span[data-icon='send']",
        "span[data-icon*='send' i]",
        "button:has(span[data-icon*='send' i])",
        "[role='button']:has(span[data-icon*='send' i])",
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector).last
            if not locator.count() or not locator.is_visible():
                continue
            target = locator
            button = locator.locator("xpath=ancestor::button[1]")
            role_button = locator.locator("xpath=ancestor::*[@role='button'][1]")
            if button.count():
                target = button.first
            elif role_button.count():
                target = role_button.first
            _save_whatsapp_debug_screenshot(page, "whatsapp-followup-before-send")
            target.click(timeout=2_000, force=True)
            return _wait_until_send_attempt_finishes(
                page,
                attachment_names=attachment_names,
                outgoing_signatures=outgoing_signatures,
                expected_outgoing_count=len(attachments),
            )
        page.wait_for_timeout(500)
    if _attachment_preview_visible(
        page,
        attachment_names,
    ) and _click_bottom_right_send_button(page):
        return _wait_until_send_attempt_finishes(
            page,
            attachment_names=attachment_names,
            outgoing_signatures=outgoing_signatures,
            expected_outgoing_count=len(attachments),
        )
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-send-button-missing")
    raise RuntimeError("No se encontro el boton Enviar de WhatsApp.")


def _click_bottom_right_send_button(page: Page) -> bool:
    viewport = page.viewport_size or {"width": 0, "height": 0}
    if not viewport["width"] or not viewport["height"]:
        return False
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-before-coordinate-send")
    page.mouse.click(viewport["width"] - 48, viewport["height"] - 50)
    return True


def _send_plain_text_message(
    page: Page,
    text: str,
    *,
    evidence_prefix: str = "whatsapp-followup",
) -> bool:
    deadline = time.monotonic() + 15
    composer = None
    while time.monotonic() < deadline:
        candidate = page.locator("footer div[contenteditable='true']").last
        if candidate.count() and candidate.is_visible():
            composer = candidate
            break
        candidate = page.locator("div[data-testid='conversation-compose-box-input']").last
        if candidate.count() and candidate.is_visible():
            composer = candidate
            break
        page.wait_for_timeout(500)
    if composer is None:
        _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-text-composer-missing")
        raise RuntimeError("No se encontro el campo para enviar el mensaje de texto.")
    logger.info("WhatsApp Web chat ready; preparing text message")
    _click_and_replace_text(page, composer, text)
    page.wait_for_timeout(500)
    if not _plain_text_ready(page, text):
        _paste_text_message(page, composer, text)
        page.wait_for_timeout(500)
    if not _plain_text_ready(page, text):
        _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-text-not-ready")
        raise RuntimeError("WhatsApp no dejo listo el mensaje de texto.")
    outgoing_signatures = _outgoing_message_signatures(page)
    _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-before-text-send")
    if not _click_visible_send_button(page):
        page.keyboard.press("Enter")
    if not _wait_until_plain_text_send_finishes(page, text, outgoing_signatures):
        _save_whatsapp_debug_screenshot(
            page,
            f"{evidence_prefix}-text-confirmation-final-check",
        )
        if not _plain_text_send_is_confirmed(page, text, outgoing_signatures):
            _save_whatsapp_debug_screenshot(
                page,
                f"{evidence_prefix}-text-send-uncertain",
            )
            return False
    _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-text-sent")
    logger.info("WhatsApp Web follow-up text message sent")
    return True


def _click_and_replace_text(page: Page, editor, text: str) -> None:
    box = editor.bounding_box()
    if box:
        page.mouse.click(box["x"] + min(40, box["width"] / 2), box["y"] + box["height"] / 2)
    else:
        editor.click(timeout=2_000, force=True)
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(text)


def _paste_text_message(page: Page, editor, text: str) -> None:
    try:
        page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://web.whatsapp.com",
        )
        page.evaluate("value => navigator.clipboard.writeText(value)", text)
        box = editor.bounding_box()
        if box:
            page.mouse.click(box["x"] + min(40, box["width"] / 2), box["y"] + box["height"] / 2)
        else:
            editor.click(timeout=2_000, force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Control+V")
    except PlaywrightError:
        logger.info("Could not paste follow-up text via clipboard")


def _click_visible_send_button(page: Page) -> bool:
    selectors = (
        "button[aria-label*='Enviar' i]",
        "button[aria-label*='Send' i]",
        "[role='button'][aria-label*='Enviar' i]",
        "[role='button'][aria-label*='Send' i]",
        "button:has(span[data-icon*='send' i])",
        "[role='button']:has(span[data-icon*='send' i])",
        "span[data-icon*='send' i]",
    )
    for selector in selectors:
        locator = page.locator(selector).last
        if not locator.count() or not locator.is_visible():
            continue
        target = locator
        button = locator.locator("xpath=ancestor::button[1]")
        role_button = locator.locator("xpath=ancestor::*[@role='button'][1]")
        if button.count():
            target = button.first
        elif role_button.count():
            target = role_button.first
        target.click(timeout=2_000, force=True)
        return True
    return _click_bottom_right_send_button(page)


def _fresh_whatsapp_page(context: BrowserContext) -> Page:
    page = context.new_page()
    for existing in list(context.pages):
        if existing == page:
            continue
        try:
            existing.close()
        except PlaywrightError:
            pass
    return page


def _close_context(context: BrowserContext | None) -> None:
    if context is not None:
        try:
            context.close()
        except PlaywrightError:
            pass
    return None
