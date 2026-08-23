from __future__ import annotations

import base64
import binascii
import logging
import struct
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.reservation_engine.appointments import APPOINTMENT_PANEL_SCREENSHOT_SELECTORS
from appointment_bot.reservation_engine.reservation_captcha_math import (
    read_reservation_math_captcha,
)
from appointment_bot.reservation_engine.reservation_captcha_refresh import (
    ensure_reservation_captcha_loaded,
)
from appointment_bot.reservation_engine.reservation_controls import (
    CAPTCHA_MEDIA_SELECTOR,
    RESERVATION_MATH_CAPTCHA_CONTAINER_SELECTOR,
)
from appointment_bot.services.telegram_alerts import enqueue_generic_telegram_alert
from appointment_bot.utils.screenshots import artifact_filename, screenshot_artifact_dir

logger = logging.getLogger(__name__)


def save_reservation_captcha_image(
    page: Page,
    settings: Settings,
    label: str,
    *,
    captcha_audit: dict[str, Any] | None = None,
) -> Path:
    logger.info("Saving isolated reservation captcha image")
    captcha_dir = screenshot_artifact_dir(settings, "captchas")
    captcha_dir.mkdir(parents=True, exist_ok=True)
    captcha_path = captcha_dir / artifact_filename(settings, label)

    for selector in APPOINTMENT_PANEL_SCREENSHOT_SELECTORS:
        panel = page.locator(selector).first
        try:
            if panel.count() == 0:
                continue

            with _revealed_panel(panel):
                math_challenge = read_reservation_math_captcha(panel)
                if math_challenge is not None:
                    math_captcha = panel.locator(
                        RESERVATION_MATH_CAPTCHA_CONTAINER_SELECTOR
                    ).first
                    if math_captcha.count() != 1:
                        raise RuntimeError(
                            "The reservation math captcha container is missing."
                        )
                    math_captcha.scroll_into_view_if_needed(timeout=5_000)
                    math_captcha.screenshot(path=str(captcha_path), timeout=10_000)
                    _record_png_dimensions(
                        captcha_path,
                        captcha_audit,
                        width_key="captcha_image_width",
                        height_key="captcha_image_height",
                    )
                    if captcha_audit is not None:
                        bounds = math_captcha.bounding_box()
                        captcha_audit.update(
                            {
                                "captcha_kind": "html_math",
                                "captcha_sent_source": "html_math_screenshot",
                                "captcha_math_expression_sha256": (
                                    math_challenge.signature
                                ),
                                "captcha_media_tag": "DIV",
                            }
                        )
                        if bounds is not None:
                            captcha_audit["captcha_element_css_width"] = round(
                                float(bounds["width"]), 3
                            )
                            captcha_audit["captcha_element_css_height"] = round(
                                float(bounds["height"]), 3
                            )
                    logger.info(
                        "Saved reservation math captcha evidence: %s using selector %s",
                        captcha_path,
                        selector,
                    )
                    return captcha_path

                if not ensure_reservation_captcha_loaded(
                    panel,
                    timeout=settings.read_timeout_seconds * 1_000,
                ):
                    logger.warning(
                        "Reservation panel captcha was not loaded using selector %s",
                        selector,
                    )
                    continue
                captcha_media = _captcha_media_locator(panel)
                if captcha_media is None:
                    logger.warning("No captcha image was found using selector %s", selector)
                    continue
                if not settings.captcha_shadow_enabled:
                    enqueue_generic_telegram_alert(
                        "⚠️ El portal volvió a mostrar un CAPTCHA gráfico. "
                        "La reserva seguirá usando 2Captcha; V3/V6 permanecen "
                        "en reserva fría hasta una reactivación explícita.",
                        dedupe_key=(
                            "captcha-graphic-returned:"
                            f"{datetime.now(UTC).strftime('%Y-%m')}"
                        ),
                    )
                captcha_media.scroll_into_view_if_needed(timeout=5_000)
                _record_captcha_render_metrics(captcha_media, captcha_audit)
                if captcha_audit is not None:
                    captcha_audit["captcha_kind"] = "image"
                original_path = _save_original_captcha_data_uri(
                    captcha_media,
                    captcha_path,
                    captcha_audit,
                )
                if original_path is not None:
                    logger.info(
                        "Using original HTML reservation captcha image without "
                        "saving an isolated screenshot: %s",
                        original_path,
                    )
                    return captcha_path

                captcha_media.screenshot(path=str(captcha_path), timeout=10_000)
                _record_png_dimensions(
                    captcha_path,
                    captcha_audit,
                    width_key="captcha_image_width",
                    height_key="captcha_image_height",
                )
            logger.info(
                "Saved isolated reservation captcha image: %s using selector %s",
                captcha_path,
                selector,
            )
            return captcha_path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save isolated reservation captcha with selector %s: %s",
                selector,
                exc,
            )

    raise RuntimeError("Could not save the reservation captcha image for captcha solving.")


