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
    _document_file_input,
    _file_input_summary,
    _image_file_input,
)
from appointment_bot.browser.whatsapp.evidence import _save_whatsapp_debug_screenshot
from appointment_bot.browser.whatsapp.navigation import _wait_for_chat


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
