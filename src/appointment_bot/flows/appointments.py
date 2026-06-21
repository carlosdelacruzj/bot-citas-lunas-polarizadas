import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.utils.sanitization import normalize_option

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
CONFIRMATION_TEXTS = [
    "cita ha sido registrado",
    "cita ha sido registrada",
    "registrado satisfactoriamente",
    "registrada satisfactoriamente",
    "reservada con exito",
    "reservado con exito",
]
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
        page.locator(RESERVE_APPOINTMENT_SELECTOR).wait_for(state="visible", timeout=5_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Reserve button is not visible; checking process stages table")

    try:
        page.get_by_text("Separa Cita Peritaje").wait_for(state="visible", timeout=15_000)
        return
    except PlaywrightTimeoutError:
        logger.info("Process stages table was not detected by Separa Cita Peritaje text")

    try:
        page.get_by_text("Ingresa Solicitud").wait_for(state="visible", timeout=5_000)
    except PlaywrightTimeoutError as exc:
        raise AppointmentWorkflowUnavailable(
            "No se encontro el detalle del tramite despues de hacer click. "
            "Es posible que la cita ya este reservada o que ya no exista un flujo pendiente."
        ) from exc


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


def select_available_site(page: Page, *, timeout: int = 15_000) -> Page:
    return _select_available_site(page, timeout=timeout, allow_hidden=False)


def select_available_site_for_observer(page: Page, *, timeout: int = 15_000) -> Page:
    return _select_available_site(page, timeout=timeout, allow_hidden=True)


def _select_available_site(page: Page, *, timeout: int, allow_hidden: bool) -> Page:
    logger.info("Selecting available site")
    site_select = page.locator(SITE_SELECTOR)
    site_select.wait_for(state="attached" if allow_hidden else "visible", timeout=timeout)
    options = _select_options(page, SITE_SELECTOR)
    logger.debug("Site options: %s", [option["text"] for option in options])
    selected = next((option for option in options if _is_real_site_option(option)), None)
    if selected is None:
        message = (
            "El observador no encontro una sede seleccionable."
            if allow_hidden
            else "No se encontro una sede seleccionable. Es posible que la cita ya este "
            "reservada o que ya no exista un flujo pendiente."
        )
        raise AppointmentWorkflowUnavailable(message)

    logger.info("Selecting site: %s", selected["text"])
    refresh_token = _mark_select_for_refresh(page, SITE_SELECTOR)
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
    _wait_for_appointment_options(
        page,
        refresh_token=refresh_token,
        previous_date_signature=previous_date,
        previous_hour_signature=previous_hour,
        timeout=timeout,
    )
    logger.debug("Current page after site selection: %s", page.url)
    return page


def read_appointment_availability(
    page: Page,
    *,
    include_person: bool = True,
    timeout: int = 30_000,
) -> AvailabilityResult:
    logger.debug("Checking appointment availability")
    page.wait_for_load_state("domcontentloaded", timeout=timeout)

    snapshot = _read_stable_appointment_snapshot(page, log_person=include_person)
    result = _availability_result_from_snapshot(
        page,
        snapshot,
        include_person=include_person,
    )
    if result.status == "partial":
        logger.info("Partial availability detected; rechecking before notifying")
        page.wait_for_timeout(1_500)
        snapshot = _read_stable_appointment_snapshot(page, log_person=include_person)
        result = _availability_result_from_snapshot(
            page,
            snapshot,
            include_person=include_person,
        )

    details = _snapshot_details(snapshot, include_person=False)
    logger.info(
        "Appointment summary: site=%s date=%s hour=%s",
        details.get("sede", "unknown"),
        details.get("fecha", "unknown"),
        details.get("hora", "unknown"),
    )
    return result


def select_available_appointment(
    page: Page,
    *,
    allow_hidden: bool = False,
    include_person: bool = True,
    is_allowed_appointment: Callable[[str, str], bool] | None = None,
    timeout: int = 15_000,
) -> AvailabilityResult:
    logger.info("Selecting available appointment date and hour")
    date_options = _real_options(_select_options(page, DATE_SELECTOR))
    if not date_options:
        raise AppointmentWorkflowUnavailable(
            "Se detecto disponibilidad, pero no se encontro una fecha seleccionable."
        )

    for date_option in date_options:
        previous_date = _selected_option_text(page, DATE_SELECTOR)
        previous_hour_signature = _options_signature(_select_options(page, HOUR_SELECTOR))
        date_select = page.locator(DATE_SELECTOR)
        logger.info("Selecting appointment date: %s", date_option["text"])
        _select_appointment_option(
            date_select,
            date_option["value"],
            allow_hidden=allow_hidden,
        )
        hour_options = _wait_for_options_after_selection(
            page,
            HOUR_SELECTOR,
            previous_signature=previous_hour_signature,
            require_change=not _same_option(previous_date, date_option["text"]),
            timeout=timeout,
        )
        real_hour_options = _real_options(hour_options)
        if not real_hour_options:
            logger.info("No selectable hours found for date %s", date_option["text"])
            continue

        for hour_option in real_hour_options:
            if is_allowed_appointment is not None and not is_allowed_appointment(
                str(date_option["text"]),
                str(hour_option["text"]),
            ):
                logger.info(
                    "Skipping appointment by order rule: %s %s",
                    date_option["text"],
                    hour_option["text"],
                )
                continue

            hour_select = page.locator(HOUR_SELECTOR)
            logger.info("Selecting appointment hour: %s", hour_option["text"])
            _select_appointment_option(
                hour_select,
                hour_option["value"],
                allow_hidden=allow_hidden,
            )
            page.wait_for_timeout(500)

            snapshot = _read_stable_appointment_snapshot(page, log_person=include_person)
            if _same_option(snapshot.date, date_option["text"]) and _same_option(
                snapshot.hour, hour_option["text"]
            ):
                return AvailabilityResult(
                    status="available",
                    message="Se seleccionaron una fecha y una hora disponibles.",
                    details=_snapshot_details(snapshot, include_person=include_person),
                )

            logger.warning(
                "Appointment selection was not preserved for date %s and hour %s",
                date_option["text"],
                hour_option["text"],
            )

    snapshot = _read_stable_appointment_snapshot(page, log_person=include_person)
    details = _snapshot_details(snapshot, include_person=include_person)
    if is_allowed_appointment is not None:
        details["blocked_by_order_rule"] = True
    return AvailabilityResult(
        status="partial",
        message=(
            "Se encontraron fechas y horas disponibles, pero ninguna cumple "
            "la regla de reserva de la orden."
            if is_allowed_appointment is not None
            else (
                "Se encontraron fechas disponibles, pero ninguna tiene una hora "
                "seleccionable y estable por ahora."
            )
        ),
        details=details,
    )


def has_available_date_options(page: Page) -> bool:
    return bool(_real_options(_select_options(page, DATE_SELECTOR)))


def solve_reservation_captcha_and_click_reserve(
    page: Page,
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
    can_submit: Callable[[], bool] | None = None,
    expected_details: dict[str, Any] | None = None,
    on_submission_intent: Callable[[], None] | None = None,
    on_submission_started: Callable[[], None] | None = None,
) -> Page:
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de resolver el captcha.")
    validate_selected_appointment(page, expected_details)
    captcha_path = _save_reservation_panel_image(page, settings)
    try:
        captcha_solution = solve_normal_captcha(captcha_path, settings)
    finally:
        try:
            captcha_path.unlink()
            logger.info("Removed temporary captcha image: %s", captcha_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Could not remove temporary captcha image %s: %s", captcha_path, exc)
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de enviar el captcha de reserva."
        )
    if can_submit is not None and not can_submit():
        raise AppointmentWorkflowCancelled("La orden fue pausada antes de enviar la reserva.")
    validate_selected_appointment(page, expected_details)

    logger.info("Filling reservation captcha field")
    reservation_field = page.locator(RESERVATION_FIELD_SELECTOR).first
    reservation_field.wait_for(state="visible", timeout=15_000)
    reservation_field.fill(captcha_solution, timeout=15_000)

    logger.info("Clicking reservation button")
    if cancel_event is not None and cancel_event.is_set():
        raise AppointmentWorkflowCancelled(
            "La pausa se aplico antes de pulsar el boton de reserva."
        )
    reserve_button = page.locator(RESERVATION_BUTTON_SELECTOR).first
    reserve_button.wait_for(state="visible", timeout=15_000)
    reserve_button.scroll_into_view_if_needed(timeout=15_000)
    if on_submission_intent is not None:
        on_submission_intent()
    try:
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
    except PlaywrightError as exc:
        raise ReservationSubmissionUncertain(
            "La solicitud de reserva fue enviada, pero la pagina se desconecto antes "
            "de iniciar la verificacion."
        ) from exc
    return page


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
            bounds = panel.bounding_box()
            if bounds is None or bounds["width"] < 120 or bounds["height"] < 80:
                logger.warning(
                    "Reservation panel has invalid dimensions using selector %s",
                    selector,
                )
                continue
            if not ensure_reservation_captcha_loaded(
                panel,
                timeout=settings.read_timeout_seconds * 1_000,
            ):
                logger.warning(
                    "Reservation panel captcha was not loaded using selector %s",
                    selector,
                )
                continue
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
    *,
    include_person: bool = True,
) -> AvailabilityResult:
    date_options = snapshot.date_options
    hour_options = snapshot.hour_options

    has_date_options = _has_real_options(date_options)
    has_hour_options = _has_real_options(hour_options)
    details = _snapshot_details(snapshot, include_person=include_person)

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
            status="partial",
            message=(
                "Se detecto texto compatible con cupo disponible, "
                "pero no hay fecha y hora seleccionables."
            ),
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


