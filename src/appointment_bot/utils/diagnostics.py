import logging
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.configuration.evidence import EvidenceSettings
from appointment_bot.utils.sanitization import sanitize_text
from appointment_bot.utils.screenshots import (
    artifact_filename,
    mask_sensitive_page,
    screenshot_artifact_dir,
)

logger = logging.getLogger(__name__)


def diagnostic_artifact_path(
    label: str, extension: str, *, evidence_settings: EvidenceSettings
) -> Path:
    return screenshot_artifact_dir(
        "diagnostics", evidence_settings=evidence_settings
    ) / artifact_filename(label, extension, evidence_settings=evidence_settings)


def save_sanitized_page_html(
    page: Page, label: str, *, evidence_settings: EvidenceSettings
) -> Path | None:
    path = diagnostic_artifact_path(label, ".html", evidence_settings=evidence_settings)
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
