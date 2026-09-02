import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from appointment_bot.reservation_engine.appointment_contracts import (
    DATE_SELECTOR,
    HOUR_SELECTOR,
    RESERVE_APPOINTMENT_POSTBACK_TARGET,
    RESERVE_APPOINTMENT_SELECTOR,
    SITE_SELECTOR,
    AppointmentOptionsNotRefreshed,
    AppointmentWorkflowUnavailable,
    SiteRefreshEvidence,
)
from appointment_bot.reservation_engine.appointment_dom import (
    has_real_options as _has_real_options,
)
from appointment_bot.reservation_engine.appointment_dom import (
    options_signature as _options_signature,
)
from appointment_bot.reservation_engine.appointment_dom import (
    select_appointment_option as _select_appointment_option,
)
from appointment_bot.reservation_engine.appointment_dom import (
    select_options as _select_options,
)
from appointment_bot.reservation_engine.appointment_modal_styles import (
    ensure_appointment_modal_styles,
)
from appointment_bot.utils.sanitization import normalize_option

logger = logging.getLogger(__name__)

@dataclass
class _PostbackCapture:
    page_origin: str
    started_at: float
    post_detected: bool = False
    post_count: int = 0
    post_url: str | None = None
    post_status: int | None = None
    post_elapsed_ms: int | None = None
    post_content_length: int | None = None
    post_resource_type: str | None = None
    post_failure: str | None = None

    def accepts(self, url: str) -> bool:
        return _url_origin(url) == self.page_origin

    def observe_request(self, request) -> None:
        if request.method.upper() != "POST" or not self.accepts(request.url):
            return
        self.post_detected = True
        self.post_count += 1
        self.post_url = _sanitize_telemetry_url(request.url)
        self.post_resource_type = request.resource_type

    def observe_response(self, response) -> None:
        request = response.request
        if request.method.upper() != "POST" or not self.accepts(response.url):
            return
        self.post_detected = True
        self.post_url = _sanitize_telemetry_url(response.url)
        self.post_status = response.status
        self.post_elapsed_ms = round((time.monotonic() - self.started_at) * 1_000)
        self.post_content_length = _content_length(response.headers.get("content-length"))
        self.post_resource_type = request.resource_type

    def observe_failure(self, request) -> None:
        if request.method.upper() != "POST" or not self.accepts(request.url):
            return
        self.post_detected = True
        self.post_url = _sanitize_telemetry_url(request.url)
        self.post_elapsed_ms = round((time.monotonic() - self.started_at) * 1_000)
        self.post_resource_type = request.resource_type
        self.post_failure = str(request.failure or "request_failed")


def open_appointment_panel(page: Page) -> Page:
    return _open_appointment_panel(page, allow_hidden=False)


def open_hidden_appointment_panel_for_observer(page: Page) -> Page:
    return _open_appointment_panel(page, allow_hidden=True)


def _open_appointment_panel(page: Page, *, allow_hidden: bool) -> Page:
    logger.info("Opening appointment availability panel")
    ensure_appointment_modal_styles(page)
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
        ensure_appointment_modal_styles(page)
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
    ensure_appointment_modal_styles(page)

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
    reset_first: bool = False,
    timeout: int = 15_000,
    telemetry_attempt: int | None = None,
    telemetry_phase: str = "required_site",
) -> Page:
    return _select_available_site(
        page,
        timeout=timeout,
        allow_hidden=False,
        required_site=required_site,
        reset_first=reset_first,
        telemetry_attempt=telemetry_attempt,
        telemetry_phase=telemetry_phase,
    )


def select_available_site_for_observer(
    page: Page,
    *,
    required_site: str | None = None,
    timeout: int = 15_000,
    telemetry_attempt: int | None = None,
) -> Page:
    return _select_available_site(
        page,
        timeout=timeout,
        allow_hidden=True,
        required_site=required_site,
        reset_first=False,
        telemetry_attempt=telemetry_attempt,
        telemetry_phase="observer_required_site",
    )


