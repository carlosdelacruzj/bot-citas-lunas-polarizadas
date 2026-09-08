from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.browser.whatsapp.common import CHAT_READY_TIMEOUT_SECONDS, _result, logger
from appointment_bot.browser.whatsapp.dom import _safe_text_content, _visible
from appointment_bot.browser.whatsapp.evidence import (
    _safe_whatsapp_artifact_name,
    _save_whatsapp_debug_screenshot,
    _whatsapp_qr_image_data_url,
)


def _open_recipient_chat(
    page: Page,
    draft: dict[str, object],
    message_id: str,
    screenshot_name: str,
) -> dict[str, object] | None:
    phone = "".join(
        character
        for character in str(draft.get("recipient_phone") or "")
        if character.isdigit()
    )
    if phone:
        page.goto(
            f"https://web.whatsapp.com/send?phone={phone}",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        if _wait_for_chat(page):
            return None
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )

    username = str(draft.get("recipient_username") or "").strip()
    if not username.startswith("@"):
        return _result(
            "recipient_not_configured",
            "La orden no tiene un numero ni un usuario de WhatsApp valido.",
            message_id=message_id,
        )
    page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=45_000)
    _dismiss_whatsapp_updates_dialog(page)
    search = _visible_whatsapp_search(page)
    if search is None:
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )
    search.click()
    search.fill(username)
    page.wait_for_timeout(700)
    rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1:
        logger.info(
            "WhatsApp username search retry before send: phase=username_search_retry"
        )
        visible_dialogs = _visible_whatsapp_dialogs(page)
        if visible_dialogs:
            _dismiss_safe_whatsapp_dialog(page, visible_dialogs)
        search = _visible_whatsapp_search(page)
        if search is not None:
            search.click()
            search.fill("")
            page.wait_for_timeout(800)
            search.fill(username)
            page.wait_for_timeout(1_200)
            rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        status = "recipient_not_found" if not rows else "recipient_ambiguous"
        detail = "no aparecio" if not rows else "aparecio mas de una vez"
        return _result(
            status,
            f"El usuario {username} {detail} como chat unico en WhatsApp. No se envio nada.",
            message_id=message_id,
        )
    expected_chat_label = _whatsapp_chat_row_label(rows[0])
    if not expected_chat_label:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        return _result(
            "recipient_mismatch",
            "WhatsApp no permitio identificar el chat encontrado para "
            f"{username}. No se envio nada.",
            message_id=message_id,
        )
    click_error = _click_username_chat_result(
        page,
        username=username,
        expected_chat_label=expected_chat_label,
        row=rows[0],
        message_id=message_id,
    )
    if click_error is not None:
        return click_error
    try:
        page.locator("header[data-testid='conversation-header']").wait_for(
            state="visible", timeout=10_000
        )
    except PlaywrightError:
        pass
    header = page.locator("header[data-testid='conversation-header']")
    header_text = _safe_text_content(header).casefold() if header.count() else ""
    header_titles = [
        str(header.locator("[title]").nth(index).get_attribute("title") or "").casefold()
        for index in range(header.locator("[title]").count())
    ] if header.count() else []
    expected_label = expected_chat_label.casefold()
    if expected_label not in header_text and expected_label not in header_titles:
        _save_whatsapp_debug_screenshot(page, screenshot_name)
        return _result(
            "recipient_mismatch",
            "WhatsApp abrio un chat distinto del resultado unico para "
            f"{username}. No se envio nada.",
            message_id=message_id,
        )
    if not _wait_for_chat(page):
        return _chat_not_ready_result(
            page,
            message_id=message_id,
            screenshot_name=screenshot_name,
        )
    return None


def _visible_whatsapp_search(page: Page):
    selectors = (
        "input[aria-label='Buscar un chat o iniciar uno nuevo']",
        "input[aria-label='Search or start a new chat']",
        "[data-tab='3'][contenteditable='true']",
    )
    deadline = time.monotonic() + CHAT_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        for selector in selectors:
            locator = page.locator(selector)
            for index in range(locator.count()):
                candidate = locator.nth(index)
                if candidate.is_visible():
                    return candidate
        page.wait_for_timeout(300)
    return None


def _dismiss_whatsapp_updates_dialog(page: Page) -> None:
    dialogs = page.locator("[role='dialog']")
    for index in range(dialogs.count()):
        dialog = dialogs.nth(index)
        if not dialog.is_visible():
            continue
        text = _safe_text_content(dialog).casefold()
        if "novedades en whatsapp web" not in text and "what's new in whatsapp web" not in text:
            continue
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        return


