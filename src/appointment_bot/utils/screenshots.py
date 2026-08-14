import logging
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings
from appointment_bot.core.models import RunReport

logger = logging.getLogger(__name__)
ARTIFACT_TIMEZONE = ZoneInfo("America/Lima")
ARTIFACT_LABEL_ALIASES = {
    "process-stages": "etapas",
    "result-available": "cupo",
    "reservation-confirmation": "confirmacion",
    "02-detalle-tramite-etapas-reservar-cita": "etapas",
    "03-modal-reserva-citas-cupo-disponible": "cupo",
    "03-modal-reserva-citas-disponibilidad-parcial": "parcial",
    "03-modal-reserva-citas-resultado-desconocido": "resultado",
    "04-reserva-captcha-tecnico-2captcha": "captcha",
    "07-detalle-tramite-etapa-programado-confirmada": "programado",
    "post-queue-programado-review": "programado-final",
    "post-queue-review-error": "revision-error",
    "error-flujo-principal": "error",
    "observer-cupo-disponible": "observer-cupo",
}


def screenshot_artifact_dir(settings: Settings, *parts: str) -> Path:
    day = datetime.now(ARTIFACT_TIMEZONE).strftime("%d-%m-%Y")
    return settings.screenshots_dir.joinpath(day, *parts)


def _artifact_path(settings: Settings, label: str) -> Path:
    return screenshot_artifact_dir(settings) / artifact_filename(settings, label)


def artifact_filename(settings: Settings, label: str, extension: str = ".png") -> str:
    suffix = extension if extension.startswith(".") else f".{extension}"
    parts = [
        _short_artifact_label(label),
        *_short_artifact_prefix(settings.artifact_prefix),
        uuid4().hex[:6],
    ]
    return f"{'-'.join(part for part in parts if part)}{suffix}"


def _short_artifact_label(label: str) -> str:
    if label in ARTIFACT_LABEL_ALIASES:
        return ARTIFACT_LABEL_ALIASES[label]
    match = re.fullmatch(r"06-reserva-respuesta-portal(?:-html)?-intento-(\d+)", label)
    if match:
        prefix = "portal-html" if "-html-" in label else "portal"
        return f"{prefix}-{match.group(1)}"
    match = re.fullmatch(r"05-reserva-antes-de-enviar-intento-(\d+)", label)
    if match:
        return f"preenvio-{match.group(1)}"
    if label.startswith("observer-captcha-sample-"):
        return label.replace("observer-captcha-sample-", "observer-captcha-")
    return "-".join(part for part in re.split(r"[^a-zA-Z0-9]+", label.lower()) if part)[:36]


def _short_artifact_prefix(prefix: str) -> list[str]:
    parts = [part for part in prefix.replace("_", "-").split("-") if part]
    result: list[str] = []
    if parts and parts[0] == "observer":
        result.append("observer")

    for part in parts:
        if re.fullmatch(r"\d{6}", part):
            result.append(part)
            break

    for index, part in enumerate(parts[:-1]):
        if part == "order" and parts[index + 1]:
            result.append(f"order-{parts[index + 1]}")
            break

    return result


def normalize_screenshot_paths(
    screenshot_path: Path | None,
    screenshot_paths: list[Path] | None,
) -> list[Path]:
    paths = []
    if screenshot_path is not None:
        paths.append(screenshot_path)
    if screenshot_paths:
        paths.extend(screenshot_paths)

    unique_paths = []
    seen = set()
    for path in paths:
        path_key = str(path)
        if path_key in seen:
            continue
        seen.add(path_key)
        unique_paths.append(path)
    return unique_paths


def report_screenshot_paths(report: RunReport) -> list[Path]:
    primary = Path(report.screenshot_path) if report.screenshot_path else None
    additional = [Path(item) for item in report.screenshot_paths or []]
    return normalize_screenshot_paths(primary, additional)


def archive_unique_slot_screenshot(
    settings: Settings,
    report: RunReport,
) -> Path | None:
    archived = archive_unique_slot_screenshots(settings, report)
    return archived[0] if archived else None


def archive_unique_slot_capture(
    settings: Settings,
    details: dict,
    source: Path,
) -> Path | None:
    if not source.is_file():
        return None
    slot_key = _unique_slot_key(details)
    if slot_key is None:
        return None
    return _archive_unique_slot_candidate(settings, slot_key, source)


