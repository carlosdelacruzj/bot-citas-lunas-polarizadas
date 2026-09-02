from __future__ import annotations

import base64
import logging
import queue
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(".runtime/whatsapp-web-profile")
COMMAND_TIMEOUT_SECONDS = 180
CHAT_READY_TIMEOUT_SECONDS = 20
_HEADLESS_WHATSAPP_USER_AGENT: str | None = None


class WhatsAppSendUncertain(RuntimeError):
    def __init__(self, message: str, *, evidence_path: str | None = None) -> None:
        super().__init__(message)
        self.evidence_path = evidence_path


class _AttachmentBeforeFileSelectionError(RuntimeError):
    pass


DAILY_SUMMARY_IMAGE_BATCH_SIZE = 4
PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS = 30
PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS = 3


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


def _album_thumbnails(page: Page) -> list[Any]:
    controls = page.locator("[role='button']:has(img):has([data-icon='x-alt'])")
    thumbnails: list[Any] = []
    for index in range(controls.count()):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        box = control.bounding_box()
        if box and 48 <= box["width"] <= 96 and 48 <= box["height"] <= 96:
            thumbnails.append(control)
    return thumbnails


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


def _wait_until_outgoing_images_uploaded(
    page: Page,
    *,
    initial_signatures: set[str],
    expected_count: int,
) -> bool:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        new_records = [
            (signature, state)
            for signature, state in _outgoing_image_message_records(page)
            if signature not in initial_signatures
        ]
        if len(new_records) < expected_count:
            page.wait_for_timeout(500)
            continue
        batch_states = [state for _signature, state in new_records[-expected_count:]]
        if all(state == "confirmed" for state in batch_states):
            page.wait_for_timeout(1_000)
            return True
        page.wait_for_timeout(500)
    return False


def _outgoing_image_message_records(page: Page) -> list[tuple[str, str]]:
    messages = page.locator("div.message-out")
    require_marker = False
    if not messages.count():
        messages = page.locator("[data-testid='msg-container']")
        require_marker = True

    records: list[tuple[str, str]] = []
    for index in range(messages.count()):
        message = messages.nth(index)
        if require_marker and not _message_container_is_outgoing(message):
            continue
        if not _message_container_has_large_image(message):
            continue
        if _message_container_has_pending_status(message):
            state = "pending"
        elif _message_container_has_confirmed_status(message):
            state = "confirmed"
        else:
            state = "unknown"
        records.append((_message_container_signature(message), state))
    return records


def _message_container_has_large_image(message) -> bool:
    images = message.locator("img")
    for index in range(images.count()):
        image = images.nth(index)
        if not image.is_visible():
            continue
        box = image.bounding_box()
        if box and box["width"] >= 100 and box["height"] >= 100:
            return True
    return False


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


def _album_control_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("button, [role='button']")
    viewport = page.viewport_size or {"width": 0, "height": 0}
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 160)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        box = control.bounding_box()
        if box is None or box["y"] < viewport["height"] * 0.55:
            continue
        summary.append(
            {
                "index": index,
                "aria_label": control.get_attribute("aria-label"),
                "title": control.get_attribute("title"),
                "data_testid": control.get_attribute("data-testid"),
                "box": {key: round(value) for key, value in box.items()},
                "images": control.locator("img").count(),
                "canvases": control.locator("canvas").count(),
                "icons": [
                    control.locator("[data-icon]").nth(icon_index).get_attribute("data-icon")
                    for icon_index in range(min(control.locator("[data-icon]").count(), 3))
                ],
            }
        )
    return summary


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


def _attachment_menu_visible(page: Page) -> bool:
    media_option = page.get_by_text(
        re.compile(r"^(Fotos y v.deos|Photos and videos|Photos & videos)$", re.I)
    ).last
    if media_option.count() and media_option.is_visible():
        return True
    document_option = page.get_by_text(re.compile(r"^(Documento|Document)$", re.I)).last
    if document_option.count() and document_option.is_visible():
        return True
    document_label = page.locator(
        "[aria-label='Documento'], [aria-label='Document'], "
        "[title='Documento'], [title='Document']"
    ).last
    if document_label.count() and document_label.is_visible():
        return True
    return bool(page.locator("[role='menuitem']:visible").count())


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


