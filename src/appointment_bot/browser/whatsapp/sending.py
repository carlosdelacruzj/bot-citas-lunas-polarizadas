from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import logger
from appointment_bot.browser.whatsapp.composition import (
    _click_and_replace_text,
    _paste_text_message,
)
from appointment_bot.browser.whatsapp.confirmation import (
    _outgoing_message_signatures,
    _plain_text_send_is_confirmed,
    _wait_until_plain_text_send_finishes,
    _wait_until_send_attempt_finishes,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_preview_visible,
    _document_preview_visible,
    _plain_text_ready,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot


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
