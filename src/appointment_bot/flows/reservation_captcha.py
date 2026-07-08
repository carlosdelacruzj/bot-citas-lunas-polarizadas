from __future__ import annotations

import base64
import binascii
import logging
import struct
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings
from appointment_bot.flows.appointments import (
    APPOINTMENT_PANEL_SCREENSHOT_SELECTORS,
    AppointmentWorkflowCancelled,
    ReservationDeferredForPriority,
    ReservationSubmissionUncertain,
    validate_selected_appointment,
)
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.services.reservation_timings import ReservationTiming
from appointment_bot.utils.screenshots import (
    artifact_filename,
    save_screenshot,
    screenshot_artifact_dir,
)

logger = logging.getLogger(__name__)

RESERVATION_FIELD_SELECTOR = "#MainContent_idUcitas_txtimg"
RESERVATION_BUTTON_SELECTOR = "#MainContent_idUcitas_btgSiguiente"
CAPTCHA_MEDIA_SELECTOR = "img, canvas"
CONFIRMATION_TEXTS = [
    "cita ha sido registrado",
    "cita ha sido registrada",
    "registrado satisfactoriamente",
    "registrada satisfactoriamente",
    "reservada con exito",
    "reservado con exito",
]
CAPTCHA_REJECTION_TEXTS = [
    "captcha incorrecto",
    "captcha invalido",
    "captcha valido",
    "codigo de seguridad incorrecto",
    "codigo de verificacion incorrecto",
    "ingrese el codigo valido del captcha",
]
SLOT_LOST_TEXTS = [
    "cupo ya no disponible",
    "cupo no disponible",
    "no existe cupos",
    "seleccione otra fecha",
    "ya no hay cupos",
    "sin cupos disponibles",
]
SUBMISSION_REJECTION_TEXTS = [
    "no se pudo registrar la cita",
    "no fue posible registrar la cita",
    "solicitud rechazada",
    "operacion no permitida",
]


def solve_reservation_captcha_and_click_reserve(
    page: Page,
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    can_solve_captcha: Callable[[], bool] | None = None,
    expected_details: dict[str, Any] | None = None,
    expected_person_name: str | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
    captcha_audit: dict[str, Any] | None = None,
    attempt_number: int = 1,
    timing: ReservationTiming | None = None,
) -> Page:
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de resolver el captcha.")
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    if timing is not None:
        timing.mark("captcha_image_started")
    effective_captcha_audit = captcha_audit if captcha_audit is not None else {}
    captcha_path = save_reservation_captcha_image(
        page,
        settings,
        "04-reserva-captcha-tecnico-2captcha",
        captcha_audit=effective_captcha_audit,
    )
    captcha_submission_path = _captcha_submission_image_path(
        captcha_path,
        effective_captcha_audit,
    )
    if captcha_audit is not None:
        captcha_audit["attempt"] = attempt_number
        captcha_audit["captcha_image_path"] = str(captcha_submission_path)
        if captcha_path.exists():
            captcha_audit["captcha_screenshot_image_path"] = str(captcha_path)
        captcha_audit["captcha_sent_source"] = (
            "original_html" if captcha_submission_path != captcha_path else "screenshot"
        )
    if timing is not None:
        timing.mark("captcha_image_finished")
    if can_solve_captcha is not None and not can_solve_captcha():
        raise ReservationDeferredForPriority(
            "Reserva diferida porque hay una orden de mayor prioridad lista.",
            dict(captcha_audit or {}),
        )
    try:
        if timing is not None:
            timing.mark("captcha_solver_started")
        captcha_solution = solve_normal_captcha(captcha_submission_path, settings)
        if captcha_audit is not None:
            captcha_audit["captcha_solution_sent"] = captcha_solution
        if timing is not None:
            timing.mark("captcha_solver_finished")
    finally:
        logger.info("Preserved captcha image sent to 2captcha: %s", captcha_submission_path)
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de enviar el captcha de reserva."
        )
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de enviar la reserva.")
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)

    logger.info("Filling reservation captcha field")
    reservation_field = page.locator(RESERVATION_FIELD_SELECTOR).first
    reservation_field.wait_for(state="visible", timeout=15_000)
    reservation_field.fill(captcha_solution, timeout=15_000)
    if timing is not None:
        timing.mark("captcha_filled")
    if captcha_audit is not None:
        pre_submit_path = save_screenshot(
            page,
            settings,
            f"05-reserva-antes-de-enviar-intento-{attempt_number}",
        )
        if pre_submit_path is not None:
            captcha_audit["pre_submit_screenshot_path"] = str(pre_submit_path)

    logger.info("Clicking reservation button")
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de pulsar el boton de reserva."
        )
    reserve_button = page.locator(RESERVATION_BUTTON_SELECTOR).first
    reserve_button.wait_for(state="visible", timeout=15_000)
    reserve_button.scroll_into_view_if_needed(timeout=15_000)
    validate_selected_appointment(page, expected_details, expected_person_name=expected_person_name)
    if on_submission_intent is not None:
        on_submission_intent()
    try:
        if timing is not None:
            timing.mark("reserve_click_started")
        reserve_button.click(timeout=15_000)
    except PlaywrightError as exc:
        if on_submission_started is not None:
            on_submission_started()
        raise ReservationSubmissionUncertain(
            "El click en Reservar pudo haber sido enviado, pero Playwright no pudo "
            "confirmar la respuesta."
        ) from exc
    if on_submission_started is not None:
        on_submission_started()
    try:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15_000)
        except PlaywrightTimeoutError:
            logger.info("Reservation click did not trigger domcontentloaded before timeout")
        logger.info("Current page after reservation click: %s", page.url)
        if timing is not None:
            timing.mark("portal_response")
    except PlaywrightError as exc:
        raise ReservationSubmissionUncertain(
            "La solicitud de reserva fue enviada, pero la pagina se desconecto antes "
            "de iniciar la verificacion."
        ) from exc
    return page


