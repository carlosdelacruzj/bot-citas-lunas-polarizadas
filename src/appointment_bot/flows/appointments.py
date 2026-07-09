import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.flows.appointment_reader import read_appointment_availability
from appointment_bot.flows.appointment_selection import (
    has_available_date_options,
    select_available_appointment,
    validate_selected_appointment,
)
from appointment_bot.utils.sanitization import normalize_option

logger = logging.getLogger(__name__)

__all__ = [
    "APPOINTMENT_PANEL_SCREENSHOT_SELECTORS",
    "AppointmentOptionsNotRefreshed",
    "AppointmentWorkflowCancelled",
    "AppointmentWorkflowUnavailable",
    "ReservationDeferredForPriority",
    "ReservationSubmissionUncertain",
    "has_available_date_options",
    "open_appointment_panel",
    "open_hidden_appointment_panel_for_observer",
    "read_appointment_availability",
    "select_available_appointment",
    "select_available_site",
    "select_available_site_for_observer",
    "validate_selected_appointment",
]

RESERVE_APPOINTMENT_SELECTOR = "input#MainContent_btnCita"
RESERVE_APPOINTMENT_POSTBACK_TARGET = "ctl00$MainContent$btnCita"
SITE_SELECTOR = "#MainContent_idUcitas_cbosede"
DATE_SELECTOR = "#MainContent_idUcitas_cboFecha"
HOUR_SELECTOR = "#MainContent_idUcitas_cboHora"
SLOTS_LABEL_ID = "MainContent_idUcitas_lblcupos"
APPOINTMENT_PANEL_SCREENSHOT_SELECTORS = [
    (
        "xpath=//*[@id='MainContent_idUcitas_cbosede']"
        "/ancestor::*[.//*[@id='MainContent_idUcitas_btgSiguiente']][1]"
    ),
    ".modal:has(#MainContent_idUcitas_cbosede)",
    ".ui-dialog:has(#MainContent_idUcitas_cbosede)",
    "[role='dialog']:has(#MainContent_idUcitas_cbosede)",
    "#MainContent_idUcitas",
    "fieldset:has(#MainContent_idUcitas_cbosede)",
    "table:has(#MainContent_idUcitas_cbosede)",
]
PROCESS_STAGES_SCREENSHOT_SELECTORS = [
    "table:has-text('Separa Cita Peritaje')",
    "table:has-text('Ingresa Solicitud')",
    "xpath=//*[normalize-space()='Etapas Trámite']/following-sibling::*[1]",
    "xpath=//*[normalize-space()='Etapas Tramite']/following-sibling::*[1]",
    "xpath=//*[normalize-space()='Etapas Tràmite']/following-sibling::*[1]",
    (
        "xpath=//*[contains(normalize-space(), 'Etapas') "
        "and contains(normalize-space(), 'Trámite')]/following-sibling::*[1]"
    ),
    (
        "xpath=//*[contains(normalize-space(), 'Etapas') "
        "and contains(normalize-space(), 'Tramite')]/following-sibling::*[1]"
    ),
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


class AppointmentWorkflowUnavailable(RuntimeError):
    pass


class AppointmentWorkflowCancelled(RuntimeError):
    pass


class ReservationDeferredForPriority(RuntimeError):
    def __init__(self, message: str, captcha_audit: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.captcha_audit = captcha_audit or {}


class ReservationSubmissionUncertain(RuntimeError):
    pass


class AppointmentOptionsNotRefreshed(RuntimeError):
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


@dataclass(frozen=True)
class SiteRefreshEvidence:
    selected_site: str
    confirmed: bool
    changed: bool
    marker_cleared: bool
    async_completed: bool
    elapsed_ms: int
    date_signature_before: str
    date_signature_after: str
    hour_signature_before: str
    hour_signature_after: str

    def details(self) -> dict[str, Any]:
        return {
            "site_refresh_selected_site": self.selected_site,
            "site_refresh_confirmed": self.confirmed,
            "site_refresh_changed": self.changed,
            "site_refresh_marker_cleared": self.marker_cleared,
            "site_refresh_async_completed": self.async_completed,
            "site_refresh_elapsed_ms": self.elapsed_ms,
            "site_refresh_date_signature_before": self.date_signature_before,
            "site_refresh_date_signature_after": self.date_signature_after,
            "site_refresh_hour_signature_before": self.hour_signature_before,
            "site_refresh_hour_signature_after": self.hour_signature_after,
        }


def open_appointment_panel(page: Page) -> Page:
    return _open_appointment_panel(page, allow_hidden=False)


def open_hidden_appointment_panel_for_observer(page: Page) -> Page:
    return _open_appointment_panel(page, allow_hidden=True)


def _open_appointment_panel(page: Page, *, allow_hidden: bool) -> Page:
    logger.info("Opening appointment availability panel")
    button = page.locator(RESERVE_APPOINTMENT_SELECTOR)
    button_count = button.count()
    logger.debug("Appointment panel buttons found: %s", button_count)

    if button_count == 0:
        if allow_hidden:
            raise AppointmentWorkflowUnavailable(
                "No se encontro el boton oculto de citas para ejecutar el modo observador."
            )
        raise AppointmentWorkflowUnavailable(
            "No se encontro el boton para abrir el panel de citas. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        )

    if allow_hidden:
        # El observador activa solo el postback de consulta: no muestra el
        # modal, resuelve captcha ni pulsa el boton final de reserva.
        button.evaluate("element => element.click()")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except PlaywrightTimeoutError:
            logger.debug("Hidden appointment button did not trigger a page load")
        try:
            _wait_for_reservation_controls_attached(page, timeout=15_000)
        except PlaywrightTimeoutError as exc:
            raise AppointmentWorkflowUnavailable(
                "El postback oculto no entrego los controles de sede, fecha y hora."
            ) from exc
        return page

    try:
        button.first.wait_for(state="visible", timeout=5_000)
        button.first.scroll_into_view_if_needed(timeout=15_000)
        button.first.click(timeout=15_000)
    except PlaywrightTimeoutError as exc:
        raise AppointmentWorkflowUnavailable(
            "El boton para abrir el panel de citas existe, pero no esta visible. "
            "Es posible que la etapa de cita no este pendiente."
        ) from exc

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
    _wait_for_reservation_controls_attached(page, timeout=timeout)


def _wait_for_reservation_controls_attached(page: Page, *, timeout: int) -> None:
    page.locator(SITE_SELECTOR).wait_for(state="attached", timeout=timeout)
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


def select_available_site(
    page: Page,
    *,
    required_site: str | None = None,
    timeout: int = 15_000,
) -> Page:
    return _select_available_site(
        page,
        timeout=timeout,
        allow_hidden=False,
        required_site=required_site,
    )


def select_available_site_for_observer(
    page: Page,
    *,
    required_site: str | None = None,
    timeout: int = 15_000,
) -> Page:
    return _select_available_site(
        page,
        timeout=timeout,
        allow_hidden=True,
        required_site=required_site,
    )


def _select_available_site(
    page: Page,
    *,
    timeout: int,
    allow_hidden: bool,
    required_site: str | None,
) -> Page:
    logger.info("Selecting available site")
    site_select = page.locator(SITE_SELECTOR)
    site_select.wait_for(state="attached" if allow_hidden else "visible", timeout=timeout)
    options = _select_options(page, SITE_SELECTOR)
    logger.debug("Site options: %s", [option["text"] for option in options])
    selected = _select_site_option(options, required_site=required_site)
    if selected is None:
        message = _missing_site_message(
            options, allow_hidden=allow_hidden, required_site=required_site
        )
        raise AppointmentWorkflowUnavailable(message)

    logger.info("Selecting site: %s", selected["text"])
    refresh_token = _mark_select_for_refresh(page, SITE_SELECTOR)
    async_refresh_token = _mark_aspnet_async_refresh(page)
    previous_date = _options_signature(_select_options(page, DATE_SELECTOR))
    previous_hour = _options_signature(_select_options(page, HOUR_SELECTOR))
    if allow_hidden:
        # El cambio del select oculto reproduce solo el postback de consulta.
        site_select.evaluate(
            """(element, value) => {
                element.value = value;
                element.dispatchEvent(new Event("change", { bubbles: true }));
            }""",
            selected["value"],
        )
    else:
        site_select.select_option(value=selected["value"], timeout=timeout)
    evidence = _wait_for_appointment_options(
        page,
        selected_site=selected["text"],
        refresh_token=refresh_token,
        async_refresh_token=async_refresh_token,
        previous_date_signature=previous_date,
        previous_hour_signature=previous_hour,
        timeout=timeout,
    )
    _store_site_refresh_evidence(page, evidence)
    logger.info(
        "Site refresh evidence: site=%s confirmed=%s changed=%s async=%s "
        "elapsed_ms=%s date_before=%s date_after=%s hour_before=%s hour_after=%s",
        evidence.selected_site,
        evidence.confirmed,
        evidence.changed,
        evidence.async_completed,
        evidence.elapsed_ms,
        evidence.date_signature_before,
        evidence.date_signature_after,
        evidence.hour_signature_before,
        evidence.hour_signature_after,
    )
    logger.debug("Current page after site selection: %s", page.url)
    return page


def _select_options_text(page: Page, selector: str) -> list[str]:
    return [option["text"] for option in _select_options(page, selector) if option["text"]]


def _select_options(page: Page, selector: str) -> list[dict[str, Any]]:
    select = page.locator(selector)
    if select.count() == 0:
        return []

    return select.locator("option").evaluate_all(
        """options => options.map(option => ({
            text: option.innerText.trim(),
            value: option.value,
            disabled: option.disabled,
            hidden: option.hidden
        }))"""
    )


def _select_appointment_option(locator, value: str, *, allow_hidden: bool) -> None:
    if not allow_hidden:
        locator.select_option(value=value, timeout=15_000)
        return

    # Solo el observador usa esta rama para consultar selects ocultos.
    # El evento change puede cargar datos, pero no ejecuta captcha ni reserva.
    locator.evaluate(
        """(element, optionValue) => {
            element.value = optionValue;
            element.dispatchEvent(new Event("change", { bubbles: true }));
        }""",
        value,
    )


def _real_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [option for option in options if _is_real_appointment_option(option)]


def _options_signature(options: list[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    return tuple((option["value"], option["text"]) for option in options)


def _format_options_signature(signature: tuple[tuple[str, str], ...]) -> str:
    return "|".join(f"{value}:{text}" for value, text in signature)


def _store_site_refresh_evidence(page: Page, evidence: SiteRefreshEvidence) -> None:
    page.evaluate(
        """evidence => {
            window.__appointmentBotLastSiteRefresh = evidence;
        }""",
        evidence.details(),
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
            const directLabel = document.getElementById("MainContent_idUcitas_lblcupos");
            if (directLabel && directLabel.textContent.trim()) {
                return directLabel.textContent.trim();
            }

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
            if (nearbyInput) {
                return nearbyInput.value.trim();
            }

            const numericText = Array.from(container.querySelectorAll("span, label, div, td"))
                .map(element => (element.textContent || "").trim())
                .find(text => /^\\d+$/.test(text));
            return numericText || "";
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


def _is_real_site_option(option: dict[str, Any]) -> bool:
    normalized = str(option["text"]).strip().lower()
    return (
        bool(option.get("value"))
        and not option.get("disabled")
        and not option.get("hidden")
        and bool(normalized)
        and not normalized.startswith("seleccione")
        and normalized != "sin cupos"
    )


def _select_site_option(
    options: list[dict[str, Any]],
    *,
    required_site: str | None,
) -> dict[str, Any] | None:
    real_options = [option for option in options if _is_real_site_option(option)]
    if not required_site:
        return real_options[0] if real_options else None

    required = normalize_option(required_site)
    return next(
        (
            option
            for option in real_options
            if normalize_option(str(option.get("text") or "")) == required
        ),
        None,
    )


def _missing_site_message(
    options: list[dict[str, Any]],
    *,
    allow_hidden: bool,
    required_site: str | None,
) -> str:
    available_sites = [
        str(option.get("text") or "").strip() for option in options if _is_real_site_option(option)
    ]
    if required_site:
        suffix = (
            f" Sedes encontradas: {', '.join(available_sites)}."
            if available_sites
            else " No hay sedes seleccionables en el formulario."
        )
        return f"No se encontro la sede requerida {required_site!r}.{suffix}"

    if allow_hidden:
        return "El observador no encontro una sede seleccionable."
    return (
        "No se encontro una sede seleccionable. Es posible que la cita ya este "
        "reservada o que ya no exista un flujo pendiente."
    )


def _wait_for_appointment_options(
    page: Page,
    *,
    selected_site: str,
    refresh_token: str,
    async_refresh_token: str | None,
    previous_date_signature: tuple[tuple[str, str], ...],
    previous_hour_signature: tuple[tuple[str, str], ...],
    timeout: int = 15_000,
) -> SiteRefreshEvidence:
    started = time.monotonic()
    try:
        page.wait_for_load_state("load", timeout=min(timeout, 10_000))
    except PlaywrightTimeoutError:
        logger.info("Site selection page did not reach load state; checking appointment options")

    page.locator(DATE_SELECTOR).wait_for(state="attached", timeout=timeout)
    page.locator(HOUR_SELECTOR).wait_for(state="attached", timeout=timeout)
    deadline = time.monotonic() + timeout / 1_000
    last_pair = None
    stable_reads = 0
    refreshed = False
    marker_cleared = False
    async_completed = False
    current_date: tuple[tuple[str, str], ...] = ()
    current_hour: tuple[tuple[str, str], ...] = ()
    while time.monotonic() < deadline:
        current_date = _options_signature(_select_options(page, DATE_SELECTOR))
        current_hour = _options_signature(_select_options(page, HOUR_SELECTOR))
        marker_present = page.locator(
            f'{SITE_SELECTOR}[data-appointment-bot-refresh="{refresh_token}"]'
        ).count()
        async_request_completed = (
            _aspnet_async_refresh_completed(page, async_refresh_token)
            if async_refresh_token is not None
            else False
        )
        marker_cleared = marker_cleared or marker_present == 0
        async_completed = async_completed or async_request_completed
        refreshed = (
            refreshed
            or marker_cleared
            or async_completed
            or (current_date != previous_date_signature or current_hour != previous_hour_signature)
        )
        pair = (current_date, current_hour)
        stable_reads = stable_reads + 1 if pair == last_pair else 1
        last_pair = pair
        if refreshed and stable_reads >= 2 and (current_date or current_hour):
            return SiteRefreshEvidence(
                selected_site=selected_site,
                confirmed=True,
                changed=(
                    current_date != previous_date_signature
                    or current_hour != previous_hour_signature
                ),
                marker_cleared=marker_cleared,
                async_completed=async_completed,
                elapsed_ms=round((time.monotonic() - started) * 1_000),
                date_signature_before=_format_options_signature(previous_date_signature),
                date_signature_after=_format_options_signature(current_date),
                hour_signature_before=_format_options_signature(previous_hour_signature),
                hour_signature_after=_format_options_signature(current_hour),
            )
        page.wait_for_timeout(250)
    raise AppointmentOptionsNotRefreshed(
        "La pagina no confirmo que las opciones de cita se actualizaran despues de elegir sede."
    )


def _wait_for_options_after_selection(
    page: Page,
    selector: str,
    *,
    previous_signature: tuple[tuple[str, str], ...],
    require_change: bool,
    timeout: int,
) -> list[dict[str, str]]:
    deadline = time.monotonic() + timeout / 1_000
    last_signature = None
    stable_reads = 0
    changed = False
    current_options: list[dict[str, Any]] = []

    while time.monotonic() < deadline:
        current_options = _select_options(page, selector)
        current_signature = _options_signature(current_options)
        changed = changed or current_signature != previous_signature
        if current_signature == last_signature:
            stable_reads += 1
        else:
            stable_reads = 1
            last_signature = current_signature

        has_real_options = _has_real_options([option["text"] for option in current_options])
        if stable_reads >= 2 and has_real_options and (changed or not require_change):
            return current_options

        page.wait_for_timeout(250)

    return current_options if changed or not require_change else []


def _has_real_options(options: list[str]) -> bool:
    return any(_is_real_appointment_option(option) for option in options)


def _is_real_appointment_option(option: dict[str, Any] | str) -> bool:
    if isinstance(option, str):
        text = option
        value_present = True
        disabled = False
        hidden = False
    else:
        text = str(option.get("text") or "")
        value_present = bool(option.get("value"))
        disabled = bool(option.get("disabled"))
        hidden = bool(option.get("hidden"))
    normalized = text.strip().lower()
    return (
        value_present
        and not disabled
        and not hidden
        and bool(normalized)
        and normalized != "sin cupos"
        and not normalized.startswith("seleccione")
    )


def _mark_select_for_refresh(page: Page, selector: str) -> str:
    token = uuid.uuid4().hex
    page.locator(selector).evaluate(
        "(element, value) => { element.dataset.appointmentBotRefresh = value; }",
        token,
    )
    return token


def _mark_aspnet_async_refresh(page: Page) -> str | None:
    return page.evaluate(
        """() => {
            if (!window.Sys || !Sys.WebForms || !Sys.WebForms.PageRequestManager) {
                return null;
            }
            const prm = Sys.WebForms.PageRequestManager.getInstance();
            if (!prm) return null;
            const token = `${Date.now()}-${Math.random()}`;
            window.__appointmentBotAsyncRefreshes = window.__appointmentBotAsyncRefreshes || {};
            window.__appointmentBotAsyncRefreshes[token] = false;
            const handler = function () {
                window.__appointmentBotAsyncRefreshes[token] = true;
                try {
                    prm.remove_endRequest(handler);
                } catch (error) {}
            };
            prm.add_endRequest(handler);
            return token;
        }"""
    )


def _aspnet_async_refresh_completed(page: Page, token: str) -> bool:
    return bool(
        page.evaluate(
            """token => Boolean(
                window.__appointmentBotAsyncRefreshes
                && window.__appointmentBotAsyncRefreshes[token]
            )""",
            token,
        )
    )


def _same_option(actual: str, expected: str) -> bool:
    return normalize_option(actual) == normalize_option(expected)
