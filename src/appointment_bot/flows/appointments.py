import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings
from appointment_bot.services.captcha import solve_normal_captcha

logger = logging.getLogger(__name__)

PROGRAM_ACTION_SELECTOR = (
    'input[type="image"][onclick*="__doPostBack"][onclick*="gvProgramacion"][onclick*="accion$0"]'
)
RESERVE_APPOINTMENT_SELECTOR = "input#MainContent_btnCita"
RESERVE_APPOINTMENT_POSTBACK_TARGET = "ctl00$MainContent$btnCita"
SITE_SELECTOR = "#MainContent_idUcitas_cbosede"
DATE_SELECTOR = "#MainContent_idUcitas_cboFecha"
HOUR_SELECTOR = "#MainContent_idUcitas_cboHora"
RESERVATION_FIELD_SELECTOR = "#MainContent_idUcitas_txtimg"
RESERVATION_BUTTON_SELECTOR = "#MainContent_idUcitas_btgSiguiente"
APPOINTMENT_PANEL_SCREENSHOT_SELECTORS = [
    ".modal:has(#MainContent_idUcitas_cbosede)",
    ".ui-dialog:has(#MainContent_idUcitas_cbosede)",
    "[role='dialog']:has(#MainContent_idUcitas_cbosede)",
    "#MainContent_idUcitas",
    "fieldset:has(#MainContent_idUcitas_cbosede)",
    "table:has(#MainContent_idUcitas_cbosede)",
]

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


class AppointmentWorkflowUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class AppointmentSnapshot:
    site_options: list[str]
    date_options: list[str]
    hour_options: list[str]
    site: str
    date: str
    hour: str
    slots: str
    person_name: str

    def signature(self) -> tuple[str, ...]:
        return (
            "|".join(self.site_options),
            "|".join(self.date_options),
            "|".join(self.hour_options),
            self.site,
            self.date,
            self.hour,
            self.slots,
            self.person_name,
        )


