from __future__ import annotations

import re
from datetime import date, datetime
from http import HTTPStatus
from typing import Any

from appointment_bot.config import load_settings
from appointment_bot.db.opportunity_bursts import (
    get_active_opportunity_burst,
    get_opportunity_burst_detail,
    list_opportunity_bursts,
)
from appointment_bot.db.opportunity_controls import (
    OpportunityControlConflict,
    OpportunityRuntimeControl,
    get_opportunity_control,
    is_opportunity_admission_allowed,
    reset_opportunity_circuit_breaker,
    update_opportunity_control,
)
from appointment_bot.db.remote_control_audit import record_remote_control_audit
from appointment_bot.services.api.http import error_payload
from appointment_bot.utils.sanitization import sanitize_text

_ACTIONS = {"activate", "deactivate", "drain", "reset_breaker"}
_TARGETS = {"obs006", "obs007"}


def opportunity_control_payload() -> tuple[HTTPStatus, dict[str, Any]]:
    return HTTPStatus.OK, _control_payload(get_opportunity_control())


def update_opportunity_control_payload(
    body: dict[str, Any],
    *,
    requested_by: str | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    action, target, reason, expected_revision, field_errors = _validated_action(body)
    if field_errors:
        payload = error_payload("bad_request", "Revisa el control de oportunidad solicitado.")
        payload["field_errors"] = field_errors
        return HTTPStatus.BAD_REQUEST, payload

    actor = _requested_by(requested_by)
    current = get_opportunity_control()
    active_burst = get_active_opportunity_burst()
    unsafe_reason = _unsafe_reason(
        action=action,
        target=target,
        control=current,
        active_burst=active_burst,
    )
    if unsafe_reason is not None:
        _audit_failure(actor, action, target, expected_revision, unsafe_reason)
        return HTTPStatus.CONFLICT, error_payload("unsafe", unsafe_reason)

    try:
        if action == "reset_breaker":
            updated = reset_opportunity_circuit_breaker(
                expected_revision=expected_revision,
                reset_by=actor,
                reason=reason,
            )
        else:
            updated = update_opportunity_control(
                _database_action(action, target),
                expected_revision=expected_revision,
                updated_by=actor,
                reason=reason,
            )
    except OpportunityControlConflict as exc:
        _audit_failure(actor, action, target, expected_revision, "stale_revision")
        payload = error_payload("stale", sanitize_text(str(exc)))
        payload["current"] = _control_payload(get_opportunity_control())
        return HTTPStatus.CONFLICT, payload

    status_text = "accepted" if updated.application_pending else "applied"
    payload = _control_payload(updated)
    payload.update(
        {
            "status": status_text,
            "message": _action_message(action, target, pending=updated.application_pending),
        }
    )
    return (HTTPStatus.ACCEPTED if updated.application_pending else HTTPStatus.OK), payload


def opportunity_bursts_payload(
    query: dict[str, list[str]],
) -> tuple[HTTPStatus, dict[str, Any]]:
    limit = _query_int(query, "limit", default=20)
    status = _query_status(query)
    if status == "invalid":
        return HTTPStatus.BAD_REQUEST, error_payload(
            "bad_request",
            "El estado debe ser running, draining, closed o aborted.",
        )
    rows = list_opportunity_bursts(limit=limit, status=status)
    return HTTPStatus.OK, {"bursts": [_burst_summary(row) for row in rows]}


def opportunity_burst_payload(
    burst_id: str,
) -> tuple[HTTPStatus, dict[str, Any]]:
    detail = get_opportunity_burst_detail(burst_id)
    if detail is None:
        return HTTPStatus.NOT_FOUND, error_payload("not_found", "Rafaga no encontrada.")
    return HTTPStatus.OK, _json_value(detail)


def opportunity_burst_id(path: str) -> str | None:
    prefix = "/api/v1/opportunity-bursts/"
    if not path.startswith(prefix):
        return None
    candidate = path.removeprefix(prefix).strip()
    if not candidate or len(candidate) > 100 or "/" in candidate:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]+", candidate) is None:
        return ""
    return candidate


def _control_payload(control: OpportunityRuntimeControl) -> dict[str, Any]:
    settings = load_settings(require_login=False)
    active_burst = get_active_opportunity_burst(settings)
    return {
        "revision": control.revision,
        "source": "database",
        "obs006": _mode_payload(control, "obs006", control.burst_mode),
        "obs007": _mode_payload(control, "obs007", control.obs007_mode),
        "breaker": {
            "state": control.circuit_state,
            "reason": control.circuit_reason,
            "opened_at": _timestamp(control.circuit_opened_at),
        },
        "active_burst": _active_burst_payload(active_burst),
        "updated_at": _timestamp(control.updated_at),
        "updated_by": control.updated_by,
        "pending_application": control.application_pending,
    }


def _mode_payload(
    control: OpportunityRuntimeControl,
    target: str,
    desired_mode: str,
) -> dict[str, Any]:
    admissions_allowed = is_opportunity_admission_allowed(target)
    if control.circuit_state == "open":
        effective_mode = "disabled"
    elif desired_mode == "draining":
        effective_mode = "draining"
    else:
        effective_mode = "enabled" if admissions_allowed else "disabled"
    return {
        "desired_mode": desired_mode,
        "effective_mode": effective_mode,
        "admissions_allowed": admissions_allowed,
    }