def archive_unique_slot_screenshots(
    settings: Settings,
    report: RunReport,
) -> list[Path]:
    candidates: list[tuple[dict, Path]] = []
    for evidence in report.unique_slot_evidence or []:
        source = Path(str(evidence.get("screenshot_path") or ""))
        if _unique_slot_key(evidence) is not None and source.is_file():
            candidates.append((evidence, source))

    if not candidates:
        source = next(
            (
                path
                for path in report_screenshot_paths(report)
                if _is_slot_screenshot(path) and path.is_file()
            ),
            None,
        )
        if source is not None:
            candidates.append((report.details or {}, source))

    archived: list[Path] = []
    seen_keys: set[str] = set()
    for details, source in candidates:
        slot_key = _unique_slot_key(details)
        if slot_key is None or slot_key in seen_keys:
            continue
        seen_keys.add(slot_key)
        destination = archive_unique_slot_capture(settings, details, source)
        if destination is not None:
            archived.append(destination)
    return archived


def _archive_unique_slot_candidate(
    settings: Settings,
    slot_key: str,
    source: Path,
) -> Path | None:
    destination = screenshot_artifact_dir(settings, "cupos-unicos") / f"{slot_key}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        logger.info(
            "Unique slot screenshot already archived for %s: %s",
            slot_key,
            destination,
        )
        return destination

    try:
        with source.open("rb") as source_file, destination.open("xb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)
    except FileExistsError:
        logger.info(
            "Unique slot screenshot was archived concurrently for %s: %s",
            slot_key,
            destination,
        )
        return destination
    except OSError as exc:
        logger.warning(
            "Could not archive unique slot screenshot %s from %s: %s",
            slot_key,
            source,
            exc,
        )
        return None

    logger.info("Archived unique slot screenshot: %s", destination)
    return destination


def _is_slot_screenshot(path: Path) -> bool:
    return path.name.startswith(("cupo-", "observer-cupo-"))


def _unique_slot_key(details: dict) -> str | None:
    date_text = str(details.get("fecha") or "").strip()
    hour_text = str(details.get("hora") or "").strip()
    date_match = re.match(
        r"^(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>\d{4})"
        r"(?:\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?)?",
        date_text,
    )
    if date_match is None:
        return None

    hour_match = re.match(r"^(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?", hour_text)
    hour = hour_match.group("hour") if hour_match is not None else date_match.group("hour")
    minute = (
        hour_match.group("minute")
        if hour_match is not None
        else date_match.group("minute")
    )
    if hour is None:
        return None

    day = int(date_match.group("day"))
    month = int(date_match.group("month"))
    year = int(date_match.group("year"))
    hour_number = int(hour)
    minute_number = int(minute or "0")
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    if not 0 <= hour_number <= 23 or not 0 <= minute_number <= 59:
        return None

    return (
        f"{day:02d}-{month:02d}-{year:04d}_"
        f"{hour_number:02d}-{minute_number:02d}"
    )


def remove_screenshot_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            logger.info("Removed screenshot: %s", path)
        except OSError as exc:
            logger.warning("Could not remove screenshot %s: %s", path, exc)


@contextmanager
def mask_sensitive_page(page: Page) -> Iterator[None]:
    page.evaluate(
        """() => {
            const sensitiveParts = [
                "dni", "documento", "nombre", "paterno", "materno",
                "apellido", "usuario", "username", "email", "mail",
                "captcha", "txtimg", "codigo"
            ];
            const controls = Array.from(document.querySelectorAll("input, textarea"));
            const sensitiveValues = controls.map(element => {
                const key = [
                    element.id, element.name, element.placeholder,
                    element.getAttribute("aria-label")
                ].join(" ").toLowerCase();
                const value = (element.value || "").trim();
                return sensitiveParts.some(part => key.includes(part)) && value.length > 2
                    ? value
                    : "";
            }).filter(Boolean);

            window.__appointmentBotScreenshotMask = {
                controls: controls.map(element => ({ element, value: element.value })),
                textNodes: []
            };
            controls.forEach(element => {
                const key = [
                    element.id, element.name, element.placeholder,
                    element.getAttribute("aria-label")
                ].join(" ").toLowerCase();
                const type = (element.type || "").toLowerCase();
                const isSensitive = sensitiveParts.some(part => key.includes(part));
                const canContainSecret = ![
                    "hidden", "button", "submit", "reset", "image"
                ].includes(type);
                if (isSensitive && canContainSecret && element.value) {
                    element.value = "***";
                }
            });

            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const original = node.nodeValue || "";
                let masked = original.replace(/\\b\\d{8}\\b/g, "***");
                sensitiveValues.forEach(value => {
                    masked = masked.split(value).join("***");
                });
                if (masked !== original) {
                    window.__appointmentBotScreenshotMask.textNodes.push({ node, original });
                    node.nodeValue = masked;
                }
            }
        }"""
    )
    try:
        yield
    finally:
        page.evaluate(
            """() => {
                const mask = window.__appointmentBotScreenshotMask;
                if (!mask) return;
                mask.controls.forEach(item => { item.element.value = item.value; });
                mask.textNodes.forEach(item => { item.node.nodeValue = item.original; });
                delete window.__appointmentBotScreenshotMask;
            }"""
        )


def save_screenshot(page: Page, settings: Settings, label: str) -> Path | None:
    path = _artifact_path(settings, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mask_sensitive_page(page):
            page.screenshot(path=str(path), full_page=True)
        logger.info("Saved screenshot: %s", path)
        return path
    except PlaywrightError as exc:
        logger.warning("Could not save screenshot %s: %s", path, exc)
        return None


def save_programmed_review_screenshot(page: Page, settings: Settings) -> Path | None:
    path = _artifact_path(settings, "post-queue-programado-review")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        viewport = page.viewport_size
        if viewport is not None and viewport["height"] < 1_100:
            page.set_viewport_size({"width": viewport["width"], "height": 1_100})
            page.wait_for_timeout(250)
        clip = page.evaluate(
            """() => {
                const wanted = new Set(["paterno", "materno", "nombres"]);
                const labels = Array.from(document.querySelectorAll("body *"))
                    .filter(element => {
                        if (element.children.length) return false;
                        return wanted.has((element.textContent || "").trim().toLowerCase());
                    });
                const stageLabel = Array.from(document.querySelectorAll("body *"))
                    .find(element => {
                        if (element.children.length) return false;
                        return (element.textContent || "").trim().toLowerCase()
                            === "separa cita peritaje";
                    });
                const stageRow = stageLabel?.closest("tr") || stageLabel?.parentElement;
                const stages = stageRow?.closest("table");
                if (labels.length !== 3 || !stageRow || !stages) return null;
                const labelRects = labels.map(element => element.getBoundingClientRect());
                const labelTop = Math.min(...labelRects.map(rect => rect.top));
                const labelBottom = Math.max(...labelRects.map(rect => rect.bottom));
                const controls = Array.from(document.querySelectorAll("input"))
                    .filter(element => {
                        const rect = element.getBoundingClientRect();
                        return rect.width > 0
                            && rect.top >= labelTop
                            && rect.top <= labelBottom + 120;
                    });
                const identityValues = controls.map(element => (element.value || "").trim());
                if (identityValues.length < 3 || identityValues.some(value => !value)) return null;
                const stageText = (stageRow.textContent || "").toLowerCase();
                if (!stageText.includes("programado")) return null;
                const rects = [...labels, ...controls]
                    .map(element => element.getBoundingClientRect())
                    .filter(rect => rect.width > 0 && rect.height > 0);
                if (!rects.length) return null;
                const tableRect = stages.getBoundingClientRect();
                const stageRowRect = stageRow.getBoundingClientRect();
                const margin = 24;
                const left = Math.max(
                    0,
                    Math.min(tableRect.left, ...rects.map(rect => rect.left)) - margin
                );
                const top = Math.max(0, Math.min(...rects.map(rect => rect.top)) - margin);
                const right = Math.min(
                    document.documentElement.clientWidth,
                    Math.max(tableRect.right, ...rects.map(rect => rect.right)) + margin
                );
                const bottom = stageRowRect.bottom + 4;
                return {
                    x: left + window.scrollX,
                    y: top + window.scrollY,
                    width: right - left,
                    height: bottom - top
                };
            }"""
        )
        if not clip:
            logger.warning("Could not determine identity-to-programmed-stage screenshot region")
            return None
        page.screenshot(path=str(path), clip=clip)
        logger.info("Saved programmed review screenshot: %s", path)
        return path
    except PlaywrightError as exc:
        logger.warning("Could not save programmed review screenshot %s: %s", path, exc)
        return None


def save_element_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
) -> Path | None:
    path = _artifact_path(settings, label)
    path.parent.mkdir(parents=True, exist_ok=True)

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue

            locator.scroll_into_view_if_needed(timeout=5_000)
            with mask_sensitive_page(page):
                locator.screenshot(path=str(path), timeout=10_000)
            logger.info("Saved element screenshot: %s using selector %s", path, selector)
            return path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save element screenshot %s with selector %s: %s",
                path,
                selector,
                exc,
            )

    return None