def _attachment_option_container(option):
    for xpath in (
        "ancestor-or-self::*[@role='menuitem'][1]",
        "ancestor-or-self::*[@role='button'][1]",
        "ancestor-or-self::li[1]",
        "ancestor-or-self::*[@tabindex='0'][1]",
    ):
        candidate = option.locator(f"xpath={xpath}")
        if candidate.count() and candidate.first.is_visible():
            return candidate.first
    return option


def _image_file_input(page: Page, *, require_multiple: bool = False):
    inputs = page.locator("input[type='file']")
    for index in range(inputs.count() - 1, -1, -1):
        locator = inputs.nth(index)
        accept = (locator.get_attribute("accept") or "").casefold()
        allows_multiple = locator.evaluate("element => element.multiple")
        if "image" in accept and (not require_multiple or allows_multiple):
            return locator
    return None


def _document_file_input(page: Page):
    inputs = page.locator("input[type='file']")
    for index in range(inputs.count() - 1, -1, -1):
        locator = inputs.nth(index)
        accept = (locator.get_attribute("accept") or "").casefold()
        if "image" in accept or "video" in accept:
            continue
        if "pdf" in accept or "application" in accept or not accept:
            return locator
    return None


def _file_input_summary(page: Page) -> list[dict[str, object]]:
    inputs = page.locator("input[type='file']")
    summary: list[dict[str, object]] = []
    for index in range(inputs.count()):
        locator = inputs.nth(index)
        label = locator.locator("xpath=ancestor::li[1]")
        if not label.count():
            label = locator.locator("xpath=ancestor::*[@role='button'][1]")
        label_text = ""
        if label.count():
            try:
                label_text = label.inner_text(timeout=1_000)[:80]
            except PlaywrightError:
                label_text = ""
        summary.append(
            {
                "index": index,
                "accept": _safe_get_attribute(locator, "accept"),
                "multiple": _safe_get_attribute(locator, "multiple"),
                "label": label_text,
            }
        )
    return summary


def _attachment_menu_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("[role='menu'] [role='button'], [role='menuitem'], [role='menu'] li")
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 20)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        try:
            text = control.inner_text(timeout=1_000)[:80]
        except PlaywrightError:
            text = ""
        summary.append(
            {
                "text": text,
                "aria_label": _safe_get_attribute(control, "aria-label"),
                "inputs": _file_input_summary_from(control),
            }
        )
    return summary


def _file_input_summary_from(root) -> list[str | None]:
    inputs = root.locator("input[type='file']")
    return [_safe_get_attribute(inputs.nth(index), "accept") for index in range(inputs.count())]


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


def _wait_until_plain_text_send_finishes(
    page: Page,
    expected: str,
    outgoing_signatures: set[str],
) -> bool:
    deadline = time.monotonic() + PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _plain_text_send_is_confirmed(page, expected, outgoing_signatures):
            page.wait_for_timeout(750)
            return True
        page.wait_for_timeout(500)
    page.wait_for_timeout(PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS * 1_000)
    if _plain_text_send_is_confirmed(page, expected, outgoing_signatures):
        page.wait_for_timeout(750)
        return True
    return False


def _plain_text_send_is_confirmed(
    page: Page,
    expected: str,
    outgoing_signatures: set[str],
) -> bool:
    confirmed_signatures = _outgoing_message_signatures(
        page,
        confirmed_only=True,
        expected_text=expected,
    )
    return (
        not _plain_text_ready(page, expected)
        and bool(confirmed_signatures - outgoing_signatures)
    )


def _outgoing_message_signatures(
    page: Page,
    *,
    confirmed_only: bool = False,
    expected_text: str | None = None,
) -> set[str]:
    expected_compact = (
        _compact_alphanumeric_text(expected_text) if expected_text is not None else None
    )
    selectors = (
        ("div.message-out", False),
        ("div[data-id^='true_']", False),
        ("[data-testid='msg-container']", True),
    )
    signatures: set[str] = set()
    for selector, requires_outgoing_marker in selectors:
        messages = page.locator(selector)
        if not messages.count():
            continue
        for index in range(messages.count()):
            message = messages.nth(index)
            if requires_outgoing_marker and not _message_container_is_outgoing(message):
                continue
            if confirmed_only and not _message_container_has_confirmed_status(message):
                continue
            if expected_compact is not None:
                actual_text = _compact_alphanumeric_text(_safe_text_content(message))
                if not expected_compact or expected_compact not in actual_text:
                    continue
            signatures.add(_message_container_signature(message))
    return signatures


