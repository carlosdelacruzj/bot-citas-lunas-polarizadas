from __future__ import annotations

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(".runtime/whatsapp-web-profile")
COMMAND_TIMEOUT_SECONDS = 75
CHAT_READY_TIMEOUT_SECONDS = 20


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
        with sync_playwright() as playwright:
            while True:
                command = self._commands.get()
                try:
                    context = _ensure_context(playwright, context)
                    result = _prepare_draft(context, command.draft)
                except PlaywrightError as exc:
                    if _is_closed_target_error(exc):
                        logger.warning(
                            "WhatsApp Web window closed while preparing draft; reopening once"
                        )
                        context = _close_context(context)
                        try:
                            context = _ensure_context(playwright, context)
                            result = _prepare_draft(context, command.draft)
                        except PlaywrightError as retry_exc:
                            logger.exception(
                                "Could not prepare WhatsApp Web draft after reopening"
                            )
                            context = _close_context(context)
                            result = _result(
                                "web_unavailable",
                                f"No se pudo preparar WhatsApp Web: {retry_exc}",
                            )
                    else:
                        logger.exception("Could not prepare WhatsApp Web draft")
                        context = _close_context(context)
                        result = _result(
                            "web_unavailable",
                            f"No se pudo preparar WhatsApp Web: {exc}",
                        )
                except Exception as exc:
                    logger.exception("Could not prepare WhatsApp Web draft")
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


def prepare_whatsapp_web_album(
    confirmation_draft: dict[str, object],
    payment_draft: dict[str, object],
) -> dict[str, object]:
    album_draft = {
        **confirmation_draft,
        "album_items": [confirmation_draft, payment_draft],
    }
    return _MANAGER.prepare(album_draft)


def _ensure_context(playwright, context: BrowserContext | None) -> BrowserContext:
    if context is not None:
        try:
            if context.pages:
                return context
        except PlaywrightError:
            context = _close_context(context)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR.resolve()),
        headless=False,
        viewport=None,
        args=["--start-maximized"],
    )


