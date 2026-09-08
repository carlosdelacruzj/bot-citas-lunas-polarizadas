from __future__ import annotations

from http import HTTPStatus

from appointment_bot.manual_session.session import blocking_manual_sessions
from appointment_bot.services.api.http import error_payload
from appointment_bot.services.api.routing import ApiRequest
from appointment_bot.services.api.worker_routes import (
    enqueue_restart_with_safe_backoff_release_payload,
    enqueue_worker_command_payload,
    health_payload,
    list_worker_commands_payload,
    record_worker_control_audit,
    worker_payload,
)


def get_health(request: ApiRequest) -> None:
    handler = request.transport
    controller = getattr(handler.server, "worker_controller", None)
    healthy, payload = health_payload(controller)
    handler._send_json(HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE, payload)
    return


def get_worker(request: ApiRequest) -> None:
    handler = request.transport
    handler._send_json(
        HTTPStatus.OK,
        worker_payload(getattr(handler.server, "worker_controller", None)),
    )
    return


def get_list_worker_commands(request: ApiRequest) -> None:
    handler = request.transport
    query = request.query
    handler._send_json(HTTPStatus.OK, list_worker_commands_payload(query))
    return


def post_worker_restart(request: ApiRequest) -> None:
    handler = request.transport
    manual_sessions = blocking_manual_sessions()
    if manual_sessions:
        handler._send_json(
            HTTPStatus.CONFLICT,
            error_payload(
                "manual_session_active",
                "No se puede reiniciar mientras exista una sesion manual abierta o cerrando.",
                blocking_session_count=len(manual_sessions),
                blocking_session_statuses=sorted(
                    {str(item.get("status") or "") for item in manual_sessions}
                ),
            ),
        )
        return
    request_payload = handler._read_json()
    release_safe_backoffs = request_payload.get("release_safe_backoffs", False)
    if not isinstance(release_safe_backoffs, bool):
        handler._send_json(
            HTTPStatus.BAD_REQUEST,
            error_payload(
                "bad_request",
                "release_safe_backoffs must be a boolean.",
            ),
        )
        return
    if release_safe_backoffs:
        status, payload = enqueue_restart_with_safe_backoff_release_payload(
            requested_by=handler._authenticated_actor(),
        )
        handler._send_json(status, payload)
        return
    controller = getattr(handler.server, "worker_controller", None)
    restart_callback = getattr(handler.server, "restart_callback", None)
    if controller is None or restart_callback is None:
        status, payload = enqueue_worker_command_payload(
            "restart",
            requested_by=handler._authenticated_actor(),
        )
        handler._send_json(status, payload)
        return
    controller.prepare_restart()
    controller_settings = getattr(controller, "runtime_settings", None)
    if controller_settings is not None:
        record_worker_control_audit(
            command="restart",
            requested_by=handler._authenticated_actor(),
            status="accepted",
            detail="control_path=embedded_api",
            runtime_settings=controller_settings,
        )
    handler._send_json(
        HTTPStatus.ACCEPTED,
        {"status": "restarting", "message": "Controlled restart requested."},
    )
    restart_callback()
    return


def post_worker_control(request: ApiRequest) -> None:
    handler = request.transport
    path = request.path
    controller = getattr(handler.server, "worker_controller", None)
    if controller is None:
        command = "pause" if path.endswith("/pause") else "resume"
        status, payload = enqueue_worker_command_payload(
            command,
            requested_by=handler._authenticated_actor(),
        )
        handler._send_json(status, payload)
        return
    command = "pause" if path.endswith("/pause") else "resume"
    payload = controller.pause() if command == "pause" else controller.resume()
    controller_settings = getattr(controller, "runtime_settings", None)
    if controller_settings is not None:
        record_worker_control_audit(
            command=command,
            requested_by=handler._authenticated_actor(),
            status="applied",
            detail="control_path=embedded_api",
            runtime_settings=controller_settings,
        )
    handler._send_json(HTTPStatus.OK, payload)
