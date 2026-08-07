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
    pass


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
                            logger.exception(
                                "Could not prepare WhatsApp Web draft after reopening"
                            )
                            context = _close_context(context)
                            context_headless = None
                            result = _result(
                                "web_unavailable",
                                f"No se pudo preparar WhatsApp Web: {retry_exc}",
                            )
                    else:
                        logger.exception("Could not prepare WhatsApp Web draft")
                        context = _close_context(context)
                        context_headless = None
                        result = _result(
                            "web_unavailable",
                            f"No se pudo preparar WhatsApp Web: {exc}",
                        )
                except Exception as exc:
                    logger.exception("Could not prepare WhatsApp Web draft")
                    if command.draft.get("close_on_error"):
                        context = _close_context(context)
                        context_headless = None
                    result = _result(
                        "web_unavailable",
                        f"No se pudo preparar WhatsApp Web: {exc}",
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
    recipient_phone: str,
    message_text: str,
) -> dict[str, object]:
    return _MANAGER.prepare(
        {
            "action": "registration_notice",
            "message_id": message_id,
            "recipient_phone": recipient_phone,
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
    if draft.get("album_items"):
        return _prepare_album(context, draft)
    if draft.get("document_items"):
        return _prepare_documents(context, draft)
    page = context.pages[0] if context.pages else context.new_page()
    phone = "".join(character for character in str(draft["recipient_phone"]) if character.isdigit())
    message_id = str(draft["message_id"])
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)

    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name="whatsapp-confirmation-chat-not-ready",
        )

    attachment = Path(str(draft["attachment_path"])).resolve()
    if not attachment.is_file():
        raise FileNotFoundError("La constancia preparada ya no esta disponible.")
    try:
        _attach_image(page, attachment)
    except RuntimeError as exc:
        if "control para adjuntar" not in str(exc):
            raise
        page.goto(target, wait_until="domcontentloaded", timeout=45_000)
        if not _wait_for_chat(page):
            raise RuntimeError("El chat no termino de cargar para adjuntar la imagen.") from exc
        _attach_image(page, attachment)
    draft_mode = _fill_caption(page, str(draft["caption"]))
    if draft_mode == "queued_text":
        page.goto(target, wait_until="domcontentloaded", timeout=45_000)
        if not _wait_for_chat(page):
            raise RuntimeError("El chat no termino de cargar para reintentar el texto.")
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
    page = _fresh_whatsapp_page(context)
    phone = "".join(
        character
        for character in str(draft["recipient_phone"])
        if character.isdigit()
    )
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=str(draft["message_id"]),
            screenshot_name="whatsapp-album-chat-not-ready",
        )
    attachments = [Path(str(item["attachment_path"])).resolve() for item in items]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Una de las imagenes preparadas ya no esta disponible.")
    _attach_image(page, attachments)
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
            )
        _save_whatsapp_debug_screenshot(page, "whatsapp-album-sent")
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