def _active_burst_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    config = row.get("config_json") if isinstance(row.get("config_json"), dict) else {}
    scheduled = row.get("scheduled_clients")
    if scheduled is None:
        scheduled = row.get("candidate_count")
    if scheduled is None and isinstance(config, dict):
        scheduled = config.get("scheduled_clients")
    return {
        "burst_id": str(row.get("burst_id") or ""),
        "status": str(row.get("status") or "unknown"),
        "started_at": _timestamp(row.get("started_at")),
        "max_active_sessions": int(row.get("max_active_sessions") or 0),
        "scheduled_clients": int(scheduled or 0),
        "completion_reason": row.get("completion_reason"),
    }


def _burst_summary(row: dict[str, Any]) -> dict[str, Any]:
    config = row.get("config_json") if isinstance(row.get("config_json"), dict) else {}
    opportunities = (
        row.get("opportunities_json") if isinstance(row.get("opportunities_json"), list) else []
    )
    candidate_count = row.get("candidate_count")
    if candidate_count is None:
        candidate_count = len(opportunities)
    scheduled = row.get("scheduled_clients")
    if scheduled is None and isinstance(config, dict):
        scheduled = config.get("scheduled_clients")
    return {
        "burst_id": str(row.get("burst_id") or ""),
        "status": str(row.get("status") or "unknown"),
        "started_at": _timestamp(row.get("started_at")),
        "finished_at": _timestamp(row.get("finished_at")),
        "completion_reason": row.get("completion_reason"),
        "max_active_sessions": int(row.get("max_active_sessions") or 0),
        "candidate_count": int(candidate_count or 0),
        "scheduled_clients": int(scheduled or 0),
    }


def _validated_action(
    body: dict[str, Any],
) -> tuple[str, str, str, int, dict[str, str]]:
    action = str(body.get("action") or "").strip().lower()
    target = str(body.get("target") or "").strip().lower()
    reason = str(body.get("reason") or "").strip()
    expected_revision = body.get("expected_revision")
    errors: dict[str, str] = {}
    if action not in _ACTIONS:
        errors["action"] = "Usa activate, deactivate, drain o reset_breaker."
    if target not in _TARGETS:
        errors["target"] = "Usa obs006 u obs007."
    if not reason:
        errors["reason"] = "Explica el motivo del cambio."
    elif len(reason) > 240:
        errors["reason"] = "El motivo no puede superar 240 caracteres."
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        errors["expected_revision"] = "Debe ser una revision entera."
        expected_revision = -1
    elif expected_revision < 0:
        errors["expected_revision"] = "La revision no puede ser negativa."
    return action, target, reason, int(expected_revision), errors


def _unsafe_reason(
    *,
    action: str,
    target: str,
    control: OpportunityRuntimeControl,
    active_burst: dict[str, Any] | None,
) -> str | None:
    if control.revision != 0 and control.application_pending and action != "reset_breaker":
        return "Hay un cambio pendiente de aplicar. Actualiza antes de solicitar otro."
    if action == "activate" and control.circuit_state == "open":
        return "El breaker esta abierto. Revisalo y resetealo antes de activar."
    if action == "reset_breaker" and control.circuit_state != "open":
        return "El breaker ya esta cerrado; no hay nada que resetear."
    if action == "drain" and target != "obs006":
        return "El drenaje solo aplica a las ráfagas de oportunidad."
    if action == "drain" and active_burst is None:
        return "No hay una rafaga activa que drenar."
    if action == "deactivate" and target == "obs006" and active_burst is not None:
        return "Hay una ráfaga activa. Solicita drain para cerrarla con seguridad."
    return None


def _database_action(action: str, target: str) -> str:
    prefix = "enable" if action == "activate" else action
    return f"{prefix}_{target}"


def _action_message(action: str, target: str, *, pending: bool) -> str:
    verb = {
        "activate": "Activacion",
        "deactivate": "Desactivacion",
        "drain": "Drenaje",
        "reset_breaker": "Reset del breaker",
    }[action]
    suffix = "solicitado al worker" if pending else "aplicado"
    return f"{verb} de {target} {suffix}."


def _audit_failure(
    actor: str,
    action: str,
    target: str,
    revision: int,
    detail: str,
) -> None:
    record_remote_control_audit(
        actor=actor,
        action=f"opportunity_{action}",
        status="failed",
        target_type="opportunity_control",
        target_id=target,
        operation_id=f"opportunity-control-{revision}",
        detail=sanitize_text(detail)[:240],
    )


def _requested_by(value: str | None) -> str:
    normalized = (value or "").strip()
    if not normalized:
        return "admin_api"
    if len(normalized) > 64 or re.fullmatch(r"[A-Za-z0-9:_-]+", normalized) is None:
        return "admin_api"
    return normalized


def _query_int(query: dict[str, list[str]], name: str, *, default: int) -> int:
    try:
        return min(max(int(query.get(name, [str(default)])[0]), 1), 100)
    except (TypeError, ValueError):
        return default


def _query_status(query: dict[str, list[str]]) -> str | None:
    value = str(query.get("status", [""])[0]).strip().lower()
    if not value:
        return None
    if value not in {"running", "draining", "closed", "aborted"}:
        return "invalid"
    return value


def _timestamp(value: Any) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value) if value is not None else None


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
