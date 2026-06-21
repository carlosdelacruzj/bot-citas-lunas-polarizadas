from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from appointment_bot.config import Settings

BLOCKED_RESOURCE_TYPES = {"font", "media"}


@contextmanager
def open_page(
    settings: Settings,
    *,
    headless: bool | None = None,
    block_heavy_assets: bool | None = None,
    init_script: str | None = None,
    video_dir: Path | None = None,
    video_width: int | None = None,
    video_height: int | None = None,
    video_path_callback: Callable[[Path | None], None] | None = None,
) -> Iterator[Page]:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    if video_dir is not None:
        video_dir.mkdir(parents=True, exist_ok=True)

    effective_headless = settings.headless if headless is None else headless
    effective_block_heavy_assets = (
        settings.block_heavy_assets if block_heavy_assets is None else block_heavy_assets
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=effective_headless)
        context_options = {
            "device_scale_factor": settings.screenshot_device_scale_factor,
        }
        if video_dir is not None:
            width = video_width or settings.client_video_width
            height = video_height or settings.client_video_height
            context_options.update(
                {
                    "record_video_dir": str(video_dir),
                    "record_video_size": {
                        "width": width,
                        "height": height,
                    },
                    "viewport": {
                        "width": width,
                        "height": height,
                    },
                }
            )
        context = browser.new_context(**context_options)
        if init_script is not None:
            context.add_init_script(init_script)
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
        video = page.video
        try:
            yield page
        finally:
            video_path = None
            try:
                context.close()
                if video is not None:
                    video_path = Path(video.path())
                if video_path_callback is not None:
                    video_path_callback(video_path)
            finally:
                browser.close()
