from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Page, Request, Response

from appointment_bot.reservation_engine.appointment_contracts import (
    PortalContractChanged,
)

logger = logging.getLogger(__name__)

RESERVATION_BUTTON_NAME = "ctl00$MainContent$idUcitas$btgSiguiente"
HONEYPOT_NAME = "ctl00$MainContent$idUcitas$txtHoneypot"
CURRENT_HONEYPOT_NAME = "website_url"
HONEYPOT_NAMES = {HONEYPOT_NAME, CURRENT_HONEYPOT_NAME}
CAPTCHA_NAME = "ctl00$MainContent$idUcitas$txtimg"
PRE_ACCESS_TOKEN_NAME = "ctl00$MainContent$idUcitas$hfRecaptchaToken"
PRE_ACCESS_VERIFIED_NAME = "ctl00$MainContent$idUcitas$hfRecaptchaVerificado"
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
    CURRENT_HONEYPOT_NAME,
    CAPTCHA_NAME,
    PRE_ACCESS_TOKEN_NAME,
    PRE_ACCESS_VERIFIED_NAME,
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
    *HONEYPOT_NAMES,
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
    *TOKEN_FIELDS,
}

ASP_NET_SUBMIT_RUNTIME_FIELDS = {"ctl00$ScriptManager1", "__ASYNCPOST"}


