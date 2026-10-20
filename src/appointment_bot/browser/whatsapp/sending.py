from __future__ import annotations

import re
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
    _document_preview_visible,
    _normal_chat_composer,
    _plain_text_ready,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot
from appointment_bot.browser.whatsapp.progress import confirm_components, start_components


def _click_send_button(page: Page, attachments: list[Path], *, component_keys=None) -> bool:
    attachment_names = [attachment.name for attachment in attachments]
    outgoing_signatures = _outgoing_message_signatures(page)
    keys = component_keys or [f"document:{index}" for index in range(len(attachments))]
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if _document_preview_visible(page, attachment_names):
            _save_whatsapp_debug_screenshot(page, "whatsapp-followup-before-send")
            if _click_visible_send_button(page, component_keys=keys):
                return _wait_until_send_attempt_finishes(
                    page,
                    attachment_names=attachment_names,
                    outgoing_signatures=outgoing_signatures,
                    expected_outgoing_count=len(attachments),
                    component_keys=component_keys,
                )
        page.wait_for_timeout(500)
    _save_whatsapp_debug_screenshot(page, "whatsapp-followup-send-button-missing")
    raise RuntimeError("No se encontro el boton Enviar de la vista previa de documentos.")


def _send_plain_text_message(
    page: Page,
    text: str,
    *,
    evidence_prefix: str = "whatsapp-followup",
    component_keys: list[str] | None = None,
    confirmation_timeout_seconds: int | None = None,
    confirmation_grace_seconds: int | None = None,
) -> bool:
    deadline = time.monotonic() + 15
    composer = None
    while time.monotonic() < deadline:
        candidate = _normal_chat_composer(page)
        if candidate is not None:
            composer = candidate
            break
        page.wait_for_timeout(500)
    if composer is None:
        _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-text-composer-missing")
        raise RuntimeError("No se encontro el campo para enviar el mensaje de texto.")
    from appointment_bot.browser.whatsapp.safety import require_clear_outgoing_queue

    require_clear_outgoing_queue(page, evidence_prefix=evidence_prefix)
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
    keys = component_keys or ["message"]
    if not _click_visible_send_button(page, component_keys=keys):
        _save_whatsapp_debug_screenshot(page, f"{evidence_prefix}-send-button-missing")
        raise RuntimeError("No se encontro el boton Enviar del mensaje de texto.")
    confirmation_options = {}
    if confirmation_timeout_seconds is not None:
        confirmation_options["timeout_seconds"] = confirmation_timeout_seconds
    if confirmation_grace_seconds is not None:
        confirmation_options["grace_seconds"] = confirmation_grace_seconds
    if not _wait_until_plain_text_send_finishes(
        page, text, outgoing_signatures, **confirmation_options
    ):
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
    identifiers = (
        _outgoing_message_signatures(page, confirmed_only=True, expected_text=text)
        - outgoing_signatures
    )
    outgoing_id = next((value for value in identifiers if value.startswith("data-id:")), None)
    confirm_components(keys, outgoing_id)
    return True


def _click_visible_send_button(page: Page, *, component_keys: list[str] | None = None) -> bool:
    candidates = [
        page.get_by_role(
            "button", name=re.compile(r"^(Enviar|Send)( \d+ (seleccionados|selected))?$", re.I)
        ),
        page.locator("button, [role='button']").filter(
            has=page.locator("span[data-icon='send'], span[data-icon='wds-ic-send-filled']")
        ),
        page.locator("button, [role='button']").filter(
            has=page.locator("svg title").filter(
                has_text=re.compile(r"^(ic-send-filled|send|wds-ic-send-filled)$", re.I)
            )
        ),
    ]
    for locator in candidates:
        for index in range(locator.count() - 1, -1, -1):
            target = locator.nth(index)
            if not target.is_visible() or not target.is_enabled():
                continue
            logger.info(
                "WhatsApp sending with identified button: label=%s title=%s",
                target.get_attribute("aria-label"),
                target.get_attribute("title"),
            )
            if component_keys is not None:
                start_components(component_keys)
            target.click(timeout=3_000)
            return True
    return False
