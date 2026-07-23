from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

ATTACH_SELECTORS = (
    "[aria-label='Adjuntar']",
    "[aria-label='Attach']",
    "[data-icon='plus-rounded']",
    "[data-icon='clip']",
)
SEND_SELECTORS = (
    "[aria-label='Enviar']",
    "[aria-label='Send']",
    "[data-icon='send']",
)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _visible_count(page: Page, selectors: tuple[str, ...]) -> int:
    count = 0
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            try:
                if locator.nth(index).is_visible():
                    count += 1
            except PlaywrightError:
                continue
    return count


def _state(page: Page) -> dict[str, Any]:
    try:
        url = page.url
        title = page.title()
        qr_visible = page.locator("canvas").count() > 0 and (
            page.get_by_text("Vincular con el número de teléfono").count() > 0
            or page.get_by_text("Link with phone number").count() > 0
        )
        chat_ready = page.locator("#pane-side").count() > 0
        file_inputs = page.locator("input[type='file']")
        file_input_details = []
        for index in range(file_inputs.count()):
            node = file_inputs.nth(index)
            file_input_details.append(
                {
                    "index": index,
                    "accept": node.get_attribute("accept"),
                    "multiple": node.get_attribute("multiple") is not None,
                }
            )
        return {
            "url": url,
            "title": title,
            "qr_visible": qr_visible,
            "chat_ready": chat_ready,
            "attach_controls_visible": _visible_count(page, ATTACH_SELECTORS),
            "send_controls_visible": _visible_count(page, SEND_SELECTORS),
            "file_inputs": file_input_details,
            "dialog_count": page.locator("[role='dialog']").count(),
        }
    except PlaywrightError as exc:
        return {"page_error": str(exc)}


def _write_event(path: Path, event: str, **details: Any) -> None:
    payload = {"at": _now(), "event": event, **details}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--profile-dir",
        default=".runtime/whatsapp-web-profile",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    events_path = output_dir / "events.jsonl"
    profile_dir = Path(args.profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    _write_event(events_path, "H0_BROWSER_STARTING", profile_dir=str(profile_dir))
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport=None,
            args=["--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=45_000)
        _write_event(events_path, "PAGE_OPENED", url=page.url)

        previous_state: dict[str, Any] | None = None
        first_ready_event_written = False
        while True:
            if not context.pages:
                _write_event(events_path, "BROWSER_CLOSED")
                return 0
            page = context.pages[0]
            state = _state(page)
            if state != previous_state:
                _write_event(events_path, "DOM_STATE_CHANGED", state=state)
                previous_state = state
            if not first_ready_event_written and (
                state.get("chat_ready") or state.get("qr_visible")
            ):
                milestone = "H1_WHATSAPP_READY" if state.get("chat_ready") else "H1_LOGIN_REQUIRED"
                screenshot_path = output_dir / f"{milestone.lower()}.png"
                try:
                    page.screenshot(path=str(screenshot_path))
                except PlaywrightError:
                    screenshot_path = None
                _write_event(
                    events_path,
                    milestone,
                    screenshot_path=str(screenshot_path) if screenshot_path else None,
                    state=state,
                )
                first_ready_event_written = True
            time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
