from __future__ import annotations

import logging
import re
import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from appointment_bot.config import Settings
from appointment_bot.core.contacts import resolve_whatsapp_recipient
from appointment_bot.db.appointment_reminder_control import (
    get_appointment_reminder_control,
)
from appointment_bot.db.appointment_reminders import (
    AppointmentReminderCandidate,
    appointment_reminder_job_counts,
    appointment_reminder_status,
    backfill_missing_appointment_days,
    count_invalid_current_appointment_dates,
    daily_summary_barrier_status,
    list_appointment_reminder_candidates,
    mark_daily_summary_missing_alerted,
    record_appointment_reminder_day,
)
from appointment_bot.db.whatsapp_automation import enqueue_appointment_reminder_job
from appointment_bot.services.notifier import send_telegram_message
from appointment_bot.utils.sanitization import sanitize_text

logger = logging.getLogger(__name__)
LIMA_TIMEZONE = ZoneInfo("America/Lima")
MONTH_NAMES = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
ALLOWED_TEMPLATE_VARIABLES = ("nombre", "fecha", "hora", "sede")
DEFAULT_REMINDER_TEMPLATE = (
    "Hola, {nombre}. Te recordamos que mañana, {fecha}, tienes tu cita de "
    "lunas polarizadas. Hora: {hora}. Sede: {sede}. Si tu cita fue "
    "modificada recientemente, por favor comunícate con nosotros."
)
_TEMPLATE_FIELD = re.compile(r"\{([^{}]+)\}")


class AppointmentReminderScheduler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="appointment-reminder-scheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Appointment reminder scheduler started: runtime_control=database time=%s",
            self.settings.appointment_reminders_time.isoformat(timespec="minutes"),
        )

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is None:
            return
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("Appointment reminder scheduler is still stopping")
        else:
            logger.info("Appointment reminder scheduler stopped")
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now(LIMA_TIMEZONE)
            if now.time() >= self.settings.appointment_reminders_time:
                try:
                    reconcile_appointment_reminders(self.settings, now=now)
                except Exception:
                    logger.exception("Could not reconcile appointment reminders")
            self._stop_event.wait(self.settings.appointment_reminders_reconcile_seconds)


