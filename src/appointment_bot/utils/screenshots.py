import logging
from datetime import datetime

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)


def save_screenshot(page: Page, settings: Settings, label: str) -> None:
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    path = settings.screenshots_dir / filename
    try:
        page.screenshot(path=str(path), full_page=True)
        logger.info("Saved screenshot: %s", path)
    except PlaywrightError as exc:
        logger.warning("Could not save screenshot %s: %s", path, exc)


def save_element_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
) -> bool:
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    path = settings.screenshots_dir / filename

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue

            locator.scroll_into_view_if_needed(timeout=5_000)
            locator.screenshot(path=str(path), timeout=10_000)
            logger.info("Saved element screenshot: %s using selector %s", path, selector)
            return True
        except PlaywrightError as exc:
            logger.warning(
                "Could not save element screenshot %s with selector %s: %s",
                path,
                selector,
                exc,
            )

    return False


def save_error_screenshot(page: Page, settings: Settings, label: str = "error") -> None:
    if not settings.screenshot_on_error:
        return

    save_screenshot(page, settings, label)


def save_result_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str] | None = None,
) -> None:
    if not settings.screenshot_on_relevant_result:
        return

    if selectors and save_element_screenshot(page, settings, label, selectors):
        return

    if selectors:
        logger.warning("Could not find result element; saving full-page screenshot instead")

    save_screenshot(page, settings, label)