def inspect_reservation_form(page: Page) -> dict[str, Any]:
    raw = page.locator("#MainContent_idUcitas_btgSiguiente").first.evaluate(
        """button => {
            const form = button.form;
            if (!form) throw new Error("Reservation button has no form");
            const data = new FormData(form);
            if (button.name) data.append(button.name, button.value || "");
            const controls = Array.from(form.elements);
            const countByName = name => controls.filter(item => item.name === name).length;
            const valuesByName = name => controls
                .filter(item => item.name === name)
                .map(item => item.value || "");
            const honeypots = controls.filter(item => item.matches(
                "#hfHoneypot, #MainContent_idUcitas_txtHoneypot"
            ));
            const action = new URL(form.getAttribute("action") || location.href, location.href);
            const question = document.querySelector(
                "#MainContent_idUcitas_lblCaptchaOperacion"
            );
            const questionRect = question?.getBoundingClientRect();
            const questionStyle = question ? window.getComputedStyle(question) : null;
            return {
                fields: Array.from(data.entries()).map(([name, value]) => ({
                    name: String(name),
                    value: typeof value === "string" ? value : `[file:${value.size}]`,
                })),
                contract: {
                    formCount: document.forms.length,
                    formId: form.id || "",
                    fieldNames: controls
                        .map(item => item.name || "")
                        .filter(Boolean)
                        .sort(),
                    method: (form.method || "").toLowerCase(),
                    actionPath: action.pathname,
                    sameOrigin: action.origin === location.origin,
                    target: form.target || "",
                    reservationButtonIdCount: document.querySelectorAll(
                        "#MainContent_idUcitas_btgSiguiente"
                    ).length,
                    reservationButtonNameCount: countByName(
                        "ctl00$MainContent$idUcitas$btgSiguiente"
                    ),
                    reservationButtonValue: button.value || "",
                    reservationButtonType: button.type || "",
                    reservationButtonOnclick: button.getAttribute("onclick") || "",
                    siteCount: countByName("ctl00$MainContent$idUcitas$cbosede"),
                    dateCount: countByName("ctl00$MainContent$idUcitas$cboFecha"),
                    hourCount: countByName("ctl00$MainContent$idUcitas$cboHora"),
                    captchaInputCount: countByName(
                        "ctl00$MainContent$idUcitas$txtimg"
                    ),
                    honeypotCount: honeypots.length,
                    honeypotKnownName: honeypots.length === 1 && [
                        "website_url",
                        "ctl00$MainContent$idUcitas$txtHoneypot"
                    ].includes(honeypots[0].name),
                    viewstateCount: countByName("__VIEWSTATE"),
                    viewstateGeneratorCount: countByName("__VIEWSTATEGENERATOR"),
                    eventValidationCount: countByName("__EVENTVALIDATION"),
                    preAccessTokenCount: countByName(
                        "ctl00$MainContent$idUcitas$hfRecaptchaToken"
                    ),
                    preAccessTokenNonempty: valuesByName(
                        "ctl00$MainContent$idUcitas$hfRecaptchaToken"
                    ).every(value => Boolean(value)),
                    preAccessVerifiedCount: countByName(
                        "ctl00$MainContent$idUcitas$hfRecaptchaVerificado"
                    ),
                    preAccessVerified: valuesByName(
                        "ctl00$MainContent$idUcitas$hfRecaptchaVerificado"
                    ).every(value => value === "1"),
                    mathQuestionCount: document.querySelectorAll(
                        "#MainContent_idUcitas_lblCaptchaOperacion"
                    ).length,
                    mathQuestionVisible: Boolean(
                        question
                        && questionRect
                        && questionRect.width >= 40
                        && questionRect.height >= 20
                        && questionStyle
                        && questionStyle.display !== "none"
                        && questionStyle.visibility !== "hidden"
                        && (question.textContent || "").trim()
                    )
                }
            };
        }"""
    )
    fields = [
        (str(item.get("name") or ""), str(item.get("value") or ""))
        for item in raw.get("fields") or []
        if isinstance(item, dict) and item.get("name")
    ]
    audit = summarize_reservation_fields(fields, source="dom_pre_submit")
    contract = dict(raw.get("contract") or {})
    audit["form_contract"] = contract
    audit["form_contract_sha256"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return audit


def validate_reservation_form_audit(
    audit: dict[str, Any],
    *,
    require_captcha_answer: bool = True,
    require_math_question: bool = True,
    pre_access_only: bool = False,
) -> None:
    if pre_access_only and (require_captcha_answer or require_math_question):
        raise ValueError("Pre-access-only submission cannot require a final CAPTCHA.")
    protected_nonempty = list(audit.get("protected_nonempty_fields") or [])
    unexpected_fields = list(audit.get("unexpected_fields") or [])
    missing_required = list(audit.get("missing_required_fields") or [])
    empty_required = list(audit.get("empty_required_fields") or [])
    if protected_nonempty:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: hay campos protegidos con contenido: "
            + ", ".join(protected_nonempty)
        )
    if unexpected_fields:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: aparecieron campos no reconocidos: "
            + ", ".join(unexpected_fields)
        )
    if audit.get("honeypot_present") is not True or audit.get("honeypot_empty") is not True:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el honeypot final falta o no esta vacio."
        )

    contract = dict(audit.get("form_contract") or {})
    expected_counts = {
        "formCount": 1,
        "reservationButtonIdCount": 1,
        "reservationButtonNameCount": 1,
        "siteCount": 1,
        "dateCount": 1,
        "hourCount": 1,
        "captchaInputCount": 0 if pre_access_only else 1,
        "honeypotCount": 1,
        "viewstateCount": 1,
        "viewstateGeneratorCount": 1,
        "eventValidationCount": 1,
        "preAccessTokenCount": 1,
        "preAccessVerifiedCount": 1,
    }
    if require_math_question:
        expected_counts["mathQuestionCount"] = 1
    elif pre_access_only:
        expected_counts["mathQuestionCount"] = 0
    count_mismatches = [
        f"{name}={contract.get(name)!r}"
        for name, expected in expected_counts.items()
        if contract.get(name) != expected
    ]
    contract_mismatches = list(count_mismatches)
    if pre_access_only:
        if contract.get("reservationButtonType") != "submit":
            contract_mismatches.append("reservationButtonType changed")
        handler = "".join(str(contract.get("reservationButtonOnclick") or "").split())
        if handler != "if(this.disabled){returnfalse;};":
            contract_mismatches.append("reservationButtonOnclick changed")
    if contract.get("formId") != "form1":
        contract_mismatches.append(f"formId={contract.get('formId')!r}")
    if contract.get("method") != "post":
        contract_mismatches.append(f"method={contract.get('method')!r}")
    if contract.get("sameOrigin") is not True:
        contract_mismatches.append("sameOrigin=false")
    if contract.get("honeypotKnownName") is not True:
        contract_mismatches.append("honeypotKnownName=false")
    if contract.get("preAccessTokenNonempty") is not True:
        contract_mismatches.append("preAccessTokenNonempty=false")
    if contract.get("preAccessVerified") is not True:
        contract_mismatches.append("preAccessVerified=false")
    if not str(contract.get("actionPath") or "").lower().endswith(
        "/seguimiento.aspx"
    ):
        contract_mismatches.append(f"actionPath={contract.get('actionPath')!r}")
    if str(contract.get("target") or "").lower() not in {"", "_self"}:
        contract_mismatches.append(f"target={contract.get('target')!r}")
    if (
        str(contract.get("reservationButtonValue") or "").strip().lower()
        != "reservar cita"
    ):
        contract_mismatches.append(
            f"reservationButtonValue={contract.get('reservationButtonValue')!r}"
        )
    if require_math_question and contract.get("mathQuestionVisible") is not True:
        contract_mismatches.append("mathQuestionVisible=false")
    if contract_mismatches:
        raise PortalContractChanged(
            "Cambio de seguridad del portal: la estructura final no coincide con "
            "el contrato conocido: "
            + ", ".join(contract_mismatches)
        )

    if missing_required or empty_required:
        if not require_captcha_answer:
            missing_required = [name for name in missing_required if name != CAPTCHA_NAME]
            empty_required = [name for name in empty_required if name != CAPTCHA_NAME]
        problems = [
            *(f"missing:{name}" for name in missing_required),
            *(f"empty:{name}" for name in empty_required),
        ]
        if problems:
            raise PortalContractChanged(
                "Cambio de seguridad del portal: hay campos obligatorios invalidos: "
                + ", ".join(problems)
            )
    if (
        not require_captcha_answer and not pre_access_only
        and audit.get("captcha_empty") is not True
    ):
        raise PortalContractChanged(
            "Cambio de seguridad del portal: el campo CAPTCHA final ya contiene un valor."
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
    name_counts = {name: actual_names.count(name) for name in actual_name_set}
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
    honeypot_values = [
        value for name, value in pairs if name in HONEYPOT_NAMES
    ]
    honeypot_value = honeypot_values[0] if len(honeypot_values) == 1 else None
    captcha_value = values_by_name.get(CAPTCHA_NAME)
    manual_core_fields = (
        MANUAL_RESERVATION_FIELDS - ASP_NET_SUBMIT_RUNTIME_FIELDS - HONEYPOT_NAMES
    )
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
            actual_name_set - ASP_NET_SUBMIT_RUNTIME_FIELDS - HONEYPOT_NAMES
            == manual_core_fields
        ),
        "manual_empty_state_match": not manual_empty_state_mismatches,
        "manual_empty_state_mismatches": manual_empty_state_mismatches,
        "unexpected_fields": unexpected_fields,
        "unexpected_nonempty_fields": unexpected_nonempty_fields,
        "missing_manual_fields": sorted(MANUAL_RESERVATION_FIELDS - actual_name_set),
        "missing_manual_core_fields": sorted(manual_core_fields - actual_name_set),
        "duplicate_field_names": sorted(
            name for name, count in name_counts.items() if count != 1
        ),
        "protected_nonempty_fields": protected_nonempty_fields,
        "missing_required_fields": missing_required_fields,
        "empty_required_fields": empty_required_fields,
        "honeypot_present": len(honeypot_values) == 1,
        "honeypot_empty": honeypot_value == "" if len(honeypot_values) == 1 else None,
        "honeypot_value_length": (
            len(honeypot_value) if honeypot_value is not None else None
        ),
        "captcha_present": captcha_value is not None,
        "captcha_empty": captcha_value == "" if captcha_value is not None else None,
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
    elif name in HONEYPOT_NAMES:
        descriptor["classification"] = "honeypot"
    elif name == CAPTCHA_NAME:
        descriptor["classification"] = "captcha_answer_redacted"
    elif name in SAFE_VALUE_NAMES:
        descriptor["classification"] = "operational"
        descriptor["safe_value"] = value
    else:
        descriptor["classification"] = "redacted"
    return descriptor
