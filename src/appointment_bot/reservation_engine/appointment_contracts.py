from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    event_id: str
    attempt: int | None
    phase: str
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
    post_detected: bool
    post_count: int
    post_url: str | None
    post_status: int | None
    post_elapsed_ms: int | None
    post_content_length: int | None
    post_resource_type: str | None
    post_failure: str | None

    def details(self) -> dict[str, Any]:
        return {
            "site_refresh_selected_site": self.selected_site,
            "site_refresh_attempt": self.attempt,
            "site_refresh_phase": self.phase,
            "site_refresh_confirmed": self.confirmed,
            "site_refresh_changed": self.changed,
            "site_refresh_marker_cleared": self.marker_cleared,
            "site_refresh_async_completed": self.async_completed,
            "site_refresh_elapsed_ms": self.elapsed_ms,
            "site_refresh_date_signature_before": self.date_signature_before,
            "site_refresh_date_signature_after": self.date_signature_after,
            "site_refresh_hour_signature_before": self.hour_signature_before,
            "site_refresh_hour_signature_after": self.hour_signature_after,
            "site_refresh_post_detected": self.post_detected,
            "site_refresh_post_count": self.post_count,
            "site_refresh_post_url": self.post_url,
            "site_refresh_post_status": self.post_status,
            "site_refresh_post_elapsed_ms": self.post_elapsed_ms,
            "site_refresh_post_content_length": self.post_content_length,
            "site_refresh_post_resource_type": self.post_resource_type,
            "site_refresh_post_failure": self.post_failure,
        }

    def history_item(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "attempt": self.attempt,
            "phase": self.phase,
            "selected_site": self.selected_site,
            "post_detected": self.post_detected,
            "post_count": self.post_count,
            "post_url": self.post_url,
            "http_status": self.post_status,
            "post_elapsed_ms": self.post_elapsed_ms,
            "post_content_length": self.post_content_length,
            "post_resource_type": self.post_resource_type,
            "post_failure": self.post_failure,
            "refresh_confirmed": self.confirmed,
            "async_completed": self.async_completed,
            "marker_cleared": self.marker_cleared,
            "options_changed": self.changed,
            "refresh_elapsed_ms": self.elapsed_ms,
            "date_before": self.date_signature_before,
            "date_after": self.date_signature_after,
            "hour_before": self.hour_signature_before,
            "hour_after": self.hour_signature_after,
        }
