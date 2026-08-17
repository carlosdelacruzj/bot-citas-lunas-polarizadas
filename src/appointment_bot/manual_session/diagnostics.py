from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Request, Response

from appointment_bot.config import Settings

logger = logging.getLogger(__name__)

RESERVATION_BUTTON_SUFFIX = "btgSiguiente"
HONEYPOT_SUFFIX = "txtHoneypot"
CAPTCHA_FIELD_SUFFIX = "txtimg"
SAFE_VALUE_SUFFIXES = ("cbosede", "cboFecha", "cboHora", RESERVATION_BUTTON_SUFFIX)
TOKEN_FIELDS = {"__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"}

_DIAGNOSTIC_SCRIPT = r"""
(() => {
  if (window.__appointmentManualDiagnosticInstalled) return;
  window.__appointmentManualDiagnosticInstalled = true;
  window.__appointmentManualDiagnosticEvents = [];
  window.__appointmentManualDiagnosticBlocked = false;

  const now = () => new Date().toISOString();
  const visible = (element) => {
    if (!element) return false;
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden"
      && rect.width > 0 && rect.height > 0;
  };
  const safeValue = (element) => {
    const name = String(element.name || element.id || "");
    const value = String(element.value || "");
    const lower = name.toLowerCase();
    const allowValue = lower.endsWith("cbosede") || lower.endsWith("cbofecha")
      || lower.endsWith("cbohora") || lower.endsWith("btgsiguiente");
    return {
      id: element.id || null,
      name: element.name || null,
      tag: element.tagName ? element.tagName.toLowerCase() : null,
      input_type: element.type || null,
      visible: visible(element),
      disabled: Boolean(element.disabled),
      readonly: Boolean(element.readOnly),
      autocomplete: element.autocomplete || null,
      empty: value.length === 0,
      value_length: value.length,
      safe_value: allowValue ? value : null,
    };
  };
  const push = (event) => {
    const queue = window.__appointmentManualDiagnosticEvents;
    if (!Array.isArray(queue)) return;
    queue.push({ at_utc: now(), path: location.pathname, ...event });
    if (queue.length > 500) queue.splice(0, queue.length - 500);
  };
  const isHoneypotControl = (element) => {
    if (!(element instanceof Element)) return false;
    const name = String(element.getAttribute("name") || element.id || "").toLowerCase();
    return name.endsWith("txthoneypot");
  };
  const valueShape = (value) => {
    const normalized = String(value ?? "");
    return { empty: normalized.length === 0, value_length: normalized.length };
  };
  const pushHoneypotWrite = (type, element, before, after) => {
    const beforeShape = valueShape(before);
    const afterShape = valueShape(after);
    push({
      type,
      control: safeValue(element),
      before_empty: beforeShape.empty,
      before_value_length: beforeShape.value_length,
      after_empty: afterShape.empty,
      after_value_length: afterShape.value_length,
      changed: String(before ?? "") !== String(after ?? ""),
    });
  };
  const installHoneypotWriteObservers = () => {
    const valueDescriptor = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value"
    );
    if (valueDescriptor?.get && valueDescriptor?.set && valueDescriptor.configurable) {
      Object.defineProperty(HTMLInputElement.prototype, "value", {
        ...valueDescriptor,
        get() {
          return valueDescriptor.get.call(this);
        },
        set(nextValue) {
          const tracked = isHoneypotControl(this);
          const before = tracked ? valueDescriptor.get.call(this) : null;
          valueDescriptor.set.call(this, nextValue);
          if (tracked) {
            pushHoneypotWrite(
              "honeypot_value_assignment",
              this,
              before,
              valueDescriptor.get.call(this)
            );
          }
        },
      });
    } else {
      push({ type: "honeypot_value_observer_unavailable" });
    }

    const originalSetAttribute = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function(name, value) {
      const tracked = String(name || "").toLowerCase() === "value"
        && isHoneypotControl(this);
      const before = tracked ? this.getAttribute("value") : null;
      const result = originalSetAttribute.call(this, name, value);
      if (tracked) {
        pushHoneypotWrite(
          "honeypot_value_attribute_assignment",
          this,
          before,
          this.getAttribute("value")
        );
      }
      return result;
    };
  };
  installHoneypotWriteObservers();
  const honeypot = () => document.querySelector("#MainContent_idUcitas_txtHoneypot");
  const reserveTarget = (element) => {
    const name = String(element?.name || element?.id || "").toLowerCase();
    return name.endsWith("btgsiguiente");
  };
  const guardHoneypot = (event) => {
    const trap = honeypot();
    if (!trap || String(trap.value || "").length === 0) return false;
    event.preventDefault();
    event.stopImmediatePropagation();
    push({ type: "honeypot_blocked", control: safeValue(trap) });
    if (!window.__appointmentManualDiagnosticBlocked) {
      window.__appointmentManualDiagnosticBlocked = true;
      window.alert(
        "Envio bloqueado: el campo trampa contiene datos. "
          + "Cierra la sesion y revisa el informe diagnostico."
      );
    }
    return true;
  };

  document.addEventListener("input", (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) {
      push({ type: "control_input", control: safeValue(event.target) });
    }
  }, true);
  document.addEventListener("change", (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) {
      push({ type: "control_change", control: safeValue(event.target) });
    }
  }, true);
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement) || !reserveTarget(target)) return;
    const trap = honeypot();
    push({
      type: "reserve_click",
      control: safeValue(target),
      honeypot: trap ? safeValue(trap) : null,
    });
    guardHoneypot(event);
  }, true);
  document.addEventListener("submit", (event) => {
    const submitter = event.submitter;
    const trap = honeypot();
    push({
      type: "form_submit",
      submitter: submitter ? safeValue(submitter) : null,
      honeypot: trap ? safeValue(trap) : null,
    });
    guardHoneypot(event);
  }, true);
  document.addEventListener("DOMContentLoaded", () => {
    push({
      type: "document_ready",
      controls: [...document.querySelectorAll("input, select, button")].map(safeValue),
    });
  }, { once: true });
})();
"""


