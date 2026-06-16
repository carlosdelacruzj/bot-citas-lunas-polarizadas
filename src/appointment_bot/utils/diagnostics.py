import logging
from datetime import datetime

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.utils.sanitization import sanitize_text, sanitize_url

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 20_000


def save_unknown_result_diagnostic(
    page: Page, settings: Settings, *, label: str = "unknown"
) -> None:
    settings.diagnostics_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    path = settings.diagnostics_dir / filename

    try:
        body_text = page.locator("body").inner_text(timeout=15_000)
        content = sanitize_text(body_text[:MAX_TEXT_LENGTH])
        path.write_text(
            f"URL: {sanitize_url(page.url)}\nTitle: {sanitize_text(page.title())}\n\n{content}\n",
            encoding="utf-8",
        )
        logger.info("Saved diagnostic dump: %s", path)
    except (OSError, PlaywrightError) as exc:
        logger.warning("Could not save diagnostic dump %s: %s", path, exc)
