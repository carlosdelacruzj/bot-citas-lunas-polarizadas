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
FINAL_CONFIRMATION_SELECTOR = (
    'button:has-text("Confirmar"), input[type="submit"][value*="Confirmar"], '
    'button:has-text("Guardar"), input[type="submit"][value*="Guardar"], '
    'button:has-text("Reservar"), input[type="submit"][value*="Reservar"], '
    'button:has-text("Finalizar"), input[type="submit"][value*="Finalizar"]'
)

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
    details: dict[str, str] | None = None


@dataclass(frozen=True)
class AppointmentSnapshot:
    site_options: list[str]
    date_options: list[str]
    hour_options: list[str]
    site: str
    date: str
    hour: str
    slots: str

    def signature(self) -> tuple[str, ...]:
        return (
            "|".join(self.site_options),
            "|".join(self.date_options),
            "|".join(self.hour_options),
            self.site,
            self.date,
            self.hour,
            self.slots,
        )


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


def open_appointment_panel(page: Page) -> Page:
    logger.info("Opening appointment availability panel")
    button = page.locator(RESERVE_APPOINTMENT_SELECTOR)
    button_count = button.count()
    logger.info("Appointment panel buttons found: %s", button_count)

    if button_count == 0:
        raise RuntimeError(
            "Could not find the appointment panel button. "
            "Review RESERVE_APPOINTMENT_SELECTOR in flows/appointments.py."
        )

    button.first.scroll_into_view_if_needed(timeout=15_000)
    button.first.click(timeout=15_000)
    _wait_for_reservation_panel(page)
    assert_no_final_confirmation_action(page)

    logger.info("Current page after opening appointment panel: %s", page.url)
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
    assert_no_final_confirmation_action(page)
    logger.info("Current page after site selection: %s", page.url)
    return page


def assert_no_final_confirmation_action(page: Page) -> None:
    final_actions = page.locator(FINAL_CONFIRMATION_SELECTOR)
    count = final_actions.count()
    if count == 0:
        logger.info("No final confirmation action is visible")
        return

    visible_labels = final_actions.evaluate_all(
        """elements => elements
            .filter(element => {
                const style = window.getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.visibility !== "hidden"
                    && style.display !== "none"
                    && rect.width > 0
                    && rect.height > 0;
            })
            .map(element => (
                element.innerText || element.value || element.id || element.name
            ).trim())
            .filter(Boolean)
        """
    )
    if visible_labels:
        logger.warning(
            "Final confirmation actions are visible and will not be clicked: %s",
            visible_labels,
        )


def read_appointment_availability(page: Page) -> AvailabilityResult:
    logger.info("Checking appointment availability")
    page.wait_for_load_state("domcontentloaded", timeout=30_000)

    snapshot = _read_stable_appointment_snapshot(page)
    result = _availability_result_from_snapshot(page, snapshot)
    if result.status != "partial":
        return result

    logger.info("Partial availability detected; rechecking before notifying")
    page.wait_for_timeout(1_500)
    snapshot = _read_stable_appointment_snapshot(page)
    return _availability_result_from_snapshot(page, snapshot)


def _availability_result_from_snapshot(
    page: Page,
    snapshot: AppointmentSnapshot,
) -> AvailabilityResult:
    date_options = snapshot.date_options
    hour_options = snapshot.hour_options

    has_date_options = _has_real_options(date_options)
    has_hour_options = _has_real_options(hour_options)
    details = _snapshot_details(snapshot)

    if has_date_options and has_hour_options:
        return AvailabilityResult(
            status="available",
            message="Se detectaron opciones seleccionables de fecha y hora.",
            details=details,
        )

    if has_date_options and not has_hour_options:
        return AvailabilityResult(
            status="partial",
            message="Se detecto fecha disponible, pero aun no hay hora seleccionable.",
            details=details,
        )

    if has_hour_options and not has_date_options:
        return AvailabilityResult(
            status="partial",
            message="Se detecto hora disponible, pero no se detecto fecha seleccionable.",
            details=details,
        )

    if _only_no_slots(date_options) and _only_no_slots(hour_options):
        return AvailabilityResult(
            status="unavailable",
            message="La pagina muestra 'Sin Cupos' en fecha y hora.",
            details=details,
        )

    content = page.locator("body").inner_text(timeout=15_000).lower()

    if any(text in content for text in AVAILABLE_TEXTS):
        return AvailabilityResult(
            status="available",
            message="Se detecto texto compatible con cupo disponible.",
            details=details,
        )

    if any(text in content for text in UNAVAILABLE_TEXTS):
        return AvailabilityResult(
            status="unavailable",
            message="Se detecto texto compatible con falta de cupos.",
            details=details,
        )

    return AvailabilityResult(
        status="unknown",
        message=(
            "No se pudo determinar la disponibilidad con los textos actuales. "
            "Ajusta AVAILABLE_TEXTS o UNAVAILABLE_TEXTS en flows/appointments.py."
        ),
        details=details,
    )


