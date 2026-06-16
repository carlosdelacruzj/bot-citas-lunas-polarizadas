from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import Page, sync_playwright

from appointment_bot.config import Settings

BLOCKED_RESOURCE_TYPES = {"font", "media"}


@contextmanager
def open_page(
    settings: Settings,
    *,
    headless: bool | None = None,
    block_heavy_assets: bool | None = None,
) -> Iterator[Page]:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    effective_headless = settings.headless if headless is None else headless
    effective_block_heavy_assets = (
        settings.block_heavy_assets if block_heavy_assets is None else block_heavy_assets
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=effective_headless)
        context = browser.new_context(
            device_scale_factor=settings.screenshot_device_scale_factor,
        )
        if effective_block_heavy_assets:
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