def _read_stable_appointment_snapshot(
    page: Page,
    *,
    log_person: bool = True,
) -> AppointmentSnapshot:
    previous_snapshot: AppointmentSnapshot | None = None
    current_snapshot: AppointmentSnapshot | None = None
    for attempt in range(1, 5):
        current_snapshot = _read_appointment_snapshot(page)
        logger.debug(
            "Appointment snapshot %s: %s",
            attempt,
            _snapshot_details(current_snapshot, include_person=False),
        )
        logger.debug("Date options: %s", current_snapshot.date_options)
        logger.debug("Hour options: %s", current_snapshot.hour_options)

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


def _snapshot_details(
    snapshot: AppointmentSnapshot,
    *,
    include_person: bool = True,
) -> dict[str, Any]:
    details = {
        "sede": _real_or_selected(snapshot.site, snapshot.site_options),
        "fecha": _real_or_selected(snapshot.date, snapshot.date_options),
        "hora": _real_or_selected(snapshot.hour, snapshot.hour_options),
        "cupos": snapshot.slots,
        "date_options": snapshot.date_options,
        "hour_options": snapshot.hour_options,
    }
    if include_person:
        details["nombre"] = snapshot.person_name
    return {key: value for key, value in details.items() if value}


def _real_or_selected(selected: str, options: list[str]) -> str:
    if selected and _has_real_options([selected]):
        return selected
    return next((option for option in options if _has_real_options([option])), selected)


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


