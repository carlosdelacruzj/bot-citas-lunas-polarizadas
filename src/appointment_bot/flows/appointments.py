import logging
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.config import Settings
from appointment_bot.domain import AvailabilityResult
from appointment_bot.services.captcha import solve_normal_captcha
from appointment_bot.services.reservation_timings import ReservationTiming
from appointment_bot.utils.sanitization import normalize_option
from appointment_bot.utils.screenshots import save_screenshot

logger = logging.getLogger(__name__)

PROGRAM_ACTION_SELECTOR = (
    'input[type="image"][onclick*="__doPostBack"][onclick*="gvProgramacion"][onclick*="accion$0"], '
    'a[id^="MainContent_gvProgramacion_btnAccion_"][href*="__doPostBack"], '
    'a[href*="gvProgramacion"][href*="btnAccion"]'
)
RESERVE_APPOINTMENT_SELECTOR = "input#MainContent_btnCita"
RESERVE_APPOINTMENT_POSTBACK_TARGET = "ctl00$MainContent$btnCita"
SITE_SELECTOR = "#MainContent_idUcitas_cbosede"
DATE_SELECTOR = "#MainContent_idUcitas_cboFecha"
HOUR_SELECTOR = "#MainContent_idUcitas_cboHora"
SLOTS_LABEL_ID = "MainContent_idUcitas_lblcupos"
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

    if button_count == 1:
        selected_button = button.first
    else:
        raise AppointmentWorkflowUnavailable(
            "Hay varios tramites programables y el listado no muestra nombre ni documento "
            "para identificar de forma segura cual corresponde a la orden."
        )

    selected_button.scroll_into_view_if_needed(timeout=15_000)

    selected_button.click(timeout=15_000)
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

    if result.status != "available":
        fetch_snapshot = _read_fetch_probe_appointment_snapshot(page)
        if fetch_snapshot is not None:
            fetch_result = _availability_result_from_snapshot(
                page,
                fetch_snapshot,
                include_person=include_person,
            )
            if fetch_result.status in {"available", "partial"}:
                details = dict(fetch_result.details or {})
                details["fetch_probe"] = True
                details["modal_must_remain_open"] = True
                result = AvailabilityResult(
                    status=fetch_result.status,
                    message=(
                        f"{fetch_result.message} "
                        "La disponibilidad fue detectada por consulta directa al formulario."
                    ),
                    details=details,
                )

    details = _snapshot_details(snapshot, include_person=False)
    details.update(_read_site_refresh_evidence(page))
    if details:
        result_details = dict(result.details or {})
        result_details.update(
            {
                key: value
                for key, value in details.items()
                if key.startswith("site_refresh_")
            }
        )
        result = AvailabilityResult(result.status, result.message, result_details)
    logger.info(
        "Appointment summary: site=%s date=%s hour=%s",
        (result.details or details).get("sede", "unknown"),
        (result.details or details).get("fecha", "unknown"),
        (result.details or details).get("hora", "unknown"),
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

    for date_option in reversed(date_options):
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

        for hour_option in reversed(real_hour_options):
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
    panel_captcha_path = _save_reservation_panel_image(page, settings)
    captcha_path = save_reservation_captcha_image(
        page,
        settings,
        "04-reserva-captcha-tecnico-2captcha",
    )
    if timing is not None:
        timing.mark("captcha_image_finished")
    try:
        if timing is not None:
            timing.mark("captcha_solver_started")
        captcha_solution = solve_normal_captcha(captcha_path, settings)
        if captcha_audit is not None:
            captcha_audit["attempt"] = attempt_number
            captcha_audit["captcha_image_path"] = str(captcha_path)
            if panel_captcha_path is not None:
                captcha_audit["captcha_panel_image_path"] = str(panel_captcha_path)
            captcha_audit["captcha_solution_sent"] = captcha_solution
        if timing is not None:
            timing.mark("captcha_solver_finished")
    finally:
        logger.info("Preserved captcha image sent to 2captcha: %s", captcha_path)
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
) -> Path:
    logger.info("Saving isolated reservation captcha image")
    captcha_dir = settings.screenshots_dir / "captchas"
    captcha_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{settings.artifact_prefix}-" if settings.artifact_prefix else ""
    captcha_path = captcha_dir / (
        f"{label}-{prefix}{uuid.uuid4().hex}.png"
    )

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
                captcha_media.screenshot(path=str(captcha_path), timeout=10_000)
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


