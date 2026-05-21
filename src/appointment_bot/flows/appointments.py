import logging
from dataclasses import dataclass

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

PROGRAM_ACTION_SELECTOR = (
    'input[type="image"][onclick*="__doPostBack"][onclick*="gvProgramacion"][onclick*="accion$0"]'
)
RESERVE_APPOINTMENT_SELECTOR = "input#MainContent_btnCita"
RESERVE_APPOINTMENT_POSTBACK_TARGET = "ctl00$MainContent$btnCita"
SITE_SELECTOR = "#MainContent_idUcitas_cbosede"
DATE_SELECTOR = "#MainContent_idUcitas_cboFecha"
HOUR_SELECTOR = "#MainContent_idUcitas_cboHora"

AVAILABLE_TEXTS = [
    "cupo disponible",
    "citas disponibles",
    "horarios disponibles",
    "seleccione una cita",
    "seleccionar horario",
]

UNAVAILABLE_TEXTS = [
    "no hay cupos",
    "no hay citas",
    "no existen citas",
    "sin cupos",
    "sin disponibilidad",
    "no se encontraron horarios",
]


@dataclass(frozen=True)
class AvailabilityResult:
    status: str
    message: str


def click_program_action(page: Page) -> Page:
    logger.info("Clicking program action button")
    button = page.locator(PROGRAM_ACTION_SELECTOR)
    button_count = button.count()
    logger.info("Program action buttons found: %s", button_count)

    if button_count == 0:
        raise RuntimeError(
            "Could not find the program action button. "
            "Review PROGRAM_ACTION_SELECTOR in flows/appointments.py."
        )

    first_button = button.first
    first_button.scroll_into_view_if_needed(timeout=15_000)

    first_button.click(timeout=15_000)
    _wait_for_program_detail(page)
    logger.info("Current page after program action: %s", page.url)
    return page


def _wait_for_program_detail(page: Page) -> None:
    try:
        page.wait_for_load_state("load", timeout=10_000)
    except PlaywrightTimeoutError:
        logger.info("Program detail page did not reach load state; checking detail selector")

    page.locator(RESERVE_APPOINTMENT_SELECTOR).wait_for(state="visible", timeout=15_000)


def click_reserve_appointment(page: Page) -> Page:
    logger.info("Clicking reserve appointment button")
    button = page.locator(RESERVE_APPOINTMENT_SELECTOR)
    button_count = button.count()
    logger.info("Reserve appointment buttons found: %s", button_count)

    if button_count == 0:
        raise RuntimeError(
            "Could not find the reserve appointment button. "
            "Review RESERVE_APPOINTMENT_SELECTOR in flows/appointments.py."
        )

    button.first.scroll_into_view_if_needed(timeout=15_000)
    button.first.click(timeout=15_000)
    _wait_for_reservation_panel(page)

    logger.info("Current page after reserve appointment action: %s", page.url)
    return page