def captcha_submission_image_path(
    screenshot_path: Path,
    captcha_audit: dict[str, Any],
) -> Path:
    original_path = captcha_audit.get("captcha_original_html_path")
    if original_path:
        path = Path(str(original_path))
        if path.exists():
            return path
        logger.warning(
            "Original HTML captcha path was recorded but does not exist: %s",
            path,
        )
    return screenshot_path


def _record_captcha_render_metrics(captcha_media, captcha_audit: dict[str, Any] | None) -> None:
    if captcha_audit is None:
        return
    try:
        bounds = captcha_media.bounding_box()
    except PlaywrightError as exc:
        logger.debug("Could not read captcha bounding box: %s", exc)
        bounds = None
    if bounds is not None:
        captcha_audit["captcha_element_css_width"] = round(float(bounds["width"]), 3)
        captcha_audit["captcha_element_css_height"] = round(float(bounds["height"]), 3)
    try:
        metadata = captcha_media.evaluate(
            """element => {
                const rect = element.getBoundingClientRect();
                const result = {
                    devicePixelRatio: window.devicePixelRatio || 1,
                    tagName: element.tagName,
                    cssWidth: rect.width,
                    cssHeight: rect.height
                };
                if (element.tagName === "IMG") {
                    result.naturalWidth = element.naturalWidth || null;
                    result.naturalHeight = element.naturalHeight || null;
                    result.currentSrc = element.currentSrc || element.getAttribute("src") || "";
                } else if (element.tagName === "CANVAS") {
                    result.naturalWidth = element.width || null;
                    result.naturalHeight = element.height || null;
                }
                return result;
            }"""
        )
    except PlaywrightError as exc:
        logger.debug("Could not read captcha media metadata: %s", exc)
        return
    if not isinstance(metadata, dict):
        return
    captcha_audit["captcha_device_scale_factor"] = metadata.get("devicePixelRatio")
    captcha_audit["captcha_media_tag"] = metadata.get("tagName")
    if metadata.get("naturalWidth") is not None:
        captcha_audit["captcha_natural_width"] = metadata.get("naturalWidth")
    if metadata.get("naturalHeight") is not None:
        captcha_audit["captcha_natural_height"] = metadata.get("naturalHeight")