def _prepare_documents(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    page = _fresh_whatsapp_page(context)
    phone = "".join(
        character
        for character in str(draft["recipient_phone"])
        if character.isdigit()
    )
    message_id = str(draft["message_id"])
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name="whatsapp-followup-chat-not-ready",
        )
    attachments = [Path(str(item)).resolve() for item in draft["document_items"]]
    if not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Uno de los PDFs preparados ya no esta disponible.")
    _attach_document(page, attachments)
    if draft.get("auto_send"):
        _click_send_button(page, attachments)
        text_sent = _send_plain_text_message(page, str(draft["caption"]))
        context.close()
        if not text_sent:
            logger.warning(
                "WhatsApp Web follow-up documents were sent but the text message "
                "was not confirmed: message_id=%s",
                message_id,
            )
            return _result(
                "send_uncertain",
                (
                    "Los PDFs salieron, pero WhatsApp no confirmo el texto post-pago. "
                    "No se marcara el paquete completo como enviado ni se reintentara "
                    "automaticamente."
                ),
                message_id=message_id,
                draft_mode="documents",
                manual_send_required=True,
            )
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
    outgoing_image_count = len(_outgoing_image_message_states(page))
    viewport = page.viewport_size or {"width": 0, "height": 0}
    if not viewport["width"] or not viewport["height"]:
        raise RuntimeError("WhatsApp no informo el tamaño de la ventana para enviar el album.")
    candidates = page.locator("button, [role='button']")
    bottom_right_target = None
    bottom_right_score = -1.0
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible():
            continue
        box = candidate.bounding_box()
        if not box:
            continue
        center_x = box["x"] + box["width"] / 2
        center_y = box["y"] + box["height"] / 2
        if (
            center_x < viewport["width"] * 0.75
            or center_y < viewport["height"] * 0.70
            or not 36 <= box["width"] <= 100
            or not 36 <= box["height"] <= 100
        ):
            continue
        score = center_x + center_y
        if score > bottom_right_score:
            bottom_right_target = candidate
            bottom_right_score = score
    if bottom_right_target is not None:
        bottom_right_target.click(timeout=2_000, force=True)
    else:
        page.mouse.click(viewport["width"] - 48, viewport["height"] - 50)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not _album_thumbnails(page) and _normal_chat_composer_visible(page):
            page.wait_for_timeout(1_000)
            if not _album_thumbnails(page):
                if not _wait_until_outgoing_images_uploaded(
                    page,
                    initial_count=outgoing_image_count,
                    expected_count=expected_count,
                ):
                    _save_whatsapp_debug_screenshot(
                        page,
                        uncertain_screenshot_name,
                    )
                    raise WhatsAppSendUncertain(
                        "WhatsApp cerro la vista previa, pero no confirmo "
                        "la carga de todas las imagenes."
                    )
                return
        page.wait_for_timeout(500)
    _save_whatsapp_debug_screenshot(page, "whatsapp-album-send-not-confirmed")
    raise RuntimeError(
        "WhatsApp no confirmo el envio del album; las miniaturas continuaron visibles."
    )


def _wait_until_outgoing_images_uploaded(
    page: Page,
    *,
    initial_count: int,
    expected_count: int,
) -> bool:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        states = _outgoing_image_message_states(page)
        required_count = initial_count + expected_count
        if len(states) < required_count:
            page.wait_for_timeout(500)
            continue
        batch_states = states[initial_count:required_count]
        if all(state == "confirmed" for state in batch_states):
            page.wait_for_timeout(1_000)
            return True
        page.wait_for_timeout(500)
    return False


def _outgoing_image_message_states(page: Page) -> list[str]:
    messages = page.locator("div.message-out")
    require_marker = False
    if not messages.count():
        messages = page.locator("[data-testid='msg-container']")
        require_marker = True

    states: list[str] = []
    for index in range(messages.count()):
        message = messages.nth(index)
        if require_marker and not _message_container_is_outgoing(message):
            continue
        if not _message_container_has_large_image(message):
            continue
        if message.locator(
            "[data-icon='msg-check'], [data-icon='msg-dblcheck'], "
            "[aria-label*='Enviado' i], [aria-label*='Entregado' i], "
            "[aria-label*='Leído' i], [aria-label*='Sent' i], "
            "[aria-label*='Delivered' i], [aria-label*='Read' i]"
        ).count():
            states.append("confirmed")
        elif message.locator("[data-icon='msg-time']").count():
            states.append("pending")
        else:
            states.append("unknown")
    return states


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

    message_text = str(draft["message_text"])
    if message_text:
        text_sent = _send_plain_text_message(page, message_text)
        if not text_sent:
            context.close()
            return _result(
                "send_uncertain",
                "WhatsApp no confirmo el mensaje del resumen diario.",
                message_id=message_id,
            )

    attachments = [
        Path(str(path)).resolve()
        for path in list(draft.get("attachment_paths") or [])
    ]
    if attachments:
        if not all(path.is_file() for path in attachments):
            raise FileNotFoundError(
                "Una de las imagenes del resumen diario ya no esta disponible."
            )

        _attach_image(page, attachments)
        page.wait_for_timeout(1_000)
        if len(_album_thumbnails(page)) != len(attachments):
            _save_whatsapp_debug_screenshot(
                page,
                "whatsapp-daily-summary-images-not-ready",
            )
            raise RuntimeError(
                "WhatsApp no mostro todas las imagenes del resumen diario."
            )
        _save_whatsapp_debug_screenshot(page, "whatsapp-daily-summary-before-send")
        try:
            _send_album(
                page,
                expected_count=len(attachments),
                uncertain_screenshot_name=(
                    f"whatsapp-daily-summary-upload-uncertain-{evidence_id}"
                ),
            )
        except WhatsAppSendUncertain as exc:
            context.close()
            return _result(
                "send_uncertain",
                str(exc),
                message_id=message_id,
            )
        _save_whatsapp_debug_screenshot(page, "whatsapp-daily-summary-images-sent")

    publication_sent = _send_plain_text_message(
        page,
        str(draft["publication_text"]),
    )
    if not publication_sent:
        context.close()
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo la publicacion diaria para TikTok.",
            message_id=message_id,
        )
    _save_whatsapp_debug_screenshot(page, "whatsapp-daily-summary-sent")
    context.close()
    return _result(
        "sent",
        (
            "Resumen diario, imagenes y publicacion de TikTok "
            "enviados automaticamente."
        ),
        message_id=message_id,
        sent=True,
    )