def _save_reservation_panel_image(page: Page, settings: Settings) -> Path | None:
    logger.info("Saving reservation panel image for technical evidence")
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{settings.artifact_prefix}-" if settings.artifact_prefix else ""
    captcha_path = settings.screenshots_dir / (
        f"04-reserva-captcha-panel-tecnico-2captcha-{prefix}{uuid.uuid4().hex}.png"
    )

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
                "Saved reservation panel image: %s using selector %s",
                captcha_path,
                selector,
            )
            return captcha_path
        except PlaywrightError as exc:
            logger.warning(
                "Could not save reservation panel image with selector %s: %s",
                selector,
                exc,
            )

    logger.warning("Could not save the reservation panel image for technical evidence.")
    return None


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
                        const looksLikeRefresh = /refresh|reload|reset|captcha|actualizar|recargar|cambiar|nuevo/.test(label);
                        const nearCaptcha = rect.left >= mediaRect.right - 8
                            && Math.abs((rect.top + rect.bottom) / 2 - (mediaRect.top + mediaRect.bottom) / 2) <= 80;
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


def _read_fetch_probe_appointment_snapshot(page: Page) -> AppointmentSnapshot | None:
    try:
        data = page.evaluate(
            """async ({ siteSelector, dateSelector, hourSelector, slotsLabelId }) => {
                const ids = {
                    site: siteSelector.slice(1),
                    date: dateSelector.slice(1),
                    hour: hourSelector.slice(1),
                    slots: slotsLabelId
                };
                const names = {
                    site: "ctl00$MainContent$idUcitas$cbosede",
                    date: "ctl00$MainContent$idUcitas$cboFecha"
                };
                const form = (
                    document.getElementById("form1")
                    || document.forms.form1
                    || document.forms[0]
                );
                const siteEl = document.querySelector(siteSelector);
                if (!form || !siteEl) return null;

                const action = form.getAttribute("action") || location.href;
                const url = new URL(action, location.href).toString();
                const setFormValue = (targetForm, name, value) => {
                    let element = targetForm.elements[name];
                    if (!element) {
                        element = targetForm.ownerDocument.createElement("input");
                        element.type = "hidden";
                        element.name = name;
                        targetForm.appendChild(element);
                    }
                    element.value = value || "";
                };
                const getForm = doc => (
                    doc.getElementById("form1") || doc.forms.form1 || doc.forms[0]
                );
                const postForm = async (doc, eventTarget, changes) => {
                    const targetForm = getForm(doc);
                    if (!targetForm) throw new Error("form1 not found");
                    Object.entries(changes || {}).forEach(([name, value]) => {
                        setFormValue(targetForm, name, value);
                    });
                    setFormValue(targetForm, "__EVENTTARGET", eventTarget);
                    setFormValue(targetForm, "__EVENTARGUMENT", "");
                    const response = await fetch(url, {
                        method: "POST",
                        body: new FormData(targetForm),
                        credentials: "include"
                    });
                    const html = await response.text();
                    return new DOMParser().parseFromString(html, "text/html");
                };
                const options = (doc, id) => {
                    const element = doc.getElementById(id);
                    if (!element) return [];
                    return Array.from(element.options).map(option => ({
                        text: (option.textContent || "").trim(),
                        value: option.value || "",
                        selected: option.selected
                    }));
                };
                const selectedText = items => {
                    const selected = items.find(option => option.selected);
                    return selected ? selected.text : "";
                };
                const isReal = option => {
                    const text = (option && option.text || "").trim().toLowerCase();
                    return Boolean(option && option.value)
                        && option.value !== "0"
                        && option.value !== "00"
                        && text
                        && !text.includes("sin cupos")
                        && !text.includes("seleccione");
                };
                const textById = (doc, id) => {
                    const element = doc.getElementById(id);
                    return element ? (element.textContent || "").trim() : "";
                };

                const siteValue = siteEl.value;
                const siteText = siteEl.options[siteEl.selectedIndex]
                    ? siteEl.options[siteEl.selectedIndex].text.trim()
                    : siteValue;
                const docDates = await postForm(document, names.site, {
                    [names.site]: siteValue
                });
                const dateOptions = options(docDates, ids.date);
                const realDates = dateOptions.filter(isReal);
                let hourOptions = [];
                let slots = "";
                if (realDates.length > 0) {
                    const firstDate = realDates[0];
                    const docHours = await postForm(docDates, names.date, {
                        [names.site]: siteValue,
                        [names.date]: firstDate.value
                    });
                    hourOptions = options(docHours, ids.hour);
                    slots = textById(docHours, ids.slots);
                }
                return {
                    siteOptions: options(document, ids.site)
                        .map(option => option.text)
                        .filter(Boolean),
                    dateOptions: dateOptions.map(option => option.text).filter(Boolean),
                    hourOptions: hourOptions.map(option => option.text).filter(Boolean),
                    site: siteText,
                    date: realDates[0] ? realDates[0].text : selectedText(dateOptions),
                    hour: selectedText(hourOptions),
                    slots,
                    personName: ""
                };
            }""",
            {
                "siteSelector": SITE_SELECTOR,
                "dateSelector": DATE_SELECTOR,
                "hourSelector": HOUR_SELECTOR,
                "slotsLabelId": SLOTS_LABEL_ID,
            },
        )
    except PlaywrightError as exc:
        logger.debug("Fetch appointment probe failed: %s", exc)
        return None

    if not data:
        return None

    snapshot = AppointmentSnapshot(
        site_options=list(data.get("siteOptions") or []),
        date_options=list(data.get("dateOptions") or []),
        hour_options=list(data.get("hourOptions") or []),
        site=str(data.get("site") or ""),
        date=str(data.get("date") or ""),
        hour=str(data.get("hour") or ""),
        slots=str(data.get("slots") or ""),
        person_name=str(data.get("personName") or ""),
    )
    logger.debug("Fetch appointment probe: %s", _snapshot_details(snapshot, include_person=False))
    return snapshot


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