def _wait_for_appointment_options(
    page: Page,
    *,
    refresh_token: str,
    previous_date_signature: tuple[tuple[str, str], ...],
    previous_hour_signature: tuple[tuple[str, str], ...],
    timeout: int = 15_000,
) -> None:
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
    while time.monotonic() < deadline:
        current_date = _options_signature(_select_options(page, DATE_SELECTOR))
        current_hour = _options_signature(_select_options(page, HOUR_SELECTOR))
        marker_present = page.locator(
            f'{SITE_SELECTOR}[data-appointment-bot-refresh="{refresh_token}"]'
        ).count()
        refreshed = (
            refreshed
            or marker_present == 0
            or (current_date != previous_date_signature or current_hour != previous_hour_signature)
        )
        pair = (current_date, current_hour)
        stable_reads = stable_reads + 1 if pair == last_pair else 1
        last_pair = pair
        if refreshed and stable_reads >= 2 and (current_date or current_hour):
            return
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


def _only_no_slots(options: list[str]) -> bool:
    return bool(options) and all(option.lower() == "sin cupos" for option in options)


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


def validate_selected_appointment(
    page: Page,
    expected_details: dict[str, Any] | None,
) -> None:
    expected_details = expected_details or {}
    expected_site = str(expected_details.get("sede") or "")
    expected_date = str(expected_details.get("fecha") or "")
    expected_hour = str(expected_details.get("hora") or "")
    actual_site = _selected_option_text(page, SITE_SELECTOR)
    actual_date = _selected_option_text(page, DATE_SELECTOR)
    actual_hour = _selected_option_text(page, HOUR_SELECTOR)
    if (
        (expected_site and not _same_option(actual_site, expected_site))
        or (expected_date and not _same_option(actual_date, expected_date))
        or (expected_hour and not _same_option(actual_hour, expected_hour))
    ):
        raise AppointmentWorkflowUnavailable(
            "La sede, fecha u hora seleccionadas cambiaron antes de enviar la reserva."
        )


def _mark_select_for_refresh(page: Page, selector: str) -> str:
    token = uuid.uuid4().hex
    page.locator(selector).evaluate(
        "(element, value) => { element.dataset.appointmentBotRefresh = value; }",
        token,
    )
    return token


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
    reloaded = panel.locator("img").evaluate_all(
        """elements => {
            let changed = false;
            for (const image of elements) {
                const rect = image.getBoundingClientRect();
                if (rect.width < 40 || rect.height < 20) continue;
                if (image.complete && image.naturalWidth > 0) continue;
                const source = image.getAttribute("src");
                if (!source) continue;
                const url = new URL(source, window.location.href);
                url.searchParams.set("_appointment_bot_retry", Date.now().toString());
                image.src = url.toString();
                changed = true;
            }
            return changed;
        }"""
    )
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


def _same_option(actual: str, expected: str) -> bool:
    return normalize_option(actual) == normalize_option(expected)
