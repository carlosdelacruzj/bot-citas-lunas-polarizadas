import logging
import re
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.utils.screenshots import mask_sensitive_page

logger = logging.getLogger(__name__)


def diagnostic_artifact_path(settings: Settings, label: str, extension: str) -> Path:
    safe_label = "-".join(part for part in re.split(r"[^a-zA-Z0-9]+", label) if part)
    safe_prefix = "-".join(
        part for part in settings.artifact_prefix.replace("_", "-").split("-") if part
    )
    prefix = f"{safe_prefix}-" if safe_prefix else ""
    suffix = extension if extension.startswith(".") else f".{extension}"
    return settings.screenshots_dir / "diagnostics" / f"{safe_label}-{prefix}{suffix}"


def save_sanitized_page_html(page: Page, settings: Settings, label: str) -> Path | None:
    path = diagnostic_artifact_path(settings, label, ".html")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mask_sensitive_page(page):
            html = page.content()
        path.write_text(sanitize_text(html), encoding="utf-8", newline="\n")
        logger.info("Saved diagnostic HTML snapshot: %s", path)
        return path
    except (OSError, PlaywrightError) as exc:
        logger.warning("Could not save diagnostic HTML snapshot %s: %s", path, exc)
        return None


def read_visible_page_text(page: Page, *, limit: int = 4000) -> str:
    try:
        text = str(
            page.evaluate(
                """() => {
                    const text = document.body ? document.body.innerText : "";
                    return text.replace(/\\s+/g, " ").trim();
                }"""
            )
            or ""
        )
    except PlaywrightError as exc:
        logger.debug("Could not read visible page text for diagnostics: %s", exc)
        return ""
    return sanitize_text(text[:limit])