def _save_original_captcha_data_uri(
    captcha_media,
    screenshot_path: Path,
    captcha_audit: dict[str, Any] | None,
) -> Path | None:
    if captcha_audit is None:
        return None
    try:
        source = captcha_media.evaluate(
            """element => {
                if (element.tagName !== "IMG") {
                    return "";
                }
                return element.currentSrc || element.getAttribute("src") || "";
            }"""
        )
    except PlaywrightError as exc:
        logger.debug("Could not read original captcha source: %s", exc)
        return None
    if not isinstance(source, str) or not source.startswith("data:"):
        captcha_audit["captcha_original_html_source"] = "not_data_uri"
        return None

    header, separator, payload = source.partition(",")
    if separator != "," or ";base64" not in header.casefold():
        captcha_audit["captcha_original_html_source"] = "unsupported_data_uri"
        return None
    mime_type = header[5:].split(";", 1)[0].strip() or "unknown"
    try:
        image_bytes = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        captcha_audit["captcha_original_html_source"] = "invalid_base64"
        logger.debug("Could not decode original captcha data URI: %s", exc)
        return None
    if not image_bytes:
        captcha_audit["captcha_original_html_source"] = "empty_data_uri"
        return None

    detected_format = _detect_image_format(image_bytes)
    extension = {
        "png": ".png",
        "jpeg": ".jpg",
        "gif": ".gif",
        "webp": ".webp",
    }.get(detected_format, ".bin")
    original_path = screenshot_path.with_name(
        f"{screenshot_path.stem}-original{extension}"
    )
    try:
        original_path.write_bytes(image_bytes)
    except OSError as exc:
        logger.debug("Could not save original captcha data URI to %s: %s", original_path, exc)
        return None

    captcha_audit["captcha_original_html_source"] = "data_uri"
    captcha_audit["captcha_original_html_path"] = str(original_path)
    captcha_audit["captcha_original_html_mime"] = mime_type
    captcha_audit["captcha_original_html_detected_format"] = detected_format or "unknown"
    captcha_audit["captcha_original_html_bytes"] = len(image_bytes)
    if detected_format == "png":
        _record_png_dimensions(
            original_path,
            captcha_audit,
            width_key="captcha_original_html_width",
            height_key="captcha_original_html_height",
        )
    logger.info("Saved original reservation captcha from HTML data URI: %s", original_path)
    return original_path


def _detect_image_format(image_bytes: bytes) -> str | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    return None


def _record_png_dimensions(
    path: Path,
    captcha_audit: dict[str, Any] | None,
    *,
    width_key: str,
    height_key: str,
) -> None:
    if captcha_audit is None:
        return
    dimensions = _png_dimensions(path)
    if dimensions is None:
        return
    width, height = dimensions
    captcha_audit[width_key] = width
    captcha_audit[height_key] = height


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        logger.debug("Could not read PNG dimensions from %s: %s", path, exc)
        return None
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


@contextmanager
def _revealed_panel(panel):
    panel.evaluate(
        """element => {
            const changed = [];
            for (
                let node = element;
                node && node !== document.body;
                node = node.parentElement
            ) {
                const style = getComputedStyle(node);
                if (
                    style.display === "none"
                    || style.visibility === "hidden"
                    || style.opacity === "0"
                ) {
                    changed.push({
                        node,
                        style: node.getAttribute("style")
                    });
                    node.style.setProperty("display", "block", "important");
                    node.style.setProperty("visibility", "visible", "important");
                    node.style.setProperty("opacity", "1", "important");
                }
            }
            window.__appointmentBotCaptchaReveal = changed;
        }"""
    )
    try:
        yield
    finally:
        try:
            panel.page.evaluate(
                """() => {
                    const changed = window.__appointmentBotCaptchaReveal || [];
                    changed.forEach(item => {
                        if (item.style === null) item.node.removeAttribute("style");
                        else item.node.setAttribute("style", item.style);
                    });
                    delete window.__appointmentBotCaptchaReveal;
                }"""
            )
        except PlaywrightError:
            logger.warning("Could not restore appointment panel styles after captcha capture")


def _captcha_media_locator(panel):
    index = int(
        panel.locator(CAPTCHA_MEDIA_SELECTOR).evaluate_all(
            """elements => {
                const candidates = elements
                    .map((element, index) => {
                        const rect = element.getBoundingClientRect();
                        const area = rect.width * rect.height;
                        const isLoaded = element.tagName !== "IMG"
                            || (element.complete && element.naturalWidth > 0);
                        return { index, width: rect.width, height: rect.height, area, isLoaded };
                    })
                    .filter(item => item.width >= 40 && item.height >= 20 && item.isLoaded)
                    .sort((left, right) => right.area - left.area);
                return candidates.length ? candidates[0].index : -1;
            }"""
        )
    )
    if index < 0:
        return None
    return panel.locator(CAPTCHA_MEDIA_SELECTOR).nth(index)