def _message_container_has_confirmed_status(message) -> bool:
    if _message_container_has_pending_status(message):
        return False
    status_markers = message.locator(
        "[data-icon='msg-check'], [data-icon='msg-dblcheck'], "
        "[data-icon^='msg-check-'], [data-icon^='msg-dblcheck-'], "
        "[data-icon*='dblcheck'], "
        "[class*='wds-ic-read'], [class*='wds-ic-delivered'], "
        "[class*='wds-ic-sent']"
    )
    if _locator_has_visible_match(status_markers):
        return True
    labels = message.locator("[aria-label]")
    confirmed_labels = {
        "enviado",
        "entregado",
        "leido",
        "sent",
        "delivered",
        "read",
    }
    for index in range(labels.count()):
        label = labels.nth(index)
        if not label.is_visible():
            continue
        value = _safe_get_attribute(label, "aria-label") or ""
        if _compact_alphanumeric_text(value) in confirmed_labels:
            return True
    return False


def _message_container_has_pending_status(message) -> bool:
    return _locator_has_visible_match(
        message.locator(
            "[data-icon='msg-time'], [data-icon^='msg-time-'], "
            "[class*='wds-ic-time']"
        )
    )


def _locator_has_visible_match(locator) -> bool:
    for index in range(locator.count()):
        try:
            if locator.nth(index).is_visible():
                return True
        except PlaywrightError:
            continue
    return False


def _message_container_signature(message) -> str:
    data_id = _safe_get_attribute(message, "data-id")
    if data_id:
        return f"data-id:{data_id}"
    ancestor = message.locator("xpath=ancestor::*[@data-id][1]")
    if ancestor.count():
        ancestor_data_id = _safe_get_attribute(ancestor.first, "data-id")
        if ancestor_data_id:
            return f"data-id:{ancestor_data_id}"
    try:
        return f"html:{message.evaluate('element => element.outerHTML')}"
    except PlaywrightError:
        return f"text:{_safe_text_content(message)}"


def _message_container_is_outgoing(message) -> bool:
    if _message_container_has_confirmed_status(message):
        return True
    labels = message.locator("[aria-label]")
    for index in range(labels.count()):
        label = (_safe_get_attribute(labels.nth(index), "aria-label") or "").strip()
        if label.casefold() in {"tú:", "tu:", "you:"}:
            return True
    metadata = _safe_text_content(message).casefold()
    return any(
        marker in metadata
        for marker in ("wds-ic-read", "wds-ic-delivered", "wds-ic-sent")
    )


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


def _plain_text_ready(page: Page, expected: str) -> bool:
    editors = page.locator(
        "footer div[contenteditable='true'], "
        "div[data-testid='conversation-compose-box-input']"
    )
    for index in range(editors.count() - 1, -1, -1):
        text = _safe_text_content(editors.nth(index))
        if _same_editor_text(text, expected, require_full_match=True) or (
            "TikTok" in text and "citaspolarizadasperu" in text
        ):
            return True
    return False


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


def _wait_until_send_attempt_finishes(
    page: Page,
    *,
    attachment_names: list[str],
    outgoing_signatures: set[str],
    expected_outgoing_count: int,
) -> bool:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        confirmed_signatures = _outgoing_message_signatures(
            page,
            confirmed_only=True,
        )
        new_confirmed_count = len(confirmed_signatures - outgoing_signatures)
        if (
            _normal_chat_composer_visible(page)
            and new_confirmed_count >= expected_outgoing_count
        ):
            page.wait_for_timeout(1_000)
            return True
        page.wait_for_timeout(500)
    evidence_path = _save_whatsapp_debug_screenshot(
        page,
        "whatsapp-followup-send-not-confirmed",
    )
    document_preview_visible = _document_preview_visible(page, attachment_names)
    preview_controls_visible = _attachment_preview_visible(page, attachment_names)
    logger.warning(
        "WhatsApp document send confirmation failed: "
        "phase=document_preview_still_open_or_unconfirmed "
        "confirmed=%s expected=%s document_preview_visible=%s "
        "preview_controls_visible=%s evidence=%s",
        new_confirmed_count,
        expected_outgoing_count,
        document_preview_visible,
        preview_controls_visible,
        evidence_path,
    )
    if not document_preview_visible and _normal_chat_composer_visible(page):
        logger.warning(
            "WhatsApp document preview closed without full confirmation; "
            "continuing with the distinct post-payment text and preserving "
            "the documents as uncertain"
        )
        return False
    raise RuntimeError(
        "WhatsApp no confirmo el envio de los documentos; la vista previa no cerro "
        "o no aparecieron todas las burbujas salientes confirmadas. "
        "Fase: document_preview_still_open_or_unconfirmed."
    )