def reconcile_appointment_reminders(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    effective_now = now or datetime.now(LIMA_TIMEZONE)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=LIMA_TIMEZONE)
    else:
        effective_now = effective_now.astimezone(LIMA_TIMEZONE)
    service_date = effective_now.date()
    appointment_day = service_date + timedelta(days=1)
    normalized_count, _invalid_backfill_count = backfill_missing_appointment_days(
        settings=settings
    )
    if normalized_count:
        logger.info("Normalized %s stored appointment dates", normalized_count)
    control = get_appointment_reminder_control(settings)
    candidates = list_appointment_reminder_candidates(
        appointment_day,
        settings=settings,
    )
    invalid_date_count = count_invalid_current_appointment_dates(settings=settings)
    summary_status = daily_summary_barrier_status(service_date, settings=settings)
    valid_candidates: list[
        tuple[AppointmentReminderCandidate, str | None, str | None, str]
    ] = []
    missing_contact_count = 0
    for candidate in candidates:
        try:
            phone, username = resolve_whatsapp_recipient(
                candidate["recipient_phone"],
                candidate["recipient_username"],
            )
        except ValueError:
            missing_contact_count += 1
            continue
        if control.mode == "canary" and candidate["order_id"] not in control.canary_order_ids:
            continue
        valid_candidates.append(
            (
                candidate,
                phone,
                username,
                appointment_reminder_message(candidate, control.message_template),
            )
        )

    status = "disabled"
    error: str | None = None
    created_count = 0
    existing_count = 0
    if control.mode != "disabled":
        if control.mode == "dry_run":
            status = "dry_run"
        elif control.mode == "canary" and not control.canary_order_ids:
            status = "blocked"
            error = "El modo canario requiere al menos una orden elegible seleccionada."
        elif len(valid_candidates) > settings.appointment_reminders_daily_limit:
            status = "blocked"
            error = (
                "El total de recordatorios supera el limite diario configurado: "
                f"{len(valid_candidates)}/{settings.appointment_reminders_daily_limit}."
            )
        else:
            for candidate, phone, username, message_text in valid_candidates:
                created = enqueue_appointment_reminder_job(
                    service_date=service_date,
                    appointment_day=appointment_day,
                    reservation_id=candidate["reservation_id"],
                    order_id=candidate["order_id"],
                    recipient_phone=phone,
                    recipient_username=username,
                    message_text=message_text,
                    settings=settings,
                )
                if created:
                    created_count += 1
                else:
                    existing_count += 1
            if not valid_candidates:
                status = "complete"
            elif summary_status == "missing":
                status = "waiting_summary"
            elif summary_status == "active":
                status = "processing"
            else:
                status = "ready"

            job_counts = appointment_reminder_job_counts(
                service_date,
                settings=settings,
            )
            active_jobs = sum(
                job_counts.get(job_status, 0)
                for job_status in ("queued", "blocked", "running")
            )
            terminal_jobs = sum(
                job_counts.get(job_status, 0)
                for job_status in ("sent", "failed", "uncertain", "skipped")
            )
            if summary_status not in {"missing", "active"}:
                if active_jobs == 0 and terminal_jobs >= len(valid_candidates):
                    status = "complete"
                elif job_counts.get("running", 0):
                    status = "processing"

    record_appointment_reminder_day(
        service_date=service_date,
        appointment_day=appointment_day,
        status=status,
        summary_status=summary_status,
        eligible_count=len(candidates),
        queued_count=created_count,
        existing_count=existing_count,
        missing_contact_count=missing_contact_count,
        invalid_date_count=invalid_date_count,
        last_error=error,
        settings=settings,
    )
    if status == "waiting_summary" and _summary_grace_expired(settings, effective_now):
        if mark_daily_summary_missing_alerted(service_date, settings=settings):
            send_telegram_message(
                settings,
                "\n".join(
                    [
                        "⚠️ Recordatorios de cita bloqueados.",
                        f"Fecha de citas: {appointment_day.isoformat()}.",
                        "El resumen diario de evidencias no aparecio dentro de la ventana.",
                        "No se enviara ningun recordatorio hasta que exista ese trabajo.",
                    ]
                ),
            )
    logger.info(
        "Appointment reminders reconciled: date=%s appointment_day=%s status=%s "
        "eligible=%s queued=%s existing=%s missing_contact=%s summary=%s",
        service_date,
        appointment_day,
        status,
        len(candidates),
        created_count,
        existing_count,
        missing_contact_count,
        summary_status,
    )
    return appointment_reminder_status(service_date, settings=settings)


