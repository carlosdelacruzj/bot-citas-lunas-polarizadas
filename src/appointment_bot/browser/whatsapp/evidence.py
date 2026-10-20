from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import BrowserContext, Page
from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.whatsapp.progress import record_evidence


def _save_whatsapp_debug_screenshot(page: Page, name: str) -> str:
    artifact_name = f"{_safe_whatsapp_artifact_name(name)[:80]}-{uuid4().hex}"
    debug_screenshot = Path(f".runtime/whatsapp-evidence/{artifact_name}.png").resolve()
    debug_screenshot.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(debug_screenshot))
    path = str(Path(".runtime/whatsapp-evidence") / f"{artifact_name}.png")
    if any(marker in name for marker in (
        "text-send-uncertain", "text-confirmation-final-check", "send-not-confirmed",
    )):
        try:
            diagnostic = page.evaluate("""() => Array.from(document.querySelectorAll(
                '.message-out, [data-testid="msg-container"]'
            )).slice(-3).map(element => ({
                id: element.closest('[data-id]')?.getAttribute('data-id'),
                text: element.textContent,
                images: Array.from(element.querySelectorAll('img[alt]'))
                    .map(image => image.getAttribute('alt')),
                labels: Array.from(element.querySelectorAll('[aria-label]'))
                    .map(label => label.getAttribute('aria-label')),
                icons: Array.from(element.querySelectorAll('[data-icon], svg title'))
                    .map(icon => ({icon: icon.getAttribute('data-icon'),
                        text: icon.textContent,
                        classes: icon.parentElement?.getAttribute('class')}))
            }))""")
            debug_screenshot.with_suffix(".json").write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except PlaywrightError:
            pass
    record_evidence(path)
    return path


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
    except Exception:
        return None
