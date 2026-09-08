from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import logger
from appointment_bot.browser.whatsapp.dom import (
    _attachment_preview_visible,
    _caption_editor,
    _caption_editor_summary,
    _safe_text_content,
    _same_editor_text,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot


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
