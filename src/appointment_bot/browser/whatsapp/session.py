from __future__ import annotations

import time

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.whatsapp.common import (
    CHAT_READY_TIMEOUT_SECONDS,
    PROFILE_DIR,
    _result,
    logger,
)
from appointment_bot.browser.whatsapp.dom import _normal_chat_composer_visible, _visible
from appointment_bot.browser.whatsapp.evidence import (
    _save_whatsapp_debug_screenshot,
    _whatsapp_qr_image_data_url,
)

_HEADLESS_WHATSAPP_USER_AGENT: str | None = None


def _is_closed_target_error(exc: PlaywrightError) -> bool:
    message = str(exc).casefold()
    return exc.__class__.__name__ == "TargetClosedError" or (
        "target" in message and "has been closed" in message
    )


def _ensure_context(
    playwright,
    context: BrowserContext | None,
    *,
    headless: bool = False,
) -> BrowserContext:
    if context is not None:
        try:
            if context.pages:
                return context
        except PlaywrightError:
            context = _close_context(context)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context_options: dict[str, object] = {
        "headless": headless,
        "viewport": {"width": 1440, "height": 1000} if headless else None,
        "args": [] if headless else ["--start-maximized"],
    }
    if headless:
        context_options["user_agent"] = _headless_whatsapp_user_agent(playwright)
    return playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR.resolve()),
        **context_options,
    )


def _headless_whatsapp_user_agent(playwright) -> str:
    global _HEADLESS_WHATSAPP_USER_AGENT
    if _HEADLESS_WHATSAPP_USER_AGENT is not None:
        return _HEADLESS_WHATSAPP_USER_AGENT
    browser = playwright.chromium.launch(headless=True)
    try:
        page = browser.new_page()
        user_agent = str(page.evaluate("navigator.userAgent"))
    finally:
        browser.close()
    _HEADLESS_WHATSAPP_USER_AGENT = user_agent.replace(
        "HeadlessChrome/",
        "Chrome/",
    )
    return _HEADLESS_WHATSAPP_USER_AGENT


def _validate_whatsapp_session(context: BrowserContext) -> dict[str, object]:
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(
        "https://web.whatsapp.com/",
        wait_until="domcontentloaded",
        timeout=45_000,
    )
    deadline = time.monotonic() + CHAT_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if _whatsapp_session_ready(page):
            logger.info("WhatsApp Web headless session validated")
            return _result(
                "session_ready",
                "WhatsApp esta vinculado y listo para envios automaticos.",
                manual_send_required=False,
            )
        qr_image_data_url = _whatsapp_qr_image_data_url(page)
        if qr_image_data_url is not None:
            return _result(
                "login_required",
                "Escanea el QR y luego pulsa Comprobar vinculacion.",
                qr_image_data_url=qr_image_data_url,
            )
        page.wait_for_timeout(500)
    _save_whatsapp_debug_screenshot(page, "whatsapp-session-validation-timeout")
    return _result(
        "web_unavailable",
        "WhatsApp no termino de cargar la sesion ni mostro un QR.",
    )


def _whatsapp_session_ready(page: Page) -> bool:
    if _normal_chat_composer_visible(page):
        return True
    return any(
        _visible(page, selector)
        for selector in (
            "#pane-side",
            "[data-testid='chat-list']",
            "[aria-label='Chat list']",
            "[aria-label='Lista de chats']",
        )
    )


def _fresh_whatsapp_page(context: BrowserContext) -> Page:
    page = context.new_page()
    for existing in list(context.pages):
        if existing == page:
            continue
        try:
            existing.close()
        except PlaywrightError:
            pass
    return page


def _close_context(context: BrowserContext | None) -> None:
    if context is not None:
        try:
            context.close()
        except PlaywrightError:
            pass
    return None