def save_centered_modal_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
) -> Path | None:
    path = _artifact_path(settings, label)
    path.parent.mkdir(parents=True, exist_ok=True)

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue

            locator.scroll_into_view_if_needed(timeout=5_000)
            bounds = locator.bounding_box()
            viewport = page.viewport_size
            if bounds is None or viewport is None:
                continue

            clip = _centered_modal_clip(bounds, viewport)
            with mask_sensitive_page(page):
                page.screenshot(path=str(path), clip=clip)
            logger.info("Saved centered modal screenshot: %s using selector %s", path, selector)
            return path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save centered modal screenshot %s with selector %s: %s",
                path,
                selector,
                exc,
            )

    return None


def _centered_modal_clip(
    bounds: dict[str, float],
    viewport: dict[str, int],
) -> dict[str, float]:
    aspect_ratio = 2160 / 1800
    viewport_width = float(viewport["width"])
    viewport_height = float(viewport["height"])
    modal_width = max(float(bounds["width"]), 1)
    modal_height = max(float(bounds["height"]), 1)

    target_width = max(1080.0, modal_width + 96.0, (modal_height + 96.0) * aspect_ratio)
    target_height = target_width / aspect_ratio
    if target_width > viewport_width:
        target_width = viewport_width
        target_height = target_width / aspect_ratio
    if target_height > viewport_height:
        target_height = viewport_height
        target_width = target_height * aspect_ratio

    center_x = float(bounds["x"]) + modal_width / 2
    center_y = float(bounds["y"]) + modal_height / 2
    x = max(0.0, min(center_x - target_width / 2, viewport_width - target_width))
    y = max(0.0, min(center_y - target_height / 2, viewport_height - target_height))

    return {
        "x": round(x, 3),
        "y": round(y, 3),
        "width": round(target_width, 3),
        "height": round(target_height, 3),
    }