def _click_username_chat_result(
    page: Page,
    *,
    username: str,
    expected_chat_label: str,
    row,
    message_id: str,
) -> dict[str, object] | None:
    try:
        row.click(timeout=4_000)
        return None
    except PlaywrightError as exc:
        evidence_name = (
            "whatsapp-recipient-chat-blocked-"
            f"{_safe_whatsapp_artifact_name(message_id)}"
        )
        evidence_path = _save_whatsapp_debug_screenshot(page, evidence_name)
        visible_dialogs = _visible_whatsapp_dialogs(page)
        logger.warning(
            "WhatsApp username chat click was blocked: message_id=%s dialogs=%s error=%s",
            message_id,
            len(visible_dialogs),
            exc.__class__.__name__,
        )
        if not visible_dialogs or not _dismiss_safe_whatsapp_dialog(page, visible_dialogs):
            return _result(
                "recipient_chat_blocked",
                (
                    f"WhatsApp no permitio abrir el chat unico para {username}. "
                    "No se escribio ni envio ningun mensaje."
                ),
                message_id=message_id,
                delivery_phase="chat_not_opened",
                evidence_path=evidence_path,
            )

    search = _visible_whatsapp_search(page)
    if search is None:
        return _result(
            "recipient_chat_blocked",
            (
                f"WhatsApp cerro el dialogo, pero no recupero la busqueda de {username}. "
                "No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=evidence_path,
        )
    search.click()
    search.fill(username)
    page.wait_for_timeout(700)
    rows = _wait_for_stable_username_chat_results(page)
    if len(rows) != 1 or _whatsapp_chat_row_label(rows[0]) != expected_chat_label:
        retry_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"{evidence_name}-retry-result-mismatch",
        )
        return _result(
            "recipient_mismatch",
            (
                f"WhatsApp no recupero el mismo chat unico para {username} despues "
                "de cerrar el dialogo. No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=retry_evidence_path,
        )
    try:
        rows[0].click(timeout=4_000)
    except PlaywrightError as exc:
        retry_evidence_path = _save_whatsapp_debug_screenshot(
            page,
            f"{evidence_name}-retry-failed",
        )
        logger.warning(
            "WhatsApp username chat retry failed before send: message_id=%s error=%s",
            message_id,
            exc.__class__.__name__,
        )
        return _result(
            "recipient_chat_blocked",
            (
                f"WhatsApp volvio a bloquear el chat unico para {username}. "
                "No se escribio ni envio ningun mensaje."
            ),
            message_id=message_id,
            delivery_phase="chat_not_opened",
            evidence_path=retry_evidence_path,
        )
    return None


def _wait_for_stable_username_chat_results(page: Page) -> list[Any]:
    deadline = time.monotonic() + 15
    rows: list[Any] = []
    previous_labels: tuple[str, ...] | None = None
    stable_reads = 0
    while time.monotonic() < deadline:
        rows = _visible_username_chat_result_rows(page)
        labels = tuple(_whatsapp_chat_row_label(row) for row in rows)
        stable_reads = stable_reads + 1 if labels == previous_labels else 0
        previous_labels = labels
        if rows and stable_reads >= 2:
            break
        page.wait_for_timeout(300)
    return rows


def _visible_whatsapp_dialogs(page: Page) -> list[Any]:
    dialogs = page.locator("[role='dialog'][aria-modal='true'], [role='dialog']")
    return [
        dialogs.nth(index)
        for index in range(dialogs.count())
        if dialogs.nth(index).is_visible()
    ]


def _dismiss_safe_whatsapp_dialog(page: Page, dialogs: list[Any]) -> bool:
    safe_labels = (
        "Cancelar",
        "Cancel",
        "Cerrar",
        "Close",
        "Ahora no",
        "Not now",
        "Entendido",
        "Got it",
    )
    for dialog in dialogs:
        for label in safe_labels:
            button = dialog.get_by_role("button", name=label, exact=True)
            if button.count() and button.first.is_visible():
                button.first.click(timeout=2_000)
                page.wait_for_timeout(500)
                return not _visible_whatsapp_dialogs(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    return not _visible_whatsapp_dialogs(page)


def _visible_username_chat_result_rows(page: Page) -> list[Any]:
    rows: list[Any] = []
    seen: set[str] = set()
    candidates = page.locator("[data-testid='cell-frame-container']")
    for index in range(candidates.count()):
        row = candidates.nth(index)
        if not row.is_visible() or not _row_belongs_to_chat_results(row):
            continue
        container = row.locator("xpath=ancestor::*[@role='row'][1]")
        key = str(
            container.get_attribute("data-testid")
            or row.get_attribute("data-id")
            or _whatsapp_chat_row_label(row)
        ).strip()
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def _row_belongs_to_chat_results(row) -> bool:
    container = row.locator("xpath=ancestor::*[@role='row'][1]")
    if container.count() != 1:
        return False
    section = container.locator("xpath=preceding-sibling::*[1]")
    if section.count() != 1:
        return False
    return _safe_text_content(section).strip().casefold() == "chats"


def _whatsapp_chat_row_label(row) -> str:
    titles = row.locator("span[title]")
    for index in range(titles.count()):
        title = titles.nth(index)
        value = str(title.get_attribute("title") or "").strip()
        if title.is_visible() and value:
            return value
    return ""


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
