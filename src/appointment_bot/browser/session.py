from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright

from appointment_bot.config import Settings

BLOCKED_RESOURCE_TYPES = {"font", "image", "media"}


@contextmanager
def open_page(settings: Settings) -> Iterator[Page]:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        if settings.block_heavy_assets:
            context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in BLOCKED_RESOURCE_TYPES
                    else route.continue_()
                ),
            )
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()