def _captcha_submission_image_path(
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


def refresh_reservation_captcha(page: Page, settings: Settings) -> bool:
    logger.info("Refreshing reservation captcha after invalid captcha response")
    try:
        page.locator(RESERVATION_FIELD_SELECTOR).first.fill("", timeout=5_000)
    except PlaywrightError as exc:
        logger.info("Could not clear reservation captcha field before retry: %s", exc)

    for selector in APPOINTMENT_PANEL_SCREENSHOT_SELECTORS:
        panel = page.locator(selector).first
        try:
            if panel.count() == 0:
                continue
            previous_signature = _captcha_signature(panel)
            changed = _click_panel_captcha_refresh(panel)
            if not changed:
                changed = _reload_panel_captcha_images(
                    panel,
                    cache_buster="_appointment_bot_captcha_retry",
                )
            if not changed:
                logger.info("No captcha image resource was changed using selector %s", selector)
                return ensure_reservation_captcha_loaded(
                    panel,
                    timeout=settings.read_timeout_seconds * 1_000,
                )
            return wait_for_reservation_captcha_changed(
                panel,
                previous_signature=previous_signature,
                timeout=settings.read_timeout_seconds * 1_000,
            )
        except PlaywrightError as exc:
            logger.info("Could not refresh captcha with selector %s: %s", selector, exc)
    return False


def wait_for_reservation_submission_outcome(page: Page, *, timeout: int = 10_000) -> str:
    outcome_texts = {
        "confirmed": CONFIRMATION_TEXTS,
        "captcha_invalid": CAPTCHA_REJECTION_TEXTS,
        "slot_lost": SLOT_LOST_TEXTS,
        "rejected": SUBMISSION_REJECTION_TEXTS,
    }
    try:
        return str(
            page.wait_for_function(
                """groups => {
                    const normalize = value => (value || "")
                        .toLowerCase()
                        .normalize("NFD")
                        .replace(/[\\u0300-\\u036f]/g, "");
                    const text = normalize(document.body ? document.body.innerText : "");
                    for (const [outcome, values] of Object.entries(groups)) {
                        if (values.some(value => text.includes(normalize(value)))) return outcome;
                    }
                    return false;
                }""",
                arg=outcome_texts,
                timeout=timeout,
            ).json_value()
        )
    except PlaywrightTimeoutError:
        return "unknown"


def wait_for_reservation_confirmation(page: Page) -> bool:
    logger.info("Waiting for reservation confirmation")
    try:
        page.wait_for_function(
            """texts => {
                const bodyText = (document.body ? document.body.innerText : "").toLowerCase();
                return texts.some(text => bodyText.includes(text));
            }""",
            arg=CONFIRMATION_TEXTS,
            timeout=10_000,
        )
        return True
    except PlaywrightTimeoutError:
        logger.info("Reservation confirmation text was not detected before timeout")
        return False


def dismiss_reservation_confirmation(page: Page) -> None:
    logger.info("Trying to dismiss reservation confirmation")
    selectors = [
        ".swal2-confirm",
        "button:has-text('OK')",
        "button:has-text('Aceptar')",
        "button:has-text('Salir')",
        "button:has-text('Cerrar')",
        "input[type='button'][value='OK']",
        "input[type='button'][value='Aceptar']",
        "input[type='button'][value='Salir']",
        "input[type='button'][value='Cerrar']",
    ]
    for selector in selectors:
        control = page.locator(selector).first
        try:
            if control.count() == 0 or not control.is_visible(timeout=1_000):
                continue

            control.click(timeout=5_000)
            page.wait_for_timeout(1_000)
            logger.info("Dismissed reservation confirmation using selector %s", selector)
            return
        except PlaywrightError as exc:
            logger.info("Could not dismiss confirmation with selector %s: %s", selector, exc)

    logger.info("No reservation confirmation control was dismissed")


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
                captcha_media.scroll_into_view_if_needed(timeout=5_000)
                _record_captcha_render_metrics(captcha_media, captcha_audit)
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


def _captcha_signature(panel) -> str:
    try:
        return str(
            panel.locator(CAPTCHA_MEDIA_SELECTOR).evaluate_all(
                """elements => elements
                    .map(element => {
                        const rect = element.getBoundingClientRect();
                        if (rect.width < 40 || rect.height < 20) return "";
                        if (element.tagName === "IMG") {
                            return [
                                element.getAttribute("src") || "",
                                element.complete ? "complete" : "loading",
                                element.naturalWidth,
                                element.naturalHeight
                            ].join("|");
                        }
                        return ["canvas", rect.width, rect.height].join("|");
                    })
                    .filter(Boolean)
                    .join("||")"""
            )
        )
    except PlaywrightError:
        return ""


def wait_for_reservation_captcha_changed(
    panel,
    *,
    previous_signature: str,
    timeout: int = 15_000,
) -> bool:
    deadline = time.monotonic() + timeout / 1_000
    while time.monotonic() < deadline:
        if ensure_reservation_captcha_loaded(panel, timeout=1_000):
            current_signature = _captcha_signature(panel)
            if current_signature and current_signature != previous_signature:
                return True
            if not previous_signature and current_signature:
                return True
        panel.page.wait_for_timeout(250)
    return False


def _click_panel_captcha_refresh(panel) -> bool:
    return bool(
        panel.evaluate(
            """element => {
                const media = Array.from(element.querySelectorAll("img, canvas"))
                    .map(item => ({ item, rect: item.getBoundingClientRect() }))
                    .filter(item => item.rect.width >= 40 && item.rect.height >= 20)
                    .sort((left, right) => (
                        right.rect.width * right.rect.height
                    ) - (
                        left.rect.width * left.rect.height
                    ))[0];
                if (!media) return false;

                const mediaRect = media.rect;
                const controls = Array.from(
                    element.querySelectorAll(
                        "button, a, input[type='button'], input[type='image'], input[type='submit']"
                    )
                );
                const scored = controls
                    .map(control => {
                        const rect = control.getBoundingClientRect();
                        const label = [
                            control.id,
                            control.name,
                            control.value,
                            control.title,
                            control.alt,
                            control.getAttribute("aria-label"),
                            control.textContent
                        ].join(" ").toLowerCase();
                        const looksLikeRefresh = (
                            /refresh|reload|reset|captcha|actualizar|recargar|cambiar|nuevo/
                        ).test(label);
                        const nearCaptcha = rect.left >= mediaRect.right - 8
                            && Math.abs(
                                (rect.top + rect.bottom) / 2
                                - (mediaRect.top + mediaRect.bottom) / 2
                            ) <= 80;
                        return {
                            control,
                            score: (looksLikeRefresh ? 2 : 0) + (nearCaptcha ? 1 : 0),
                            area: rect.width * rect.height
                        };
                    })
                    .filter(item => item.score > 0 && item.area > 0)
                    .sort((left, right) => right.score - left.score || left.area - right.area);
                if (!scored.length) return false;
                scored[0].control.click();
                return true;
            }"""
        )
    )


def _reload_panel_captcha_images(panel, *, cache_buster: str) -> bool:
    return bool(
        panel.locator("img").evaluate_all(
            """(elements, cacheBuster) => {
                let changed = false;
                for (const image of elements) {
                    const rect = image.getBoundingClientRect();
                    if (rect.width < 40 || rect.height < 20) continue;
                    const source = image.getAttribute("src");
                    if (!source) continue;
                    const url = new URL(source, window.location.href);
                    url.searchParams.set(cacheBuster, Date.now().toString());
                    image.src = url.toString();
                    changed = true;
                }
                return changed;
            }""",
            cache_buster,
        )
    )



def _panel_has_loaded_captcha(panel) -> bool:
    return bool(
        panel.locator("img, canvas").evaluate_all(
            """elements => elements.some(element => {
                const rect = element.getBoundingClientRect();
                if (rect.width < 40 || rect.height < 20) return false;
                if (element.tagName === "IMG") {
                    return element.complete && element.naturalWidth > 0;
                }
                return true;
            })"""
        )
    )


def ensure_reservation_captcha_loaded(panel, *, timeout: int = 15_000) -> bool:
    if _wait_for_panel_captcha(panel, timeout=timeout):
        return True

    logger.warning("Reservation CAPTCHA did not load; retrying its image resource")
    reloaded = _reload_panel_captcha_images(panel, cache_buster="_appointment_bot_retry")
    if not reloaded:
        return False
    return _wait_for_panel_captcha(panel, timeout=timeout)


def _wait_for_panel_captcha(panel, *, timeout: int) -> bool:
    deadline = time.monotonic() + timeout / 1_000
    while time.monotonic() < deadline:
        if _panel_has_loaded_captcha(panel):
            return True
        panel.page.wait_for_timeout(250)
    return False

