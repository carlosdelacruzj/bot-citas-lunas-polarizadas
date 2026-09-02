from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Page, Request, Response

logger = logging.getLogger(__name__)

RESERVATION_BUTTON_NAME = "ctl00$MainContent$idUcitas$btgSiguiente"
HONEYPOT_NAME = "ctl00$MainContent$idUcitas$txtHoneypot"
CAPTCHA_NAME = "ctl00$MainContent$idUcitas$txtimg"
SAFE_VALUE_NAMES = {
    "ctl00$MainContent$idUcitas$cbosede",
    "ctl00$MainContent$idUcitas$cboFecha",
    "ctl00$MainContent$idUcitas$cboHora",
    RESERVATION_BUTTON_NAME,
    "__EVENTTARGET",
}
TOKEN_FIELDS = {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"}

MANUAL_RESERVATION_FIELDS = {
    "ctl00$ScriptManager1",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtTramite",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtMotivo",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtdni",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtNacionalidad",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtPaterno",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtMaterno",
    "ctl00$MainContent$TabContainer1$TabPanelDatosP$txtNombres",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtTipoV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtPlacaV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtMarcaV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtModeloV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtCarroV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtSerieV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtMotorV",
    "ctl00$MainContent$TabContainer1$TabPanel1$txtColorV",
    "ctl00$MainContent$TabContainer1$TabPanel4$txtSecuencia",
    "ctl00$MainContent$TabContainer1$TabPanel4$txtfechamovimiento",
    "ctl00$MainContent$TabContainer1$TabPanel4$txtcodcaja",
    "ctl00$MainContent$TxtMensajeCita",
    "ctl00$MainContent$txtRespuestaI",
    "ctl00$MainContent$idUcitas$cbosede",
    "ctl00$MainContent$idUcitas$cboFecha",
    "ctl00$MainContent$idUcitas$cboHora",
    "ctl00$MainContent$TabContainer1$TabPanel2$txtRuc",
    "ctl00$MainContent$TabContainer1$TabPanel2$txtRazonSocial",
    HONEYPOT_NAME,
    CAPTCHA_NAME,
    "ctl00$MainContent$idUcitas$xzl",
    "ctl00$MainContent$idUcitas$txtCodigo",
    "ctl00$MainContent$txtObservacionCancel",
    "__EVENTTARGET",
    "__EVENTARGUMENT",
    "__LASTFOCUS",
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "MainContent_TabContainer1_ClientState",
    "__VIEWSTATEENCRYPTED",
    "__ASYNCPOST",
    RESERVATION_BUTTON_NAME,
}

PROTECTED_EMPTY_FIELDS = {
    HONEYPOT_NAME,
    "ctl00$MainContent$idUcitas$xzl",
    "ctl00$MainContent$idUcitas$txtCodigo",
    "ctl00$MainContent$txtRespuestaI",
    "ctl00$MainContent$txtObservacionCancel",
}

MANUAL_EMPTY_FIELDS = {
    *PROTECTED_EMPTY_FIELDS,
    "__EVENTTARGET",
    "__EVENTARGUMENT",
    "__LASTFOCUS",
    "__VIEWSTATEENCRYPTED",
}

REQUIRED_NONEMPTY_FIELDS = {
    "ctl00$MainContent$idUcitas$cbosede",
    "ctl00$MainContent$idUcitas$cboFecha",
    "ctl00$MainContent$idUcitas$cboHora",
    CAPTCHA_NAME,
    RESERVATION_BUTTON_NAME,
}

ASP_NET_SUBMIT_RUNTIME_FIELDS = {"ctl00$ScriptManager1", "__ASYNCPOST"}


def inspect_reservation_form(page: Page) -> dict[str, Any]:
    raw_fields = page.locator("#MainContent_idUcitas_btgSiguiente").first.evaluate(
        """button => {
            const form = button.form;
            if (!form) throw new Error("Reservation button has no form");
            const data = new FormData(form);
            if (button.name) data.append(button.name, button.value || "");
            return Array.from(data.entries()).map(([name, value]) => ({
                name: String(name),
                value: typeof value === "string" ? value : `[file:${value.size}]`,
            }));
        }"""
    )
    fields = [
        (str(item.get("name") or ""), str(item.get("value") or ""))
        for item in raw_fields
        if isinstance(item, dict) and item.get("name")
    ]
    return summarize_reservation_fields(fields, source="dom_pre_submit")


def validate_reservation_form_audit(audit: dict[str, Any]) -> None:
    protected_nonempty = list(audit.get("protected_nonempty_fields") or [])
    unexpected_nonempty = list(audit.get("unexpected_nonempty_fields") or [])
    missing_required = list(audit.get("missing_required_fields") or [])
    empty_required = list(audit.get("empty_required_fields") or [])
    if protected_nonempty:
        raise RuntimeError(
            "Reservation submit blocked because protected fields are not empty: "
            + ", ".join(protected_nonempty)
        )
    if unexpected_nonempty:
        raise RuntimeError(
            "Reservation submit blocked because unexpected fields contain data: "
            + ", ".join(unexpected_nonempty)
        )
    if missing_required or empty_required:
        problems = [
            *(f"missing:{name}" for name in missing_required),
            *(f"empty:{name}" for name in empty_required),
        ]
        raise RuntimeError(
            "Reservation submit blocked because required fields are invalid: "
            + ", ".join(problems)
        )


def summarize_reservation_fields(
    fields: Iterable[tuple[str, str]],
    *,
    source: str,
) -> dict[str, Any]:
    pairs = list(fields)
    descriptors = [_field_descriptor(name, value) for name, value in pairs]
    actual_names = [name for name, _value in pairs]
    actual_name_set = set(actual_names)
    values_by_name = {name: value for name, value in pairs}
    unexpected_fields = sorted(actual_name_set - MANUAL_RESERVATION_FIELDS)
    unexpected_nonempty_fields = sorted(
        name for name in unexpected_fields if values_by_name.get(name, "") != ""
    )
    protected_nonempty_fields = sorted(
        name
        for name in PROTECTED_EMPTY_FIELDS
        if name in values_by_name and values_by_name[name] != ""
    )
    missing_required_fields = sorted(REQUIRED_NONEMPTY_FIELDS - actual_name_set)
    empty_required_fields = sorted(
        name
        for name in REQUIRED_NONEMPTY_FIELDS
        if name in values_by_name and values_by_name[name] == ""
    )
    manual_empty_state_mismatches = sorted(
        name
        for name in MANUAL_RESERVATION_FIELDS & actual_name_set
        if (values_by_name[name] == "") != (name in MANUAL_EMPTY_FIELDS)
    )
    honeypot_value = values_by_name.get(HONEYPOT_NAME)
    return {
        "schema_version": 1,
        "source": source,
        "field_count": len(pairs),
        "nonempty_field_count": sum(value != "" for _name, value in pairs),
        "empty_field_count": sum(value == "" for _name, value in pairs),
        "manual_field_names_match": (
            len(pairs) == len(MANUAL_RESERVATION_FIELDS)
            and actual_name_set == MANUAL_RESERVATION_FIELDS
        ),
        "manual_core_field_names_match": (
            actual_name_set - ASP_NET_SUBMIT_RUNTIME_FIELDS
            == MANUAL_RESERVATION_FIELDS - ASP_NET_SUBMIT_RUNTIME_FIELDS
        ),
        "manual_empty_state_match": not manual_empty_state_mismatches,
        "manual_empty_state_mismatches": manual_empty_state_mismatches,
        "unexpected_fields": unexpected_fields,
        "unexpected_nonempty_fields": unexpected_nonempty_fields,
        "missing_manual_fields": sorted(MANUAL_RESERVATION_FIELDS - actual_name_set),
        "protected_nonempty_fields": protected_nonempty_fields,
        "missing_required_fields": missing_required_fields,
        "empty_required_fields": empty_required_fields,
        "honeypot_present": honeypot_value is not None,
        "honeypot_empty": honeypot_value == "" if honeypot_value is not None else None,
        "honeypot_value_length": (
            len(honeypot_value) if honeypot_value is not None else None
        ),
        "privacy": {
            "raw_body_saved": False,
            "captcha_answer_saved": False,
            "tokens_saved": False,
            "personal_values_saved": False,
            "honeypot_value_saved": False,
        },
        "fields": descriptors,
    }


class ReservationPostCollector:
    def __init__(self, audit_target: dict[str, Any]) -> None:
        self.audit_target = audit_target
        self.request: Request | None = None

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def detach(self, page: Page) -> None:
        page.remove_listener("request", self._on_request)
        page.remove_listener("response", self._on_response)

    def wait_for_response(self, page: Page, *, timeout_ms: int = 5_000) -> None:
        deadline = time.monotonic() + (timeout_ms / 1000)
        while time.monotonic() < deadline:
            if self.audit_target.get("response_status") is not None:
                return
            page.wait_for_timeout(50)
        self.audit_target["response_wait_timed_out"] = True

    def _on_request(self, request: Request) -> None:
        if request.method.upper() != "POST":
            return
        body = request.post_data or ""
        fields = parse_qsl(body, keep_blank_values=True)
        if not any(name == RESERVATION_BUTTON_NAME for name, _value in fields):
            return
        self.request = request
        self.audit_target.clear()
        self.audit_target.update(
            summarize_reservation_fields(fields, source="playwright_post_request")
        )
        self.audit_target.update(
            {
                "request_seen": True,
                "path": urlsplit(request.url).path,
                "resource_type": request.resource_type,
                "body_length": len(body.encode("utf-8")),
                "response_status": None,
                "response_wait_timed_out": False,
            }
        )

    def _on_response(self, response: Response) -> None:
        if self.request is None or response.request != self.request:
            return
        self.audit_target["response_status"] = response.status
        logger.info(
            "Captured sanitized reservation POST audit: fields=%s status=%s manual_shape=%s",
            self.audit_target.get("field_count"),
            response.status,
            self.audit_target.get("manual_field_names_match"),
        )


def _field_descriptor(name: str, value: str) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "field_name": name,
        "empty": value == "",
        "value_length": len(value),
    }
    if name in TOKEN_FIELDS:
        descriptor["value_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        descriptor["classification"] = "aspnet_token"
    elif name == HONEYPOT_NAME:
        descriptor["classification"] = "honeypot"
    elif name == CAPTCHA_NAME:
        descriptor["classification"] = "captcha_answer_redacted"
    elif name in SAFE_VALUE_NAMES:
        descriptor["classification"] = "operational"
        descriptor["safe_value"] = value
    else:
        descriptor["classification"] = "redacted"
    return descriptor