def _format_options_signature(signature: tuple[tuple[str, str], ...]) -> str:
    return "|".join(f"{value}:{text}" for value, text in signature)


def _store_site_refresh_evidence(page: Page, evidence: SiteRefreshEvidence) -> None:
    page.evaluate(
        """evidence => {
            window.__appointmentBotLastSiteRefresh = evidence;
        }""",
        evidence.details(),
    )


def _read_site_refresh_evidence(page: Page) -> dict[str, Any]:
    try:
        data = page.evaluate("() => window.__appointmentBotLastSiteRefresh || null")
    except PlaywrightError:
        return {}
    return dict(data or {})


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
    *,
    expected_person_name: str | None = None,
) -> None:
    expected_details = expected_details or {}
    expected_site = str(expected_details.get("sede") or "")
    expected_date = str(expected_details.get("fecha") or "")
    expected_hour = str(expected_details.get("hora") or "")
    actual_site = _selected_option_text(page, SITE_SELECTOR)
    actual_date = _selected_option_text(page, DATE_SELECTOR)
    actual_hour = _selected_option_text(page, HOUR_SELECTOR)
    actual_slots = _read_slots_value(page)
    if (
        (expected_site and not _same_option(actual_site, expected_site))
        or (expected_date and not _same_option(actual_date, expected_date))
        or (expected_hour and not _same_option(actual_hour, expected_hour))
    ):
        raise AppointmentWorkflowUnavailable(
            "La sede, fecha u hora seleccionadas cambiaron antes de enviar la reserva."
        )
    if not actual_site or not actual_date or not actual_hour:
        raise AppointmentWorkflowUnavailable(
            "La sede, fecha y hora deben seguir seleccionadas antes de enviar la reserva."
        )
    normalized_slots = normalize_option(actual_slots)
    if normalized_slots in {"0", "sin cupos", "sin cupos disponibles"}:
        raise AppointmentWorkflowUnavailable(
            "El portal indica que el cupo seleccionado ya no esta disponible."
        )
    actual_person_name = _read_person_name(page)
    if expected_person_name and actual_person_name:
        expected_name = normalize_option(expected_person_name)
        actual_name = normalize_option(actual_person_name)
        if expected_name not in actual_name and actual_name not in expected_name:
            raise AppointmentWorkflowUnavailable(
                "La identidad mostrada por el portal no coincide con la persona de la orden."
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


def _same_option(actual: str, expected: str) -> bool:
    return normalize_option(actual) == normalize_option(expected)