def _normal_chat_composer_visible(page: Page) -> bool:
    composer = page.locator("div[data-testid='conversation-compose-box-input']").last
    return bool(composer.count() and composer.is_visible())


def _document_preview_visible(page: Page, names: list[str]) -> bool:
    document_icons = page.locator("[data-icon='media-document']")
    if any(document_icons.nth(index).is_visible() for index in range(document_icons.count())):
        return True
    for name in names:
        preview_text = page.get_by_text(name, exact=True)
        if any(preview_text.nth(index).is_visible() for index in range(preview_text.count())):
            return True
    return False


def _attachment_preview_visible(page: Page, names: list[str]) -> bool:
    close_icons = page.locator("[data-icon='x-alt']")
    send_icons = page.locator("[data-icon='send']")
    close_visible = any(
        close_icons.nth(index).is_visible() for index in range(close_icons.count())
    )
    send_visible = any(
        send_icons.nth(index).is_visible() for index in range(send_icons.count())
    )
    return close_visible and send_visible and _document_preview_visible(page, names)


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


def _caption_editor(page: Page, *, allow_footer_editor: bool = False):
    editors = page.locator("div[contenteditable='true']")
    candidates = []
    for index in range(editors.count()):
        editor = editors.nth(index)
        if not editor.is_visible():
            continue
        aria_label = (editor.get_attribute("aria-label") or "").casefold()
        placeholder = " ".join(
            filter(
                None,
                (
                    editor.get_attribute("data-placeholder"),
                    editor.get_attribute("aria-placeholder"),
                    editor.get_attribute("title"),
                ),
            )
        ).casefold()
        description = f"{aria_label} {placeholder}"
        score = 0
        if any(
            term in description
            for term in ("caption", "pie de foto", "comentario", "descripci")
        ):
            score += 100
        if editor.locator("xpath=ancestor::*[@role='dialog']").count():
            score += 20
        in_footer = bool(editor.locator("xpath=ancestor::footer").count())
        if not in_footer and editor.get_attribute("role") == "textbox":
            score += 40
        if in_footer and allow_footer_editor:
            score += 80
        elif in_footer:
            score -= 50
        candidates.append((score, index, editor))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2] if candidates[0][0] > 0 else None


def _same_editor_text(
    actual: str | None,
    expected: str,
    *,
    require_full_match: bool = False,
) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.replace("\u200b", "").split())

    actual_normalized = normalize(actual or "")
    expected_normalized = normalize(expected)
    if require_full_match:
        return actual_normalized == expected_normalized or (
            len(actual_normalized) >= 80
            and actual_normalized in expected_normalized
            and any(
                marker in actual_normalized
                for marker in (
                    "TikTok",
                    "citaspolarizadasperu",
                    "Gracias por confiar",
                )
            )
        ) or _compact_alphanumeric_text(actual or "") == _compact_alphanumeric_text(
            expected
        )
    return actual_normalized == expected_normalized or len(actual_normalized) >= max(
        20,
        len(expected_normalized) // 2,
    )


def _compact_alphanumeric_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character.casefold()
        for character in decomposed
        if character.isalnum()
    )