def save_revealed_centered_modal_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
    *,
    ready_check: Callable[[object], bool] | None = None,
) -> Path | None:
    path = _artifact_path(settings, label)
    path.parent.mkdir(parents=True, exist_ok=True)

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() == 0:
                continue
            locator.evaluate(
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
                            changed.push({node, style: node.getAttribute("style")});
                            node.style.setProperty("display", "block", "important");
                            node.style.setProperty("visibility", "visible", "important");
                            node.style.setProperty("opacity", "1", "important");
                        }
                    }
                    window.__appointmentBotRevealedCenteredModal = changed;
                }"""
            )
            locator.scroll_into_view_if_needed(timeout=5_000)
            if ready_check is not None and not ready_check(locator):
                logger.warning(
                    "Revealed modal was not ready for screenshot using selector %s",
                    selector,
                )
                continue
            bounds = locator.bounding_box()
            viewport = page.viewport_size
            if bounds is None or viewport is None:
                continue
            clip = _centered_modal_clip(bounds, viewport)
            with mask_sensitive_page(page):
                page.screenshot(path=str(path), clip=clip)
            logger.info("Saved revealed centered modal screenshot: %s", path)
            return path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save revealed centered modal screenshot %s: %s",
                path,
                exc,
            )
        finally:
            try:
                page.evaluate(
                    """() => {
                        const changed = window.__appointmentBotRevealedCenteredModal || [];
                        changed.forEach(item => {
                            if (item.style === null) item.node.removeAttribute("style");
                            else item.node.setAttribute("style", item.style);
                        });
                        delete window.__appointmentBotRevealedCenteredModal;
                    }"""
                )
            except PlaywrightError:
                logger.warning("Could not restore centered modal styles after screenshot")

    return None


def save_error_screenshot(page: Page, settings: Settings, label: str = "error") -> Path | None:
    if not settings.screenshot_on_error:
        return None

    return save_screenshot(page, settings, label)


def save_result_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str] | None = None,
) -> Path | None:
    if not settings.screenshot_on_relevant_result:
        return None

    if selectors:
        path = save_element_screenshot(page, settings, label, selectors)
        if path is not None:
            return path

    if selectors:
        logger.warning("Could not find result element; saving full-page screenshot instead")

    return save_screenshot(page, settings, label)
