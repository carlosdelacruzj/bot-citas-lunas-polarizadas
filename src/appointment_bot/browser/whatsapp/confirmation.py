from __future__ import annotations

import re
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
from appointment_bot.browser.whatsapp.progress import confirm_components


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
        signature = _message_container_signature(message)
        if signature:
            records.append((signature, state))
    return records


def _message_container_has_large_image(message) -> bool:
    images = message.locator("img")
    for index in range(images.count()):
        image = images.nth(index)
        try:
            if not image.is_visible():
                continue
            box = image.bounding_box(timeout=500)
            if box and box["width"] >= 100 and box["height"] >= 100:
                return True
        except PlaywrightError:
            continue
    return False


def _wait_until_plain_text_send_finishes(
    page: Page,
    expected: str,
    outgoing_signatures: set[str],
    *,
    timeout_seconds: int = PLAIN_TEXT_CONFIRMATION_TIMEOUT_SECONDS,
    grace_seconds: int = PLAIN_TEXT_CONFIRMATION_GRACE_SECONDS,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _plain_text_send_is_confirmed(page, expected, outgoing_signatures):
            page.wait_for_timeout(750)
            return True
        page.wait_for_timeout(500)
    page.wait_for_timeout(grace_seconds * 1_000)
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
    return not _plain_text_ready(page, expected) and bool(
        confirmed_signatures - outgoing_signatures
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
                if expected_compact and expected_compact not in actual_text:
                    if _expand_matching_message_text(message, expected_compact, actual_text):
                        actual_text = _compact_alphanumeric_text(_safe_text_content(message))
                if not expected_compact or expected_compact not in actual_text:
                    continue
            signature = _message_container_signature(message)
            if signature:
                signatures.add(signature)
    return signatures


def _expand_matching_message_text(message, expected: str, actual: str) -> bool:
    if len(expected) < 80 or expected[:80] not in actual:
        return False
    controls = message.get_by_text(re.compile(r"^(Leer m\u00e1s|Leer mas|Read more)$", re.I))
    for index in range(controls.count()):
        control = controls.nth(index)
        try:
            if control.is_visible():
                control.click(timeout=1_000)
                return True
        except PlaywrightError:
            continue
    return False


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
    svg_status = message.locator("svg:has(title)").filter(
        has_text=re.compile(r"^(wds-ic-read|wds-ic-delivered|wds-ic-sent)$")
    )
    if _locator_has_visible_match(status_markers) or _locator_has_visible_match(svg_status):
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
    pending_svg = message.locator("svg:has(title)").filter(
        has_text=re.compile(r"^(wds-ic-time|wds-ic-error)$")
    )
    return _locator_has_visible_match(pending_svg) or _locator_has_visible_match(
        message.locator(
            "[data-icon='msg-time'], [data-icon^='msg-time-'], [class*='wds-ic-time'], "
            "[data-icon*='error'], [data-icon*='retry'], [data-icon*='upload'], "
            "[role='progressbar'], [class*='wds-ic-error'], "
            "[aria-label*='No se pudo enviar' i], [aria-label*='Reintentar' i], "
            "[aria-label*='Failed' i], [aria-label*='Not sent' i], [aria-label*='Retry' i]"
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
    return ""


def _message_container_is_outgoing(message) -> bool:
    if _message_container_has_confirmed_status(message):
        return True
    labels = message.locator("[aria-label]")
    for index in range(labels.count()):
        label = _safe_get_attribute(labels.nth(index), "aria-label") or ""
        if _compact_alphanumeric_text(label) in {"tu", "you"}:
            return True
    try:
        return message.evaluate("""element => !!element.closest(
            '.message-out, [data-id^="true_"]'
        )""")
    except PlaywrightError:
        return False


def _wait_until_send_attempt_finishes(
    page: Page,
    *,
    attachment_names: list[str],
    outgoing_signatures: set[str],
    expected_outgoing_count: int,
    component_keys: list[str] | None = None,
) -> bool:
    def check_documents() -> tuple[bool, int]:
        confirmed_ids: set[str] = set()
        documents_confirmed = bool(attachment_names)
        for index, name in enumerate(attachment_names):
            matches = (
                _outgoing_message_signatures(page, confirmed_only=True, expected_text=name)
                - outgoing_signatures
            )
            confirmed_ids.update(matches)
            if not matches:
                documents_confirmed = False
                continue
            if component_keys:
                outgoing_id = next(
                    (value for value in matches if value.startswith("data-id:")), None
                )
                confirm_components([component_keys[index]], outgoing_id)
        confirmed_count = len(confirmed_ids)
        return (
            documents_confirmed
            and confirmed_count >= expected_outgoing_count
            and _normal_chat_composer_visible(page),
            confirmed_count,
        )

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        documents_confirmed, new_confirmed_count = check_documents()
        if documents_confirmed:
            page.wait_for_timeout(1_000)
            return True
        page.wait_for_timeout(500)
    # DOM queries can outlast the deadline while WhatsApp finishes the upload.
    documents_confirmed, new_confirmed_count = check_documents()
    if documents_confirmed:
        page.wait_for_timeout(1_000)
        return True
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
            "stopping and preserving the documents as uncertain"
        )
        return False
    raise RuntimeError(
        "WhatsApp no confirmo el envio de los documentos; la vista previa no cerro "
        "o no aparecieron todas las burbujas salientes confirmadas. "
        "Fase: document_preview_still_open_or_unconfirmed."
    )