def _wait_for_reservation_panel(page: Page) -> None:
    try:
        _wait_for_reservation_controls(page, timeout=5_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Reservation panel did not appear after click; trying ASP.NET postback")

    _trigger_reserve_appointment_postback(page)
    _wait_for_reservation_controls(page, timeout=15_000)


def _wait_for_reservation_controls(page: Page, *, timeout: int) -> None:
    page.locator(SITE_SELECTOR).wait_for(state="visible", timeout=timeout)
    page.locator(DATE_SELECTOR).wait_for(state="attached", timeout=timeout)
    page.locator(HOUR_SELECTOR).wait_for(state="attached", timeout=timeout)


def _trigger_reserve_appointment_postback(page: Page) -> None:
    logger.info("Triggering reserve appointment ASP.NET postback")
    page.evaluate(
        """target => {
            if (typeof WebForm_DoPostBackWithOptions === "function"
                && typeof WebForm_PostBackOptions === "function") {
                WebForm_DoPostBackWithOptions(
                    new WebForm_PostBackOptions(target, "", true, "", "", false, false)
                );
                return;
            }

            if (typeof __doPostBack === "function") {
                __doPostBack(target, "");
                return;
            }

            throw new Error("ASP.NET postback helpers are not available.");
        }""",
        RESERVE_APPOINTMENT_POSTBACK_TARGET,
    )


def select_available_site(page: Page) -> Page:
    logger.info("Selecting available site")
    site_select = page.locator(SITE_SELECTOR)
    site_select.wait_for(state="visible", timeout=15_000)

    options = _select_options(page, SITE_SELECTOR)
    logger.info("Site options: %s", [option["text"] for option in options])

    selected = next((option for option in options if _is_real_site_option(option["text"])), None)
    if selected is None:
        raise RuntimeError("Could not find a selectable site option.")

    logger.info("Selecting site: %s", selected["text"])
    site_select.select_option(value=selected["value"], timeout=15_000)
    site_select.dispatch_event("change", timeout=15_000)
    _wait_for_appointment_options(page)
    logger.info("Current page after site selection: %s", page.url)
    return page


def read_appointment_availability(page: Page) -> AvailabilityResult:
    logger.info("Checking appointment availability")
    page.wait_for_load_state("domcontentloaded", timeout=30_000)

    date_options = _select_options_text(page, DATE_SELECTOR)
    hour_options = _select_options_text(page, HOUR_SELECTOR)
    logger.info("Date options: %s", date_options)
    logger.info("Hour options: %s", hour_options)

    has_date_options = _has_real_options(date_options)
    has_hour_options = _has_real_options(hour_options)

    if has_date_options and has_hour_options:
        return AvailabilityResult(
            status="available",
            message="Se detectaron opciones seleccionables de fecha y hora.",
        )

    if has_date_options and not has_hour_options:
        return AvailabilityResult(
            status="partial",
            message="Se detecto fecha disponible, pero aun no hay hora seleccionable.",
        )

    if has_hour_options and not has_date_options:
        return AvailabilityResult(
            status="partial",
            message="Se detecto hora disponible, pero no se detecto fecha seleccionable.",
        )

    if _only_no_slots(date_options) and _only_no_slots(hour_options):
        return AvailabilityResult(
            status="unavailable",
            message="La pagina muestra 'Sin Cupos' en fecha y hora.",
        )

    content = page.locator("body").inner_text(timeout=15_000).lower()

    if any(text in content for text in AVAILABLE_TEXTS):
        return AvailabilityResult(
            status="available",
            message="Se detecto texto compatible con cupo disponible.",
        )

    if any(text in content for text in UNAVAILABLE_TEXTS):
        return AvailabilityResult(
            status="unavailable",
            message="Se detecto texto compatible con falta de cupos.",
        )

    return AvailabilityResult(
        status="unknown",
        message=(
            "No se pudo determinar la disponibilidad con los textos actuales. "
            "Ajusta AVAILABLE_TEXTS o UNAVAILABLE_TEXTS en flows/appointments.py."
        ),
    )


def _select_options_text(page: Page, selector: str) -> list[str]:
    return [option["text"] for option in _select_options(page, selector) if option["text"]]


def _select_options(page: Page, selector: str) -> list[dict[str, str]]:
    select = page.locator(selector)
    if select.count() == 0:
        return []

    return select.locator("option").evaluate_all(
        """options => options.map(option => ({
            text: option.innerText.trim(),
            value: option.value
        }))"""
    )


def _is_real_site_option(text: str) -> bool:
    normalized = text.strip().lower()
    return (
        bool(normalized) and not normalized.startswith("seleccione") and normalized != "sin cupos"
    )


def _wait_for_appointment_options(page: Page) -> None:
    try:
        page.wait_for_load_state("load", timeout=10_000)
    except PlaywrightTimeoutError:
        logger.info("Site selection page did not reach load state; checking appointment options")

    page.locator(DATE_SELECTOR).wait_for(state="attached", timeout=15_000)
    page.locator(HOUR_SELECTOR).wait_for(state="attached", timeout=15_000)
    try:
        page.wait_for_function(
            """selectors => {
                const [dateSelector, hourSelector] = selectors;
                const hasTextOption = selector => {
                    const select = document.querySelector(selector);
                    if (!select) return false;
                    return Array.from(select.options).some(option => option.innerText.trim());
                };
                return hasTextOption(dateSelector) || hasTextOption(hourSelector);
            }""",
            arg=[DATE_SELECTOR, HOUR_SELECTOR],
            timeout=15_000,
        )
    except PlaywrightTimeoutError:
        logger.info("Appointment date/hour options did not populate after site selection")


def _only_no_slots(options: list[str]) -> bool:
    return bool(options) and all(option.lower() == "sin cupos" for option in options)


def _has_real_options(options: list[str]) -> bool:
    ignored = {"", "sin cupos", "seleccione", "seleccione la fecha", "seleccione la hora"}
    return any(option.strip().lower() not in ignored for option in options)