def _caption_editor_summary(page: Page) -> list[dict[str, object]]:
    editors = page.locator(
        "[contenteditable='true'], textarea, input, "
        "[aria-placeholder], [aria-label*='caption' i], "
        "[aria-label*='comentario' i], [aria-label*='descripci' i]"
    )
    summary: list[dict[str, object]] = []
    for index in range(min(editors.count(), 12)):
        editor = editors.nth(index)
        if not editor.is_visible():
            continue
        summary.append(
            {
                "aria_label": editor.get_attribute("aria-label"),
                "aria_placeholder": editor.get_attribute("aria-placeholder"),
                "data_placeholder": editor.get_attribute("data-placeholder"),
                "data_tab": editor.get_attribute("data-tab"),
                "title": editor.get_attribute("title"),
                "tag": editor.evaluate("element => element.tagName"),
                "role": editor.get_attribute("role"),
                "contenteditable": editor.get_attribute("contenteditable"),
                "in_dialog": bool(editor.locator("xpath=ancestor::*[@role='dialog']").count()),
                "in_footer": bool(editor.locator("xpath=ancestor::footer").count()),
            }
        )
    return summary


def _save_whatsapp_debug_screenshot(page: Page, name: str) -> str:
    debug_screenshot = Path(f".runtime/{name}.png").resolve()
    debug_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(debug_screenshot))
    return str(Path(".runtime") / f"{name}.png")


def _safe_whatsapp_artifact_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "message"


def _whatsapp_qr_image_data_url(page: Page) -> str | None:
    candidates = page.locator("canvas, [data-ref]")
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible():
            continue
        box = candidate.bounding_box()
        if not box or not (160 <= box["width"] <= 420 and 160 <= box["height"] <= 420):
            continue
        try:
            image_bytes = candidate.screenshot(type="png")
        except PlaywrightError:
            continue
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    return None


def _safe_get_attribute(locator, name: str) -> str | None:
    try:
        return locator.get_attribute(name, timeout=1_000)
    except PlaywrightError:
        return None


def _safe_text_content(locator) -> str:
    try:
        return locator.text_content(timeout=1_000) or ""
    except PlaywrightError:
        return ""


def _visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector).first
    return bool(locator.count() and locator.is_visible())


def _attachment_control_summary(page: Page) -> list[dict[str, object]]:
    controls = page.locator("button, [role='button'], [data-icon]")
    summary: list[dict[str, object]] = []
    for index in range(min(controls.count(), 80)):
        control = controls.nth(index)
        if not control.is_visible():
            continue
        icons = control.locator("[data-icon]")
        summary.append(
            {
                "tag": control.evaluate("element => element.tagName"),
                "aria_label": _safe_get_attribute(control, "aria-label"),
                "title": _safe_get_attribute(control, "title"),
                "data_testid": _safe_get_attribute(control, "data-testid"),
                "data_icon": _safe_get_attribute(control, "data-icon"),
                "icons": [
                    _safe_get_attribute(icons.nth(icon_index), "data-icon")
                    for icon_index in range(min(icons.count(), 4))
                ],
            }
        )
    return summary


def _close_context(context: BrowserContext | None) -> None:
    if context is not None:
        try:
            context.close()
        except PlaywrightError:
            pass
    return None


def _save_context_failure_screenshot(
    context: BrowserContext | None,
    draft: dict[str, object],
) -> str | None:
    if context is None or not context.pages:
        return None
    message_id = _safe_whatsapp_artifact_name(
        str(draft.get("message_id") or draft.get("action") or "unknown")
    )
    try:
        return _save_whatsapp_debug_screenshot(
            context.pages[-1],
            f"whatsapp-automation-error-{message_id}",
        )
    except PlaywrightError:
        return None


def _result(
    status: str,
    message: str,
    *,
    message_id: str | None = None,
    draft_mode: str | None = None,
    manual_send_required: bool = True,
    sent: bool = False,
    qr_image_data_url: str | None = None,
    delivery_phase: str | None = None,
    evidence_path: str | None = None,
    delivery_components: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = {
        "status": status,
        "message": message,
        "message_id": message_id,
        "manual_send_required": manual_send_required,
        "sent": sent,
    }
    if draft_mode is not None:
        result["draft_mode"] = draft_mode
    if qr_image_data_url is not None:
        result["qr_image_data_url"] = qr_image_data_url
    if delivery_phase is not None:
        result["delivery_phase"] = delivery_phase
    if evidence_path is not None:
        result["evidence_path"] = evidence_path
    if delivery_components is not None:
        result["delivery_components"] = dict(delivery_components)
    return result
