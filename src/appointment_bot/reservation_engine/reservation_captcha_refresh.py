from __future__ import annotations

import logging
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.reservation_engine.appointments import APPOINTMENT_PANEL_SCREENSHOT_SELECTORS
from appointment_bot.reservation_engine.reservation_controls import (
    CAPTCHA_MEDIA_SELECTOR,
    RESERVATION_FIELD_SELECTOR,
)

logger = logging.getLogger(__name__)


def refresh_reservation_captcha(page: Page, settings: Settings) -> bool:
    logger.info("Refreshing reservation captcha after invalid captcha response")
    try:
        page.locator(RESERVATION_FIELD_SELECTOR).first.fill("", timeout=5_000)
    except PlaywrightError as exc:
        logger.info("Could not clear reservation captcha field before retry: %s", exc)

    for selector in APPOINTMENT_PANEL_SCREENSHOT_SELECTORS:
        panel = page.locator(selector).first
        try:
            if panel.count() == 0:
                continue
            previous_signature = _captcha_signature(panel)
            changed = _click_panel_captcha_refresh(panel)
            if not changed:
                changed = _reload_panel_captcha_images(
                    panel,
                    cache_buster="_appointment_bot_captcha_retry",
                )
            if not changed:
                logger.info("No captcha image resource was changed using selector %s", selector)
                return ensure_reservation_captcha_loaded(
                    panel,
                    timeout=settings.read_timeout_seconds * 1_000,
                )
            return wait_for_reservation_captcha_changed(
                panel,
                previous_signature=previous_signature,
                timeout=settings.read_timeout_seconds * 1_000,
            )
        except PlaywrightError as exc:
            logger.info("Could not refresh captcha with selector %s: %s", selector, exc)
    return False


def wait_for_reservation_captcha_changed(
    panel,
    *,
    previous_signature: str,
    timeout: int = 15_000,
) -> bool:
    deadline = time.monotonic() + timeout / 1_000
    while time.monotonic() < deadline:
        if ensure_reservation_captcha_loaded(panel, timeout=1_000):
            current_signature = _captcha_signature(panel)
            if current_signature and current_signature != previous_signature:
                return True
            if not previous_signature and current_signature:
                return True
        panel.page.wait_for_timeout(250)
    return False


def ensure_reservation_captcha_loaded(panel, *, timeout: int = 15_000) -> bool:
    if _wait_for_panel_captcha(panel, timeout=timeout):
        return True

    logger.warning("Reservation CAPTCHA did not load; retrying its image resource")
    reloaded = _reload_panel_captcha_images(panel, cache_buster="_appointment_bot_retry")
    if not reloaded:
        return False
    return _wait_for_panel_captcha(panel, timeout=timeout)


def _captcha_signature(panel) -> str:
    try:
        return str(
            panel.locator(CAPTCHA_MEDIA_SELECTOR).evaluate_all(
                """elements => elements
                    .map(element => {
                        const rect = element.getBoundingClientRect();
                        if (rect.width < 40 || rect.height < 20) return "";
                        if (element.tagName === "IMG") {
                            return [
                                element.getAttribute("src") || "",
                                element.complete ? "complete" : "loading",
                                element.naturalWidth,
                                element.naturalHeight
                            ].join("|");
                        }
                        return ["canvas", rect.width, rect.height].join("|");
                    })
                    .filter(Boolean)
                    .join("||")"""
            )
        )
    except PlaywrightError:
        return ""


def _click_panel_captcha_refresh(panel) -> bool:
    return bool(
        panel.evaluate(
            """element => {
                const media = Array.from(element.querySelectorAll("img, canvas"))
                    .map(item => ({ item, rect: item.getBoundingClientRect() }))
                    .filter(item => item.rect.width >= 40 && item.rect.height >= 20)
                    .sort((left, right) => (
                        right.rect.width * right.rect.height
                    ) - (
                        left.rect.width * left.rect.height
                    ))[0];
                if (!media) return false;

                const mediaRect = media.rect;
                const controls = Array.from(
                    element.querySelectorAll(
                        "button, a, input[type='button'], input[type='image'], input[type='submit']"
                    )
                );
                const scored = controls
                    .map(control => {
                        const rect = control.getBoundingClientRect();
                        const label = [
                            control.id,
                            control.name,
                            control.value,
                            control.title,
                            control.alt,
                            control.getAttribute("aria-label"),
                            control.textContent
                        ].join(" ").toLowerCase();
                        const looksLikeRefresh = (
                            /refresh|reload|reset|captcha|actualizar|recargar|cambiar|nuevo/
                        ).test(label);
                        const nearCaptcha = rect.left >= mediaRect.right - 8
                            && Math.abs(
                                (rect.top + rect.bottom) / 2
                                - (mediaRect.top + mediaRect.bottom) / 2
                            ) <= 80;
                        return {
                            control,
                            score: (looksLikeRefresh ? 2 : 0) + (nearCaptcha ? 1 : 0),
                            area: rect.width * rect.height
                        };
                    })
                    .filter(item => item.score > 0 && item.area > 0)
                    .sort((left, right) => right.score - left.score || left.area - right.area);
                if (!scored.length) return false;
                scored[0].control.click();
                return true;
            }"""
        )
    )


def _reload_panel_captcha_images(panel, *, cache_buster: str) -> bool:
    return bool(
        panel.locator("img").evaluate_all(
            """(elements, cacheBuster) => {
                let changed = false;
                for (const image of elements) {
                    const rect = image.getBoundingClientRect();
                    if (rect.width < 40 || rect.height < 20) continue;
                    const source = image.getAttribute("src");
                    if (!source) continue;
                    const url = new URL(source, window.location.href);
                    url.searchParams.set(cacheBuster, Date.now().toString());
                    image.src = url.toString();
                    changed = true;
                }
                return changed;
            }""",
            cache_buster,
        )
    )


def _panel_has_loaded_captcha(panel) -> bool:
    return bool(
        panel.locator("img, canvas").evaluate_all(
            """elements => elements.some(element => {
                const rect = element.getBoundingClientRect();
                if (rect.width < 40 || rect.height < 20) return false;
                if (element.tagName === "IMG") {
                    return element.complete && element.naturalWidth > 0;
                }
                return true;
            })"""
        )
    )


def _wait_for_panel_captcha(panel, *, timeout: int) -> bool:
    deadline = time.monotonic() + timeout / 1_000
    while time.monotonic() < deadline:
        if _panel_has_loaded_captcha(panel):
            return True
        panel.page.wait_for_timeout(250)
    return False
