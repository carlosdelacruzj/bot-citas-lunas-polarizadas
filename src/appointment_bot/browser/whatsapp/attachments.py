from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import _AttachmentBeforeFileSelectionError, logger
from appointment_bot.browser.whatsapp.dom import (
    _attachment_control_summary,
    _attachment_menu_summary,
    _attachment_menu_visible,
    _attachment_option_container,
    _file_input_summary,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot
from appointment_bot.browser.whatsapp.navigation import _wait_for_chat
from appointment_bot.browser.whatsapp.safety import require_clear_outgoing_queue


def _attach_image(page: Page, attachment: Path | list[Path]) -> None:
    require_clear_outgoing_queue(page, evidence_prefix="whatsapp-attachment")
    files = (
        [str(item) for item in attachment] if isinstance(attachment, list) else [str(attachment)]
    )
    failure_phase = "attach_control_not_found"
    file_selection_started = False
    for attempt in range(1, 3):
        if attempt == 2:
            logger.info(
                "WhatsApp image attachment safe retry before file selection: phase=%s",
                failure_phase,
            )
            if not _wait_for_chat(page):
                failure_phase = "chat_not_ready_before_attachment_retry"
                break
        if not _attachment_menu_visible(page) and not _click_attachment_button(page):
            failure_phase = "attach_control_not_found"
            continue
        if not _wait_for_attachment_menu(page):
            failure_phase = "attach_menu_not_opened"
            continue
        media_name = re.compile(r"^(Fotos y v.deos|Photos and videos|Photos & videos)$", re.I)
        candidates = [
            page.get_by_role("menuitem", name=media_name),
            page.get_by_role("button", name=media_name),
            page.get_by_text(media_name),
        ]
        target = None
        for candidates_locator in candidates:
            for index in range(candidates_locator.count()):
                candidate = candidates_locator.nth(index)
                if candidate.is_visible():
                    target = _attachment_option_container(candidate)
                    break
            if target is not None:
                break
        if target is None:
            failure_phase = "media_picker_not_ready"
            logger.info("WhatsApp Web attachment menu: %s", _attachment_menu_summary(page))
            continue
        option_input = target.locator("input[type='file']")
        if option_input.count():
            if len(files) > 1 and not option_input.first.evaluate("element => element.multiple"):
                failure_phase = "non_multiple_input"
                continue
            file_selection_started = True
            option_input.first.set_input_files(files)
        else:
            try:
                with page.expect_file_chooser(timeout=5_000) as chooser_info:
                    target.click(timeout=3_000)
            except PlaywrightError:
                failure_phase = "media_chooser_not_opened"
                continue
            chooser = chooser_info.value
            if len(files) > 1 and not chooser.is_multiple():
                failure_phase = "non_multiple_input"
                continue
            file_selection_started = True
            chooser.set_files(files)
        page.wait_for_timeout(1_000)
        return

    logger.info("WhatsApp Web file inputs: %s", _file_input_summary(page))
    logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
    error_message = (
        f"No se encontro el control para adjuntar imagenes en WhatsApp Web. Fase: {failure_phase}."
    )
    if not file_selection_started:
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
        target.click(timeout=3_000)
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
    require_clear_outgoing_queue(page, evidence_prefix="whatsapp-attachment")
    files = (
        [str(item) for item in attachment] if isinstance(attachment, list) else [str(attachment)]
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not _attachment_menu_visible(page):
            if not _click_attachment_button(page):
                page.wait_for_timeout(400)
                continue
            if not _wait_for_attachment_menu(page):
                continue
        if _choose_document_files(page, files):
            return
        page.wait_for_timeout(400)
    _save_whatsapp_debug_screenshot(page, "whatsapp-document-input-missing")
    logger.info("WhatsApp Web attachment controls: %s", _attachment_control_summary(page))
    raise RuntimeError(
        "No se encontro el control Documento para adjuntar los PDFs en WhatsApp Web."
    )


def _choose_document_files(page: Page, files: list[str]) -> bool:
    candidates = [
        page.locator(
            "[aria-label='Documento'], [aria-label='Document'], "
            "[title='Documento'], [title='Document']"
        ).last,
        page.get_by_text(re.compile(r"^(Documento|Document)$", re.I)).last,
        page.locator(
            "[role='menu'] [aria-label='Documento'], [role='menu'] [aria-label='Document']"
        ).last,
        page.locator("[role='menuitem']")
        .filter(has_text=re.compile(r"^(Documento|Document)$", re.I))
        .last,
        page.locator("[role='button']")
        .filter(has_text=re.compile(r"^(Documento|Document)$", re.I))
        .last,
        page.locator("li").filter(has_text=re.compile(r"^(Documento|Document)$", re.I)).last,
        page.locator("[tabindex='0']")
        .filter(has_text=re.compile(r"^(Documento|Document)$", re.I))
        .last,
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
                target.click(timeout=2_000)
        except PlaywrightError:
            logger.info("Documento target did not open a file chooser")
            continue
        chooser = chooser_info.value
        if len(files) > 1 and not chooser.is_multiple():
            raise RuntimeError("El selector Documento no permite adjuntar todos los PDFs juntos.")
        chooser.set_files(files)
        page.wait_for_timeout(1_000)
        return True
    return False
