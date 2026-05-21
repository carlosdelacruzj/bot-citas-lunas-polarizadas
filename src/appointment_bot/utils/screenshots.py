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


def save_error_screenshot(page: Page, settings: Settings, label: str = "error") -> None:
    if not settings.screenshot_on_error:
        return

    save_screenshot(page, settings, label)


def save_result_screenshot(page: Page, settings: Settings, label: str) -> None:
    if not settings.screenshot_on_relevant_result:
        return

    save_screenshot(page, settings, label)