def validate_reminder_template(message_template: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    template = message_template.strip()
    if not template:
        return {"message_template": "El mensaje no puede quedar vacío."}
    if len(template) > 1000:
        errors["message_template"] = "El mensaje no puede superar 1000 caracteres."
    stripped = _TEMPLATE_FIELD.sub("", template)
    if "{" in stripped or "}" in stripped:
        errors["message_template"] = "Hay una variable incompleta o llaves sin cerrar."
    unknown = sorted(set(_TEMPLATE_FIELD.findall(template)) - set(ALLOWED_TEMPLATE_VARIABLES))
    if unknown:
        errors["message_template"] = "Variables no permitidas: " + ", ".join(unknown)
    if "{fecha}" not in template:
        errors["message_template"] = "Incluye {fecha} para identificar la cita sin ambigüedad."
    return errors


def appointment_reminder_message(
    candidate: AppointmentReminderCandidate,
    message_template: str = DEFAULT_REMINDER_TEMPLATE,
) -> str:
    appointment_day = candidate["appointment_day"]
    name = str(candidate.get("applicant_name") or "").strip()
    date_text = _appointment_day_text(appointment_day)
    hour = str(candidate.get("appointment_hour") or "").strip()
    site = str(candidate.get("site") or "").strip()
    values = {
        "nombre": name or "cliente",
        "fecha": date_text,
        "hora": hour or "por confirmar",
        "sede": site or "por confirmar",
    }
    rendered = message_template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return sanitize_text(rendered)


def _appointment_day_text(appointment_day: date) -> str:
    return (
        f"{appointment_day.day} de {MONTH_NAMES[appointment_day.month]} "
        f"de {appointment_day.year}"
    )

def appointment_reminder_status_payload(settings: Settings) -> dict[str, object]:
    now = datetime.now(LIMA_TIMEZONE)
    control = get_appointment_reminder_control(settings)
    payload = appointment_reminder_status(now.date(), settings=settings)
    candidates = list_appointment_reminder_candidates(
        now.date() + timedelta(days=1),
        settings=settings,
    )
    job_status_by_order = {
        str(job["order_id"]): str(job["status"])
        for job in payload["jobs"]
        if isinstance(job, dict) and job.get("order_id")
    }
    payload["candidates"] = _appointment_reminder_candidates_payload(
        candidates,
        job_status_by_order,
    )
    payload["configuration"] = {
        "enabled": control.mode in {"canary", "live"},
        "dry_run": control.mode == "dry_run",
        "time": settings.appointment_reminders_time.isoformat(timespec="minutes"),
        "summary_grace_minutes": settings.appointment_reminders_summary_grace_minutes,
        "reconcile_seconds": settings.appointment_reminders_reconcile_seconds,
        "send_interval_seconds": settings.appointment_reminders_send_interval_seconds,
        "daily_limit": settings.appointment_reminders_daily_limit,
        "timezone": "America/Lima",
    }
    payload["control"] = {
        "mode": control.mode,
        "message_template": control.message_template,
        "default_template": DEFAULT_REMINDER_TEMPLATE,
        "canary_order_ids": list(control.canary_order_ids),
        "revision": control.revision,
        "updated_at": control.updated_at.isoformat(),
        "updated_by": control.updated_by,
        "applies_from": "next_reconciliation",
    }
    payload["allowed_variables"] = list(ALLOWED_TEMPLATE_VARIABLES)
    payload["current_time"] = now.isoformat()
    payload["scheduler_window_open"] = now.time() >= settings.appointment_reminders_time
    return payload


def _summary_grace_expired(settings: Settings, now: datetime) -> bool:
    cutoff = datetime.combine(
        now.date(),
        settings.appointment_reminders_time,
        tzinfo=LIMA_TIMEZONE,
    )
    return now >= cutoff + timedelta(
        minutes=settings.appointment_reminders_summary_grace_minutes
    )


def _masked_reminder_recipient(phone: str | None, username: str | None) -> str:
    if phone:
        digits = "".join(character for character in phone if character.isdigit())
        return f"***{digits[-4:]}" if digits else "telefono configurado"
    if username:
        text = username.lstrip("@")
        return f"@{text[:2]}***{text[-1:]}" if text else "usuario configurado"
    return "sin contacto"


def _appointment_reminder_candidates_payload(
    candidates: list[AppointmentReminderCandidate],
    job_status_by_order: dict[str, str],
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for candidate in candidates:
        try:
            phone, username = resolve_whatsapp_recipient(
                candidate["recipient_phone"],
                candidate["recipient_username"],
            )
            recipient = _masked_reminder_recipient(phone, username)
            status = job_status_by_order.get(candidate["order_id"], "eligible")
        except ValueError:
            recipient = "sin contacto"
            status = "missing_contact"
        payload.append(
            {
                "order_id": candidate["order_id"],
                "applicant_name": candidate["applicant_name"],
                "appointment_day": candidate["appointment_day"].isoformat(),
                "appointment_date_label": _appointment_day_text(
                    candidate["appointment_day"]
                ),
                "appointment_hour": candidate["appointment_hour"],
                "site": candidate["site"],
                "recipient": recipient,
                "status": status,
            }
        )
    return payload


__all__ = [
    "AppointmentReminderScheduler",
    "appointment_reminder_message",
    "appointment_reminder_status_payload",
    "reconcile_appointment_reminders",
    "validate_reminder_template",
]
