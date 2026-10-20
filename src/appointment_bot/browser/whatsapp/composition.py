from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import logger
from appointment_bot.browser.whatsapp.dom import (
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
) -> str:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        editor = _caption_editor(page, allow_footer_editor=allow_footer_editor)
        if editor is not None:
            _click_and_replace_text(page, editor, caption)
            page.wait_for_timeout(300)
            if _same_editor_text(
                _safe_text_content(editor),
                caption,
                require_full_match=require_full_match,
            ):
                return "caption"
        page.wait_for_timeout(400)
    _save_whatsapp_debug_screenshot(page, "whatsapp-caption-field-missing")
    logger.info("WhatsApp Web caption editors: %s", _caption_editor_summary(page))
    raise RuntimeError(
        "El adjunto no tiene una descripcion completa verificada. Revisa la vista previa."
    )


def _click_and_replace_text(page: Page, editor, text: str) -> None:
    editor.click(timeout=2_000)
    page.keyboard.press("Control+A")
    page.keyboard.insert_text(text)


def _paste_text_message(page: Page, editor, text: str) -> None:
    try:
        page.context.grant_permissions(
            ["clipboard-read", "clipboard-write"],
            origin="https://web.whatsapp.com",
        )
        page.evaluate("value => navigator.clipboard.writeText(value)", text)
        editor.click(timeout=2_000)
        page.keyboard.press("Control+A")
        page.keyboard.press("Control+V")
    except PlaywrightError:
        logger.info("Could not paste follow-up text via clipboard")