def click_program_action(page: Page) -> Page:
    logger.info("Clicking program action button")
    button = page.locator(PROGRAM_ACTION_SELECTOR)
    button_count = button.count()
    logger.info("Program action buttons found: %s", button_count)

    if button_count == 0:
        raise AppointmentWorkflowUnavailable(
            "No se encontro una accion de programacion disponible. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
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

    try:
        page.locator(RESERVE_APPOINTMENT_SELECTOR).wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise AppointmentWorkflowUnavailable(
            "No se encontro el boton para abrir el panel de citas. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        ) from exc


def open_appointment_panel(page: Page) -> Page:
    logger.info("Opening appointment availability panel")
    button = page.locator(RESERVE_APPOINTMENT_SELECTOR)
    button_count = button.count()
    logger.info("Appointment panel buttons found: %s", button_count)

    if button_count == 0:
        raise AppointmentWorkflowUnavailable(
            "No se encontro el boton para abrir el panel de citas. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        )

    button.first.scroll_into_view_if_needed(timeout=15_000)
    button.first.click(timeout=15_000)
    _wait_for_reservation_panel(page)

    logger.info("Current page after opening appointment panel: %s", page.url)
    return page


def _wait_for_reservation_panel(page: Page) -> None:
    try:
        _wait_for_reservation_controls(page, timeout=5_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Reservation panel did not appear after click; trying ASP.NET postback")

    _trigger_reserve_appointment_postback(page)
    try:
        _wait_for_reservation_controls(page, timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise AppointmentWorkflowUnavailable(
            "No se encontraron controles de sede, fecha y hora. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        ) from exc


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
        raise AppointmentWorkflowUnavailable(
            "No se encontro una sede seleccionable. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        )

    logger.info("Selecting site: %s", selected["text"])
    site_select.select_option(value=selected["value"], timeout=15_000)
    site_select.dispatch_event("change", timeout=15_000)
    _wait_for_appointment_options(page)
    logger.info("Current page after site selection: %s", page.url)
    return page


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


def solve_reservation_captcha_and_click_reserve(page: Page, settings: Settings) -> Page:
    captcha_path = _save_reservation_panel_image(page, settings)
    captcha_solution = solve_normal_captcha(captcha_path, settings)

    logger.info("Filling reservation captcha field")
    reservation_field = page.locator(RESERVATION_FIELD_SELECTOR).first
    reservation_field.wait_for(state="visible", timeout=15_000)
    reservation_field.fill(captcha_solution, timeout=15_000)

    logger.info("Clicking reservation button")
    reserve_button = page.locator(RESERVATION_BUTTON_SELECTOR).first
    reserve_button.wait_for(state="visible", timeout=15_000)
    reserve_button.scroll_into_view_if_needed(timeout=15_000)
    reserve_button.click(timeout=15_000)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except PlaywrightTimeoutError:
        logger.info("Reservation click did not trigger domcontentloaded before timeout")

    logger.info("Current page after reservation click: %s", page.url)
    return page


def _save_reservation_panel_image(page: Page, settings: Settings) -> Path:
    logger.info("Saving reservation panel image for captcha solving")
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    captcha_path = settings.screenshots_dir / (
        f"reservation-panel-captcha-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    )

    page.locator(RESERVATION_FIELD_SELECTOR).first.wait_for(state="visible", timeout=15_000)
    for selector in APPOINTMENT_PANEL_SCREENSHOT_SELECTORS:
        panel = page.locator(selector).first
        try:
            if panel.count() == 0:
                continue

            panel.scroll_into_view_if_needed(timeout=5_000)
            panel.screenshot(path=str(captcha_path), timeout=10_000)
            logger.info(
                "Saved reservation panel image: %s using selector %s", captcha_path, selector
            )
            return captcha_path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save reservation panel image with selector %s: %s",
                selector,
                exc,
            )

    raise RuntimeError("Could not save the reservation panel image for captcha solving.")


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
        person_name=_read_person_name(page),
    )


def _snapshot_details(snapshot: AppointmentSnapshot) -> dict[str, str]:
    details = {
        "sede": _real_or_selected(snapshot.site, snapshot.site_options),
        "fecha": _real_or_selected(snapshot.date, snapshot.date_options),
        "hora": _real_or_selected(snapshot.hour, snapshot.hour_options),
        "cupos": snapshot.slots,
        "nombre": snapshot.person_name,
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


def _read_person_name(page: Page) -> str:
    return page.evaluate(
        """() => {
            const normalize = value => (value || "").trim();
            const normalizeKey = value => normalize(value).toLowerCase();
            const visibleValue = element => {
                const value = normalize(element.value || element.innerText || element.textContent);
                if (!value || value.length > 120) return "";
                return value;
            };
            const fieldKey = element => normalizeKey([
                element.id,
                element.name,
                element.placeholder,
                element.getAttribute("aria-label")
            ].join(" "));
            const controls = Array.from(document.querySelectorAll("input, textarea"))
                .filter(element => {
                    const type = normalizeKey(element.type);
                    return !["hidden", "password", "submit", "button", "image"].includes(type);
                });

            const findControlValue = parts => {
                const control = controls.find(element => {
                    const key = fieldKey(element);
                    return parts.some(part => key.includes(part)) && visibleValue(element);
                });
                return control ? visibleValue(control) : "";
            };

            const names = findControlValue(["nombres", "nombre"]);
            const paternal = findControlValue(["paterno"]);
            const maternal = findControlValue(["materno"]);
            const surname = findControlValue(["apellidos", "apellido"]);
            const controlName = [names, paternal || surname, maternal]
                .filter(Boolean)
                .join(" ")
                .replace(/\\s+/g, " ")
                .trim();
            if (controlName) return controlName;

            const bodyText = normalize(document.body ? document.body.innerText : "");
            const lines = bodyText.split("\\n").map(line => normalize(line)).filter(Boolean);
            const valueAfterLabel = labels => {
                for (const label of labels) {
                    const normalizedLabel = label.toLowerCase();
                    for (let index = 0; index < lines.length; index += 1) {
                        const line = lines[index];
                        const lowerLine = line.toLowerCase();
                        if (lowerLine === normalizedLabel && lines[index + 1]) {
                            return lines[index + 1];
                        }
                        if (lowerLine.startsWith(`${normalizedLabel}:`)) {
                            return normalize(line.slice(label.length + 1));
                        }
                    }
                }
                return "";
            };

            const textNames = valueAfterLabel(["Nombres", "Nombre"]);
            const textPaternal = valueAfterLabel(["Apellido Paterno", "Paterno"]);
            const textMaternal = valueAfterLabel(["Apellido Materno", "Materno"]);
            const textSurname = valueAfterLabel(["Apellidos", "Apellido"]);
            return [textNames, textPaternal || textSurname, textMaternal]
                .filter(Boolean)
                .join(" ")
                .replace(/\\s+/g, " ")
                .trim();
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
