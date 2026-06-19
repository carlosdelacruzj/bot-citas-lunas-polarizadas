import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)


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
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    path = settings.screenshots_dir / filename
    try:
        with mask_sensitive_page(page):
            page.screenshot(path=str(path), full_page=True)
        logger.info("Saved screenshot: %s", path)
        return path
    except PlaywrightError as exc:
        logger.warning("Could not save screenshot %s: %s", path, exc)
        return None


def save_element_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
) -> Path | None:
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    path = settings.screenshots_dir / filename

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


def save_revealed_element_screenshot(
    page: Page,
    settings: Settings,
    label: str,
    selectors: list[str],
    *,
    ready_check: Callable[[object], bool] | None = None,
) -> Path | None:
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    path = settings.screenshots_dir / filename

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
                        if (style.display === "none" || style.visibility === "hidden") {
                            changed.push({
                                node,
                                style: node.getAttribute("style")
                            });
                            node.style.setProperty("display", "block", "important");
                            node.style.setProperty("visibility", "visible", "important");
                            node.style.setProperty("opacity", "1", "important");
                        }
                    }
                    window.__appointmentBotRevealedElements = changed;
                }"""
            )
            locator.scroll_into_view_if_needed(timeout=5_000)
            if ready_check is not None and not ready_check(locator):
                logger.warning(
                    "Revealed element was not ready for screenshot using selector %s",
                    selector,
                )
                continue
            with mask_sensitive_page(page):
                locator.screenshot(path=str(path), timeout=10_000)
            logger.info("Saved revealed element screenshot: %s using selector %s", path, selector)
            return path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save revealed element screenshot %s with selector %s: %s",
                path,
                selector,
                exc,
            )
        finally:
            try:
                page.evaluate(
                    """() => {
                        const changed = window.__appointmentBotRevealedElements || [];
                        changed.forEach(item => {
                            if (item.style === null) item.node.removeAttribute("style");
                            else item.node.setAttribute("style", item.style);
                        });
                        delete window.__appointmentBotRevealedElements;
                    }"""
                )
            except PlaywrightError:
                logger.warning("Could not restore appointment panel styles after screenshot")

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
