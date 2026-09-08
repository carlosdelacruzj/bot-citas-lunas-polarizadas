from __future__ import annotations

import base64
import re
from pathlib import Path

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError


def _save_whatsapp_debug_screenshot(page: Page, name: str) -> str:
    debug_screenshot = Path(f".runtime/{name}.png").resolve()
    debug_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(debug_screenshot))
    return str(Path(".runtime") / f"{name}.png")


def _safe_whatsapp_artifact_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "message"


def _whatsapp_qr_image_data_url(page: Page) -> str | None:
    candidates = page.locator("canvas, [data-ref]")
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if not candidate.is_visible():
            continue
        box = candidate.bounding_box()
        if not box or not (160 <= box["width"] <= 420 and 160 <= box["height"] <= 420):
            continue
        try:
            image_bytes = candidate.screenshot(type="png")
        except PlaywrightError:
            continue
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    return None


def _save_context_failure_screenshot(
    context: BrowserContext | None,
    draft: dict[str, object],
) -> str | None:
    if context is None or not context.pages:
        return None
    message_id = _safe_whatsapp_artifact_name(
        str(draft.get("message_id") or draft.get("action") or "unknown")
    )
    try:
        return _save_whatsapp_debug_screenshot(
            context.pages[-1],
            f"whatsapp-automation-error-{message_id}",
        )
    except PlaywrightError:
        return None