def _read_stable_appointment_snapshot(page: Page) -> AppointmentSnapshot:
    previous_snapshot: AppointmentSnapshot | None = None
    current_snapshot: AppointmentSnapshot | None = None
    for attempt in range(1, 5):
        current_snapshot = _read_appointment_snapshot(page)
        logger.info("Appointment snapshot %s: %s", attempt, _snapshot_details(current_snapshot))
        logger.info("Date options: %s", current_snapshot.date_options)
        logger.info("Hour options: %s", current_snapshot.hour_options)

        if (
            previous_snapshot is not None
            and current_snapshot.signature() == previous_snapshot.signature()
        ):
            return current_snapshot

        previous_snapshot = current_snapshot
        page.wait_for_timeout(750)

    if current_snapshot is None:
        raise RuntimeError("Could not read appointment availability controls.")
    return current_snapshot


def _read_appointment_snapshot(page: Page) -> AppointmentSnapshot:
    site_options = _select_options_text(page, SITE_SELECTOR)
    date_options = _select_options_text(page, DATE_SELECTOR)
    hour_options = _select_options_text(page, HOUR_SELECTOR)
    return AppointmentSnapshot(
        site_options=site_options,
        date_options=date_options,
        hour_options=hour_options,
        site=_selected_option_text(page, SITE_SELECTOR),
        date=_selected_option_text(page, DATE_SELECTOR),
        hour=_selected_option_text(page, HOUR_SELECTOR),
        slots=_read_slots_value(page),
    )


def _snapshot_details(snapshot: AppointmentSnapshot) -> dict[str, str]:
    details = {
        "sede": _real_or_selected(snapshot.site, snapshot.site_options),
        "fecha": _real_or_selected(snapshot.date, snapshot.date_options),
        "hora": _real_or_selected(snapshot.hour, snapshot.hour_options),
        "cupos": snapshot.slots,
    }
    return {key: value for key, value in details.items() if value}


def _real_or_selected(selected: str, options: list[str]) -> str:
    if selected and _has_real_options([selected]):
        return selected
    return next((option for option in options if _has_real_options([option])), selected)


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


def _selected_option_text(page: Page, selector: str) -> str:
    select = page.locator(selector)
    if select.count() == 0:
        return ""

    return select.evaluate(
        """element => {
            const selected = element.options[element.selectedIndex];
            return selected ? selected.innerText.trim() : "";
        }"""
    )


def _read_slots_value(page: Page) -> str:
    return page.evaluate(
        """() => {
            const normalize = value => (value || "").trim().toLowerCase();
            const directInput = Array.from(document.querySelectorAll("input")).find(input => {
                const id = normalize(input.id);
                const name = normalize(input.name);
                return id.includes("cupo") || name.includes("cupo");
            });
            if (directInput && directInput.value.trim()) {
                return directInput.value.trim();
            }

            const labels = Array.from(document.querySelectorAll("label, span, th, td, div"));
            const cuposLabel = labels.find(element => normalize(element.innerText) === "cupos");
            if (!cuposLabel) {
                return "";
            }

            const container = cuposLabel.closest("tr, .row, div, fieldset, table") || document.body;
            const nearbyInput = Array.from(container.querySelectorAll("input")).find(
                input => input.value.trim()
            );
            return nearbyInput ? nearbyInput.value.trim() : "";
        }"""
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
