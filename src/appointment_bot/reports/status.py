from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, time
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from appointment_bot.db.orders import list_service_order_summaries
from appointment_bot.db.runs import (
    list_runs,
    summarize_order_checks,
)
from appointment_bot.services.database_models import ServiceOrderSummary

REPORT_TIMEZONE = ZoneInfo("America/Lima")
REPORT_START_HOUR = 6
REPORT_END_HOUR = 20
RUN_PAGE_SIZE = 200
DEFAULT_RESERVATION_SITE = "LIMA-LA VICTORIA"


@dataclass(frozen=True)
class StatusReportActivity:
    checks: int
    reservation_attempts: int
    confirmed_reservations: int
    last_status: str | None
    last_finished_at: datetime | None


def generate_status_report_images(
    orders: list[ServiceOrderSummary],
    *,
    output_dir: Path = Path("reports/status"),
) -> list[Path]:
    if not orders:
        return []

    generated_at = datetime.now(UTC)
    period_start, period_end = _report_window(generated_at)
    output_dir = _dated_output_dir(output_dir, generated_at)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    active_orders = [order for order in list_service_order_summaries() if order.status == "ready"]
    monitoring_order = active_orders[0] if active_orders else orders[0]
    monitoring_activity = _activity_for_order(
        monitoring_order.order_id,
        period_start,
        period_end,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
            for order in orders:
                order_activity = _activity_for_order(order.order_id, period_start, period_end)
                activity = order_activity
                if not _order_has_confirmed_reservation(order, order_activity):
                    activity = replace(
                        order_activity,
                        checks=monitoring_activity.checks,
                        last_status=monitoring_activity.last_status,
                        last_finished_at=monitoring_activity.last_finished_at,
                    )
                page.set_content(
                    _report_html(
                        order,
                        activity,
                        generated_at,
                    )
                )
                card = page.locator(".report-card")
                card.wait_for(state="visible")
                output_path = output_dir / _report_filename(order, generated_at)
                card.screenshot(path=str(output_path))
                results.append(output_path)
        finally:
            browser.close()

    return results


def _activity_for_order(
    order_id: str,
    period_start: datetime,
    period_end: datetime,
) -> StatusReportActivity:
    matching_runs = []
    offset = 0

    while True:
        page = list_runs(limit=RUN_PAGE_SIZE, offset=offset, order_id=order_id)
        if not page:
            break
        for run in page:
            started_at = _parse_timestamp(run.started_at)
            if period_start <= started_at <= period_end:
                matching_runs.append(run)
        if len(page) < RUN_PAGE_SIZE or _parse_timestamp(page[-1].started_at) < period_start:
            break
        offset += RUN_PAGE_SIZE

    last_run = matching_runs[0] if matching_runs else None
    confirmed_run = next((run for run in matching_runs if run.reservation_confirmed), None)
    (
        check_count,
        _first_check_at,
        _tracking_started_at,
        last_check_status,
        last_check_at,
    ) = summarize_order_checks(
        order_id,
        started_at=period_start,
        finished_at=period_end,
    )
    return StatusReportActivity(
        checks=check_count,
        reservation_attempts=sum(run.reservation_attempted for run in matching_runs),
        confirmed_reservations=sum(run.reservation_confirmed for run in matching_runs),
        last_status=(
            confirmed_run.status
            if confirmed_run is not None
            else (
            last_check_status
            if last_check_status is not None
            else (last_run.status if last_run is not None else None)
            )
        ),
        last_finished_at=(
            _parse_timestamp(confirmed_run.finished_at)
            if confirmed_run is not None
            else (
            last_check_at
            if last_check_at is not None
            else (_parse_timestamp(last_run.finished_at) if last_run is not None else None)
            )
        ),
    )


def _report_html(
    order: ServiceOrderSummary,
    activity: StatusReportActivity,
    generated_at: datetime,
) -> str:
    title, badge, badge_class = _status_presentation(order, activity)
    confirmed = _order_has_confirmed_reservation(order, activity)
    last_check = (
        _format_local_datetime(activity.last_finished_at)
        if activity.last_finished_at is not None
        else "Sin revisiones registradas en este periodo"
    )
    reservation_detail = _reservation_detail(order, activity)
    applicant_name = order.applicant_name or order.document_number_masked
    eyebrow = "Cita verificada" if confirmed else "Estado de monitoreo"
    checks_label = "Verificaciones realizadas" if confirmed else "Consultas realizadas"
    result_label = "Estado" if confirmed else "Ultimo resultado"
    result_text = "Programada" if confirmed else _status_text(activity.last_status)
    last_check_label = "Verificada el" if confirmed else "Ultima revision"
    reservation_label = "Cita" if confirmed else "Reserva"

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: transparent; font-family: Arial, sans-serif; color: #172033; }}
.report-card {{ width: 1000px; min-height: 830px; margin: 40px; padding: 66px; background: #f8fafc;
  border-radius: 38px; border: 2px solid #dbe4ee; box-shadow: 0 18px 60px rgba(15, 23, 42, .12); }}
.header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 30px; }}
.eyebrow {{ color: #2563eb; font-weight: 700; font-size: 22px; letter-spacing: 1.6px;
  text-transform: uppercase; }}
h1 {{ margin: 13px 0 8px; font-size: 48px; line-height: 1.08; }}
.badge {{ padding: 16px 24px; border-radius: 999px; font-weight: 700; font-size: 21px;
  white-space: nowrap; }}
.active {{ color: #166534; background: #dcfce7; }}
.reserved {{ color: #1d4ed8; background: #dbeafe; }}
.paused {{ color: #92400e; background: #fef3c7; }}
.neutral {{ color: #475569; background: #e2e8f0; }}
.identity {{ margin-top: 42px; padding: 30px 34px; border-radius: 24px;
  background: white; border: 1px solid #e2e8f0; }}
.name {{ font-size: 31px; font-weight: 700; line-height: 1.25; }}
.document {{ margin-top: 8px; color: #64748b; font-size: 22px; }}
.metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 26px; }}
.metric {{ min-height: 150px; padding: 28px; border-radius: 24px; background: white;
  border: 1px solid #e2e8f0; }}
.label {{ color: #64748b; font-size: 19px; text-transform: uppercase; letter-spacing: .8px; }}
.value {{ margin-top: 13px; font-size: 34px; font-weight: 700; line-height: 1.15; }}
.value.small {{ font-size: 25px; }}
.footer {{ display: flex; justify-content: flex-end; gap: 30px; margin-top: 36px;
  color: #64748b; font-size: 18px; }}
</style>
</head>
<body><main class="report-card">
  <div class="header"><div><div class="eyebrow">{escape(eyebrow)}</div>
  <h1>{escape(title)}</h1></div>
  <div class="badge {badge_class}">{escape(badge)}</div></div>
  <section class="identity"><div class="name">{escape(applicant_name)}</div>
  <div class="document">Documento: {escape(order.document_number_masked)}</div></section>
  <section class="metrics">
    <div class="metric"><div class="label">{escape(checks_label)}</div>
      <div class="value">{activity.checks}</div></div>
    <div class="metric"><div class="label">{escape(result_label)}</div>
      <div class="value small">{escape(result_text)}</div></div>
    <div class="metric"><div class="label">{escape(last_check_label)}</div>
      <div class="value small">{escape(last_check)}</div></div>
    <div class="metric"><div class="label">{escape(reservation_label)}</div>
      <div class="value small">{escape(reservation_detail)}</div></div>
  </section>
  <footer class="footer">
    <span>Reporte generado: {_format_local_datetime(generated_at)}</span>
  </footer>
</main></body></html>"""


def _status_presentation(
    order: ServiceOrderSummary,
    activity: StatusReportActivity,
) -> tuple[str, str, str]:
    if _order_has_confirmed_reservation(order, activity):
        return "Cita programada", "PROGRAMADA", "reserved"
    if order.status == "ready":
        return "Monitoreo de disponibilidad", "ACTIVO", "active"
    if order.status == "paused":
        return "Monitoreo pausado", "PAUSADO", "paused"
    return "Estado de la solicitud", order.status.upper(), "neutral"


def _reservation_detail(
    order: ServiceOrderSummary,
    activity: StatusReportActivity,
) -> str:
    if _order_has_confirmed_reservation(order, activity):
        parts = [
            order.reservation_date,
            order.reservation_hour,
            order.reservation_site or DEFAULT_RESERVATION_SITE,
        ]
        return " - ".join(str(part) for part in parts if part) or "Programada"
    if activity.reservation_attempts:
        return f"{activity.reservation_attempts} intento(s) registrado(s)"
    if order.status == "paused":
        return "Pausada"
    if order.status != "ready":
        return "No activa"
    return "Automática activa"


def _order_has_confirmed_reservation(
    order: ServiceOrderSummary,
    activity: StatusReportActivity,
) -> bool:
    return order.reservation_status == "confirmed" or activity.confirmed_reservations > 0


def _status_text(status: str | None) -> str:
    return {
        None: "Sin actividad reciente",
        "unavailable": "Sin cupos disponibles",
        "partial": "Disponibilidad parcial",
        "available": "Cupo detectado",
        "registered": "Reserva confirmada",
        "reservation_unconfirmed": "Reserva pendiente de verificación",
        "completed": "Trámite completado",
        "error": "Revisión con error",
        "unknown": "Resultado por verificar",
        "paused": "Monitoreo pausado",
        "skipped": "Revisión omitida",
    }.get(status, status.replace("_", " ").capitalize() if status else "Sin actividad reciente")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=REPORT_TIMEZONE)
    return parsed.astimezone(UTC)


def _format_local_datetime(value: datetime) -> str:
    formatted = value.astimezone(REPORT_TIMEZONE).strftime("%d/%m/%Y %I:%M %p")
    return formatted.replace("AM", "a. m.").replace("PM", "p. m.")


def _report_window(generated_at: datetime) -> tuple[datetime, datetime]:
    local_now = generated_at.astimezone(REPORT_TIMEZONE)
    period_start = datetime.combine(
        local_now.date(),
        time(hour=REPORT_START_HOUR),
        tzinfo=REPORT_TIMEZONE,
    )
    scheduled_end = datetime.combine(
        local_now.date(),
        time(hour=REPORT_END_HOUR),
        tzinfo=REPORT_TIMEZONE,
    )
    period_end = min(max(local_now, period_start), scheduled_end)
    return period_start.astimezone(UTC), period_end.astimezone(UTC)


def _dated_output_dir(output_dir: Path, generated_at: datetime) -> Path:
    day = generated_at.astimezone(REPORT_TIMEZONE).strftime("%d-%m-%Y")
    return output_dir / day


def _report_filename(order: ServiceOrderSummary, generated_at: datetime) -> str:
    applicant_name = order.applicant_name or order.document_number_masked or "Cliente"
    safe_name = "".join(
        character
        for character in applicant_name
        if character not in '<>:"/\\|?*' and ord(character) >= 32
    ).strip(" .")
    timestamp = generated_at.astimezone(REPORT_TIMEZONE).strftime("%d-%m-%Y %H-%M-%S")
    return f"Reporte - {safe_name or 'Cliente'} - {timestamp}.png"