def _send_registration_notice(
    context: BrowserContext,
    draft: dict[str, object],
) -> dict[str, object]:
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
            screenshot_name="whatsapp-registration-notice-chat-not-ready",
        )
    if not _send_plain_text_message(page, str(draft["message_text"])):
        context.close()
        return _result(
            "send_uncertain",
            "WhatsApp no confirmo el aviso automatico de registro.",
            message_id=message_id,
        )
    _save_whatsapp_debug_screenshot(
        page,
        f"whatsapp-registration-notice-sent-{evidence_id}",
    )
    context.close()
    return _result(
        "sent",
        "Aviso automatico de registro enviado.",
        message_id=message_id,
        sent=True,
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
    deadline = time.monotonic() + 10
    file_input = None
    attachment_opened = False
    while time.monotonic() < deadline and file_input is None:
        if not attachment_opened:
            if _click_attachment_button(page):
                attachment_opened = True
                _wait_for_attachment_menu(page)
        elif attachment_opened:
            media_option = page.get_by_text(
                re.compile(r"^(Fotos y v.deos|Photos and videos|Photos & videos)$", re.I)
            ).last
            if media_option.count() and media_option.is_visible():
                container = _attachment_option_container(media_option)
                option_input = container.locator("input[type='file']")
                if option_input.count():
                    try:
                        option_input.first.set_input_files(files)
                        page.wait_for_timeout(1_000)
                        return
                    except PlaywrightError:
                        logger.info("Fotos y videos input did not accept the selected files")
                try:
                    with page.expect_file_chooser(timeout=3_000) as chooser_info:
                        container.click()
                    chooser_info.value.set_files(files)
                    page.wait_for_timeout(1_000)
                    return
                except PlaywrightError:
                    logger.info("Fotos y videos did not open a file chooser")
            logger.info("WhatsApp Web attachment menu: %s", _attachment_menu_summary(page))
            file_input = _image_file_input(page, require_multiple=len(files) > 1)
            if file_input is None:
                attachment_opened = False
        page.wait_for_timeout(400)
    if file_input is None:
        logger.info("WhatsApp Web file inputs: %s", _file_input_summary(page))
        logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
        raise RuntimeError("No se encontro el control para adjuntar imagenes en WhatsApp Web.")
    file_input.set_input_files(files)
    page.wait_for_timeout(1_000)


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


def _click_send_button(page: Page, attachments: list[Path]) -> None:
    if _document_preview_visible(page, [attachment.name for attachment in attachments]):
        for _ in range(2):
            if _click_bottom_right_send_button(page):
                try:
                    _wait_until_send_attempt_finishes(page)
                    return
                except RuntimeError:
                    page.wait_for_timeout(800)
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
            _wait_until_send_attempt_finishes(page)
            return
        page.wait_for_timeout(500)
    if _click_bottom_right_send_button(page):
        _wait_until_send_attempt_finishes(page)
        return
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-send-button-missing")
    raise RuntimeError("No se encontro el boton Enviar de WhatsApp.")


def _click_bottom_right_send_button(page: Page) -> bool:
    viewport = page.viewport_size or {"width": 0, "height": 0}
    if not viewport["width"] or not viewport["height"]:
        return False
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-before-coordinate-send")
    page.mouse.click(viewport["width"] - 48, viewport["height"] - 50)
    return True


def _send_plain_text_message(page: Page, text: str) -> bool:
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
        _save_whatsapp_debug_screenshot(page, "whatsapp-followup-text-composer-missing")
        raise RuntimeError("No se encontro el campo para enviar el mensaje de texto.")
    logger.info("WhatsApp Web chat ready; preparing text message")
    _click_and_replace_text(page, composer, text)
    page.wait_for_timeout(500)
    if not _plain_text_ready(page, text):
        _paste_text_message(page, composer, text)
        page.wait_for_timeout(500)
    if not _plain_text_ready(page, text):
        _save_whatsapp_debug_screenshot(page, "whatsapp-followup-text-not-ready")
        raise RuntimeError("WhatsApp no dejo listo el mensaje de texto.")
    outgoing_signatures = _matching_confirmed_outgoing_text_signatures(page, text)
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-before-text-send")
    if not _click_visible_send_button(page):
        page.keyboard.press("Enter")
    if not _wait_until_plain_text_send_finishes(page, text, outgoing_signatures):
        _save_whatsapp_debug_screenshot(page, "whatsapp-followup-text-send-uncertain")
        return False
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-text-sent")
    logger.info("WhatsApp Web follow-up text message sent")
    return True


def _wait_until_plain_text_send_finishes(
    page: Page,
    expected: str,
    outgoing_signatures: set[str],
) -> bool:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current_signatures = _matching_confirmed_outgoing_text_signatures(
            page,
            expected,
        )
        if (
            not _plain_text_ready(page, expected)
            and bool(current_signatures - outgoing_signatures)
        ):
            page.wait_for_timeout(750)
            return True
        page.wait_for_timeout(500)
    return False


def _matching_confirmed_outgoing_text_signatures(
    page: Page,
    expected: str,
) -> set[str]:
    selectors = (
        ("div.message-out", False),
        ("div[data-id^='true_']", False),
        ("[data-testid='msg-container']", True),
    )
    for selector, requires_outgoing_marker in selectors:
        messages = page.locator(selector)
        if not messages.count():
            continue
        matches: set[str] = set()
        for index in range(messages.count()):
            message = messages.nth(index)
            if requires_outgoing_marker and not _message_container_is_outgoing(message):
                continue
            actual = _safe_text_content(message)
            if (
                _message_contains_expected_text(actual, expected)
                and _message_container_has_confirmed_status(message)
            ):
                matches.add(_message_container_signature(message))
        return matches
    return set()


def _message_container_has_confirmed_status(message) -> bool:
    return bool(
        message.locator(
            "[data-icon='msg-check'], [data-icon='msg-dblcheck'], "
            "[aria-label*='Enviado' i], [aria-label*='Entregado' i], "
            "[aria-label*='Leído' i], [aria-label*='Sent' i], "
            "[aria-label*='Delivered' i], [aria-label*='Read' i]"
        ).count()
    )


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


def _message_contains_expected_text(actual: str, expected: str) -> bool:
    def normalize(value: str) -> str:
        comparable = re.sub(r"[^\w]+", " ", value.replace("\u200b", " "))
        return " ".join(comparable.casefold().split())

    actual_normalized = normalize(actual)
    expected_normalized = normalize(expected)
    if expected_normalized and expected_normalized in actual_normalized:
        return True
    actual_compact = _compact_alphanumeric_text(actual)
    expected_compact = _compact_alphanumeric_text(expected)
    return bool(expected_compact and expected_compact in actual_compact)


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


def _wait_until_send_attempt_finishes(page: Page) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if (
            _normal_chat_composer_visible(page)
            and not _attachment_preview_visible(page, [])
        ):
            page.wait_for_timeout(1_000)
            return
        page.wait_for_timeout(500)
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-send-not-confirmed")
    raise RuntimeError("WhatsApp no confirmo el envio; no volvio al chat normal.")


def _normal_chat_composer_visible(page: Page) -> bool:
    composer = page.locator("footer div[contenteditable='true']").last
    return bool(composer.count() and composer.is_visible())


def _document_preview_visible(page: Page, names: list[str]) -> bool:
    if page.locator("[data-icon='media-document']").count():
        return True
    for name in names:
        preview_text = page.get_by_text(name, exact=True)
        if preview_text.count() and preview_text.first.is_visible():
            return True
    return False


def _attachment_preview_visible(page: Page, names: list[str]) -> bool:
    if _document_preview_visible(page, names):
        return True
    if page.locator("[data-icon='x-alt']").count() and page.locator("[data-icon='send']").count():
        return True
    return False


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


def _save_whatsapp_debug_screenshot(page: Page, name: str) -> None:
    debug_screenshot = Path(f".runtime/{name}.png").resolve()
    debug_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(debug_screenshot))


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


def _result(
    status: str,
    message: str,
    *,
    message_id: str | None = None,
    draft_mode: str | None = None,
    manual_send_required: bool = True,
    sent: bool = False,
    qr_image_data_url: str | None = None,
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
    return result