def _select_available_site(
    page: Page,
    *,
    timeout: int,
    allow_hidden: bool,
    required_site: str | None,
    reset_first: bool,
    telemetry_attempt: int | None,
    telemetry_phase: str,
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

    if reset_first:
        _reset_site_selection(
            page,
            site_select,
            options,
            allow_hidden=allow_hidden,
            timeout=timeout,
            telemetry_attempt=telemetry_attempt,
        )
        options = _select_options(page, SITE_SELECTOR)
        selected = _select_site_option(options, required_site=required_site)
        if selected is None:
            raise AppointmentWorkflowUnavailable(
                "La sede requerida dejo de estar disponible despues de vaciar el selector."
            )

    logger.info("Selecting site: %s", selected["text"])
    refresh_token = _mark_select_for_refresh(page, SITE_SELECTOR)
    async_refresh_token = _mark_aspnet_async_refresh(page)
    previous_date = _options_signature(_select_options(page, DATE_SELECTOR))
    previous_hour = _options_signature(_select_options(page, HOUR_SELECTOR))
    postback_capture = _start_postback_capture(page)
    try:
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
            postback_capture=postback_capture,
            telemetry_attempt=telemetry_attempt,
            telemetry_phase=telemetry_phase,
            timeout=timeout,
        )
    finally:
        _stop_postback_capture(page, postback_capture)
    _store_site_refresh_evidence(page, evidence)
    logger.info(
        "Site refresh evidence: attempt=%s phase=%s site=%s post=%s status=%s "
        "post_ms=%s confirmed=%s changed=%s async=%s elapsed_ms=%s "
        "date_before=%s date_after=%s hour_before=%s hour_after=%s",
        evidence.attempt,
        evidence.phase,
        evidence.selected_site,
        evidence.post_detected,
        evidence.post_status,
        evidence.post_elapsed_ms,
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


def _reset_site_selection(
    page: Page,
    site_select,
    options: list[dict[str, Any]],
    *,
    allow_hidden: bool,
    timeout: int,
    telemetry_attempt: int | None,
) -> None:
    placeholder = next(
        (
            option
            for option in options
            if not option.get("disabled")
            and not option.get("hidden")
            and (
                not str(option.get("value") or "").strip()
                or normalize_option(str(option.get("text") or "")).startswith("seleccione")
            )
        ),
        None,
    )
    if placeholder is None:
        raise AppointmentWorkflowUnavailable(
            "No se encontro la opcion vacia necesaria para refrescar la sede."
        )
    if site_select.input_value() == str(placeholder["value"]):
        return

    logger.info("Resetting site selection to the empty option before selecting it again")
    refresh_token = _mark_select_for_refresh(page, SITE_SELECTOR)
    async_refresh_token = _mark_aspnet_async_refresh(page)
    previous_date = _options_signature(_select_options(page, DATE_SELECTOR))
    previous_hour = _options_signature(_select_options(page, HOUR_SELECTOR))
    postback_capture = _start_postback_capture(page)
    try:
        _select_appointment_option(
            site_select,
            str(placeholder["value"]),
            allow_hidden=allow_hidden,
        )
        evidence = _wait_for_appointment_options(
            page,
            selected_site=str(placeholder.get("text") or ""),
            refresh_token=refresh_token,
            async_refresh_token=async_refresh_token,
            previous_date_signature=previous_date,
            previous_hour_signature=previous_hour,
            postback_capture=postback_capture,
            telemetry_attempt=telemetry_attempt,
            telemetry_phase="empty_site",
            timeout=timeout,
        )
    finally:
        _stop_postback_capture(page, postback_capture)
    _store_site_refresh_evidence(page, evidence)
    logger.info(
        "Empty site refresh attempt=%s post=%s status=%s confirmed=%s async=%s elapsed_ms=%s",
        evidence.attempt,
        evidence.post_detected,
        evidence.post_status,
        evidence.confirmed,
        evidence.async_completed,
        evidence.elapsed_ms,
    )


def _format_options_signature(signature: tuple[tuple[str, str], ...]) -> str:
    return "|".join(f"{value}:{text}" for value, text in signature)


def _url_origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), "", "", ""))


def _sanitize_telemetry_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _content_length(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except ValueError:
        return None


def _start_postback_capture(page: Page) -> _PostbackCapture:
    capture = _PostbackCapture(
        page_origin=_url_origin(page.url),
        started_at=time.monotonic(),
    )
    page.on("request", capture.observe_request)
    page.on("response", capture.observe_response)
    page.on("requestfailed", capture.observe_failure)
    return capture


def _stop_postback_capture(page: Page, capture: _PostbackCapture) -> None:
    page.remove_listener("request", capture.observe_request)
    page.remove_listener("response", capture.observe_response)
    page.remove_listener("requestfailed", capture.observe_failure)


def _store_site_refresh_evidence(page: Page, evidence: SiteRefreshEvidence) -> None:
    page.evaluate(
        """payload => {
            window.__appointmentBotLastSiteRefresh = payload.latest;
            window.__appointmentBotSiteRefreshHistory =
                window.__appointmentBotSiteRefreshHistory || [];
            window.__appointmentBotSiteRefreshHistory.push(payload.historyItem);
            if (window.__appointmentBotSiteRefreshHistory.length > 100) {
                window.__appointmentBotSiteRefreshHistory =
                    window.__appointmentBotSiteRefreshHistory.slice(-100);
            }
        }""",
        {
            "latest": evidence.details(),
            "historyItem": evidence.history_item(),
        },
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
    postback_capture: _PostbackCapture,
    telemetry_attempt: int | None,
    telemetry_phase: str,
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
                event_id=refresh_token,
                attempt=telemetry_attempt,
                phase=telemetry_phase,
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
                post_detected=postback_capture.post_detected,
                post_count=postback_capture.post_count,
                post_url=postback_capture.post_url,
                post_status=postback_capture.post_status,
                post_elapsed_ms=postback_capture.post_elapsed_ms,
                post_content_length=postback_capture.post_content_length,
                post_resource_type=postback_capture.post_resource_type,
                post_failure=postback_capture.post_failure,
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
