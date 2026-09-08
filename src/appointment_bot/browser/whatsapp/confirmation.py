from __future__ import annotations

import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import (
    PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS,
    PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS,
    logger,
)
from appointment_bot.browser.whatsapp.dom import (
    _attachment_preview_visible,
    _compact_alphanumeric_text,
    _document_preview_visible,
    _locator_has_visible_match,
    _normal_chat_composer_visible,
    _plain_text_ready,
    _safe_get_attribute,
    _safe_text_content,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot


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