def _prepare_draft(context: BrowserContext, draft: dict[str, object]) -> dict[str, object]:
    if draft.get("album_items"):
        return _prepare_album(context, draft)
    page = context.pages[0] if context.pages else context.new_page()
    phone = "".join(character for character in str(draft["recipient_phone"]) if character.isdigit())
    message_id = str(draft["message_id"])
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)

    if not _wait_for_chat(page):
        return _result(
            "login_required",
            "Escanea el QR en la ventana de WhatsApp Web y vuelve a pulsar Preparar borrador.",
            message_id=message_id,
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
    page = context.pages[0] if context.pages else context.new_page()
    phone = "".join(
        character
        for character in str(draft["recipient_phone"])
        if character.isdigit()
    )
    target = f"https://web.whatsapp.com/send?phone={phone}"
    page.goto(target, wait_until="domcontentloaded", timeout=45_000)
    if not _wait_for_chat(page):
        return _result(
            "login_required",
            "Escanea el QR en la ventana de WhatsApp Web y vuelve a preparar el album.",
            message_id=str(draft["message_id"]),
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
    for thumbnail, caption in zip(thumbnails, captions, strict=True):
        thumbnail.locator("img").first.click()
        page.wait_for_timeout(300)
        _fill_selected_album_caption(page, caption)
    for thumbnail, caption in zip(thumbnails, captions, strict=True):
        thumbnail.locator("img").first.click()
        page.wait_for_timeout(250)
        editor = _caption_editor(page)
        if editor is None or not _same_editor_text(editor.text_content(), caption):
            raise RuntimeError("No se pudo verificar el texto individual de cada imagen.")
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
        "Las dos imagenes tienen su propio texto. Revisa el album y pulsa Enviar una sola vez.",
        message_id=str(draft["message_id"]),
        draft_mode="album",
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


def _fill_selected_album_caption(page: Page, caption: str) -> None:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        editor = _caption_editor(page)
        if editor is not None:
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(caption)
            page.wait_for_timeout(300)
            if _same_editor_text(editor.text_content(), caption):
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
        if _visible(page, "canvas") or _visible(page, "div[data-ref]"):
            return False
        page.wait_for_timeout(500)
    return _visible(page, "div[data-testid='conversation-compose-box-input']")


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
            for selector in (
                "footer [role='button'][aria-label*='Attach' i]",
                "footer [role='button'][aria-label*='Adjuntar' i]",
                "footer button[aria-label*='Attach' i]",
                "footer button[aria-label*='Adjuntar' i]",
                "footer [title*='Attach' i]",
                "footer [title*='Adjuntar' i]",
                "footer span[data-icon='plus-rounded']",
                "footer span[data-icon='plus']",
                "footer span[data-icon='clip']",
            ):
                locator = page.locator(selector).first
                if locator.count() and locator.is_visible():
                    locator.click()
                    attachment_opened = True
                    break
        elif attachment_opened:
            media_option = page.get_by_text(
                re.compile(r"^(Fotos y videos|Photos and videos|Photos & videos)$", re.I)
            ).first
            if media_option.count() and media_option.is_visible():
                container = media_option.locator("xpath=ancestor::*[@role='button'][1]")
                option_input = container.locator("input[type='file']")
                if option_input.count():
                    option_input.first.set_input_files(files)
                    page.wait_for_timeout(1_000)
                    return
                try:
                    with page.expect_file_chooser(timeout=3_000) as chooser_info:
                        (container if container.count() else media_option).click()
                    chooser_info.value.set_files(files)
                    page.wait_for_timeout(1_000)
                    return
                except PlaywrightError:
                    logger.info("Fotos y videos did not open a file chooser")
            logger.info("WhatsApp Web attachment menu: %s", _attachment_menu_summary(page))
            file_input = _image_file_input(page)
        page.wait_for_timeout(400)
    if file_input is None:
        logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
        raise RuntimeError("No se encontro el control para adjuntar imagenes en WhatsApp Web.")
    file_input.set_input_files(files)
    page.wait_for_timeout(1_000)


def _image_file_input(page: Page):
    inputs = page.locator("input[type='file']")
    for index in range(inputs.count() - 1, -1, -1):
        locator = inputs.nth(index)
        accept = (locator.get_attribute("accept") or "").casefold()
        if "image" in accept and "video" in accept:
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
        summary.append(
            {
                "index": index,
                "accept": locator.get_attribute("accept"),
                "multiple": locator.get_attribute("multiple"),
                "label": (label.inner_text() if label.count() else "")[:80],
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
        summary.append(
            {
                "text": control.inner_text()[:80],
                "aria_label": control.get_attribute("aria-label"),
                "inputs": _file_input_summary_from(control),
            }
        )
    return summary


def _file_input_summary_from(root) -> list[str | None]:
    inputs = root.locator("input[type='file']")
    return [inputs.nth(index).get_attribute("accept") for index in range(inputs.count())]


def _fill_caption(page: Page, caption: str) -> str:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        editor = _caption_editor(page)
        if editor is not None:
            editor.click()
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(caption)
            page.wait_for_timeout(300)
            if _same_editor_text(editor.text_content(), caption):
                return "caption"
        page.wait_for_timeout(400)
    composer = page.locator("div[data-testid='conversation-compose-box-input']").first
    if composer.count() and composer.is_visible():
        composer.evaluate("element => element.focus()")
        page.keyboard.press("Control+A")
        page.keyboard.insert_text(caption)
        page.wait_for_timeout(300)
        if _same_editor_text(composer.text_content(), caption):
            return "queued_text"
    debug_screenshot = Path(".runtime/whatsapp-caption-field-missing.png").resolve()
    debug_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(debug_screenshot))
    logger.info("WhatsApp Web caption editors: %s", _caption_editor_summary(page))
    raise RuntimeError("La imagen se adjunto, pero no se encontro el campo para el texto.")


def _caption_editor(page: Page):
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
        if in_footer:
            score -= 50
        candidates.append((score, index, editor))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2] if candidates[0][0] > 0 else None


def _same_editor_text(actual: str | None, expected: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.replace("\u200b", "").split())

    actual_normalized = normalize(actual or "")
    expected_normalized = normalize(expected)
    return actual_normalized == expected_normalized or len(actual_normalized) >= max(
        20,
        len(expected_normalized) // 2,
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
                "aria_label": control.get_attribute("aria-label"),
                "title": control.get_attribute("title"),
                "data_testid": control.get_attribute("data-testid"),
                "data_icon": control.get_attribute("data-icon"),
                "icons": [
                    icons.nth(icon_index).get_attribute("data-icon")
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
) -> dict[str, Any]:
    result = {
        "status": status,
        "message": message,
        "message_id": message_id,
        "manual_send_required": True,
        "sent": False,
    }
    if draft_mode is not None:
        result["draft_mode"] = draft_mode
    return result