class ManualDiagnosticRecorder:
    def __init__(self, settings: Settings, session_id: str, order_id: str) -> None:
        day = datetime.now().strftime("%d-%m-%Y")
        self.report_path = (
            settings.screenshots_dir
            / day
            / "manual-diagnostics"
            / session_id
            / "report.json"
        )
        self.session_id = session_id
        self.order_id = order_id
        self.started_at = _now()
        self.events: list[dict[str, object]] = []
        self.submission_seen = False
        self.honeypot_blocked = False
        self._sequence = 0
        self._lock = threading.Lock()
        self._write_report(state="opening")

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self.events)

    def attach(self, page: Page) -> None:
        page.add_init_script(_DIAGNOSTIC_SCRIPT)
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        try:
            page.evaluate(_DIAGNOSTIC_SCRIPT)
        except PlaywrightError:
            logger.debug("Diagnostic script will be installed on the first navigation")
        self.record("browser_opened", path=_safe_path(page.url))

    def poll(self, page: Page) -> None:
        try:
            browser_events = page.evaluate(
                """() => {
                    const events = window.__appointmentManualDiagnosticEvents || [];
                    window.__appointmentManualDiagnosticEvents = [];
                    return events;
                }"""
            )
        except PlaywrightError:
            return
        if not isinstance(browser_events, list) or not browser_events:
            return
        with self._lock:
            for event in browser_events:
                if not isinstance(event, dict):
                    continue
                normalized = dict(event)
                normalized["source"] = "dom"
                normalized["sequence"] = self._next_sequence()
                self.events.append(normalized)
                if normalized.get("type") == "honeypot_blocked":
                    self.honeypot_blocked = True
            self._write_report_locked(state="active")

    def record(self, event_type: str, **details: object) -> None:
        with self._lock:
            self.events.append(
                {
                    "sequence": self._next_sequence(),
                    "at_utc": _now(),
                    "source": "playwright",
                    "type": event_type,
                    **details,
                }
            )
            self._write_report_locked(state="active")

    def finish(self, *, state: str, error: str | None = None) -> None:
        with self._lock:
            self._write_report_locked(state=state, finished_at=_now(), error=error)

    def _on_request(self, request: Request) -> None:
        if request.method.upper() != "POST":
            return
        body = request.post_data or ""
        fields = _sanitize_post_fields(body)
        honeypot_field = next(
            (
                field
                for field in fields
                if str(field.get("name") or "").endswith(HONEYPOT_SUFFIX)
            ),
            None,
        )
        reserve_post = any(
            str(field.get("name") or "").endswith(RESERVATION_BUTTON_SUFFIX)
            for field in fields
        )
        if reserve_post:
            self.submission_seen = True
        self.record(
            "post_request",
            path=_safe_path(request.url),
            resource_type=request.resource_type,
            body_length=len(body.encode("utf-8")),
            reserve_post=reserve_post,
            honeypot_present=honeypot_field is not None,
            honeypot_empty=(honeypot_field or {}).get("empty"),
            honeypot_value_length=(honeypot_field or {}).get("value_length"),
            fields=fields,
        )

    def _on_response(self, response: Response) -> None:
        if response.request.method.upper() != "POST":
            return
        self.record(
            "post_response",
            path=_safe_path(response.url),
            status=response.status,
            reserve_post=_request_is_reservation_submit(response.request),
        )

    def _next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def _write_report(self, *, state: str) -> None:
        with self._lock:
            self._write_report_locked(state=state)

    def _write_report_locked(
        self,
        *,
        state: str,
        finished_at: str | None = None,
        error: str | None = None,
    ) -> None:
        payload = {
            "schema_version": 2,
            "session_id": self.session_id,
            "order_id": self.order_id,
            "state": state,
            "started_at": self.started_at,
            "updated_at": _now(),
            "finished_at": finished_at,
            "submission_seen": self.submission_seen,
            "honeypot_blocked": self.honeypot_blocked,
            "event_count": len(self.events),
            "error": error,
            "privacy": {
                "raw_post_body_saved": False,
                "cookies_saved": False,
                "captcha_answer_saved": False,
                "aspnet_tokens_saved": False,
                "credentials_saved": False,
                "honeypot_value_saved": False,
            },
            "events": self.events,
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(self.report_path)


def _sanitize_post_fields(body: str) -> list[dict[str, object]]:
    fields: list[dict[str, object]] = []
    for name, value in parse_qsl(body, keep_blank_values=True):
        descriptor: dict[str, object] = {
            "name": name,
            "empty": value == "",
            "value_length": len(value),
        }
        if name in TOKEN_FIELDS:
            descriptor["value_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
            descriptor["classification"] = "aspnet_token"
        elif name.endswith(HONEYPOT_SUFFIX):
            descriptor["classification"] = "honeypot"
        elif name.endswith(CAPTCHA_FIELD_SUFFIX):
            descriptor["classification"] = "captcha_answer_redacted"
        elif name.endswith(SAFE_VALUE_SUFFIXES) or name == "__EVENTTARGET":
            descriptor["classification"] = "operational"
            descriptor["safe_value"] = value
        else:
            descriptor["classification"] = "redacted"
        fields.append(descriptor)
    return fields


def _request_is_reservation_submit(request: Request) -> bool:
    body = request.post_data or ""
    return any(
        name.endswith(RESERVATION_BUTTON_SUFFIX)
        for name, _value in parse_qsl(body, keep_blank_values=True)
    )


def _safe_path(url: str) -> str:
    return urlsplit(url).path or "about:blank"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")
