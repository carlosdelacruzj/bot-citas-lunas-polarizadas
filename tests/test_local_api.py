from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from appointment_bot.db.orders import create_service_order
from appointment_bot.services.local_api import create_local_api_server
from tests.helpers import make_settings


class _Controller:
    is_running = True
    pause_called = False
    resume_called = False
    restart_called = False

    def health(self):
        return True, "ok"

    def status(self):
        return {
            "phase": "monitoring_observer",
            "owner_token": "internal-owner",
            "lease_expires_at": "2026-07-09T18:00:00",
        }

    def pause(self):
        self.pause_called = True
        return {"phase": "paused", "paused": True}

    def resume(self):
        self.resume_called = True
        return {"phase": "starting", "paused": False}

    def prepare_restart(self):
        self.restart_called = True
        return {"phase": "restarting", "paused": False}


@contextmanager
def _running_server(
    extra_environment: dict[str, str] | None = None,
    *,
    restart_callback=None,
):
    environment_values = {
        "APPOINTMENT_BOT_API_HOST": "127.0.0.1",
        "APPOINTMENT_BOT_API_PORT": "0",
        "APPOINTMENT_BOT_API_TOKEN": "secret",
    }
    if extra_environment:
        environment_values.update(extra_environment)
    environment = patch.dict(
        os.environ,
        environment_values,
    )
    with environment:
        server = create_local_api_server(
            worker_controller=_Controller(),
            restart_callback=restart_callback,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class LocalApiTests(unittest.TestCase):
    def test_health_is_public_but_worker_status_requires_token(self) -> None:
        with _running_server() as base_url:
            with urlopen(f"{base_url}/health", timeout=3) as response:
                self.assertEqual(response.status, 200)
                health = json.loads(response.read())
            self.assertEqual(health["status"], "ok")
            self.assertTrue(health["worker_running"])

            with self.assertRaises(HTTPError) as context:
                urlopen(f"{base_url}/api/v1/worker", timeout=3)
            self.assertEqual(context.exception.code, 401)

            request = Request(
                f"{base_url}/api/v1/worker",
                headers={"Authorization": "Bearer secret"},
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["phase"], "monitoring_observer")
            self.assertNotIn("owner_token", payload)
            self.assertNotIn("lease_expires_at", payload)

    def test_api_service_orders_requires_token_and_does_not_expose_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            create_service_order(
                document_number="12345678",
                password="secret",
                applicant_name="Test",
                priority=1,
                settings=settings,
            )

            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                with self.assertRaises(HTTPError) as context:
                    urlopen(f"{base_url}/api/v1/service-orders", timeout=3)
                self.assertEqual(context.exception.code, 401)

                request = Request(
                    f"{base_url}/api/v1/service-orders",
                    headers={"Authorization": "Bearer secret"},
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read())

                detail_request = Request(
                    f"{base_url}/api/v1/service-orders/order-12345678",
                    headers={"Authorization": "Bearer secret"},
                )
                with urlopen(detail_request, timeout=3) as response:
                    detail = json.loads(response.read())

            self.assertEqual(payload["service_orders"][0]["order_id"], "order-12345678")
            self.assertEqual(payload["service_orders"][0]["document_number_masked"], "12***8")
            self.assertNotIn("document_number", payload["service_orders"][0])
            self.assertNotIn("contact_whatsapp", payload["service_orders"][0])
            self.assertNotIn("password", payload["service_orders"][0])

            self.assertEqual(detail["document_number"], "12345678")
            self.assertIn("contact_whatsapp", detail)
            self.assertNotIn("password", detail)

    def test_service_order_create_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                create_payload = {
                    "document_number": "87654321",
                    "password": "secret",
                    "contact_name": "  Contacto   de prueba  ",
                    "contact_source": "WhatsApp",
                    "contact_whatsapp": "+51 999-111-222",
                    "applicant_name": "Client Two",
                    "priority": 5,
                    "minimum_reservation_hour": 11,
                    "minimum_reservation_date": "2026-08-01",
                    "allowed_weekdays": [1, 6],
                }
                response = _json_request(
                    f"{base_url}/api/v1/service-orders",
                    method="POST",
                    token="secret",
                    payload=create_payload,
                )
                self.assertEqual(response["status"], "created")
                order_id = response["order_id"]

                invalid_payload = {**create_payload, "document_number": "11112222"}
                invalid_payload["contact_source"] = "instagram"
                with self.assertRaises(HTTPError) as context:
                    _json_request(
                        f"{base_url}/api/v1/service-orders",
                        method="POST",
                        token="secret",
                        payload=invalid_payload,
                    )
                invalid_error = json.loads(context.exception.read())
                self.assertEqual(context.exception.code, 400)
                self.assertIn("contact_source", invalid_error["field_errors"])

                for action in ("pause", "activate", "done"):
                    result = _json_request(
                        f"{base_url}/api/v1/service-orders/{order_id}/{action}",
                        method="POST",
                        token="secret",
                    )
                    self.assertEqual(result["status"], "ok")

                request = Request(
                    f"{base_url}/api/v1/service-orders",
                    headers={"Authorization": "Bearer secret"},
                )
                with urlopen(request, timeout=3) as response:
                    orders = json.loads(response.read())["service_orders"]
                detail = _json_request(
                    f"{base_url}/api/v1/service-orders/{order_id}",
                    token="secret",
                )

            self.assertEqual(orders[0]["order_id"], "order-87654321")
            self.assertEqual(orders[0]["priority"], 5)
            self.assertEqual(orders[0]["status"], "archived")
            self.assertEqual(detail["contact_name"], "Contacto de prueba")
            self.assertEqual(detail["contact_source"], "whatsapp")
            self.assertEqual(detail["contact_whatsapp"], "+51999111222")
            self.assertEqual(detail["minimum_reservation_hour"], 11)
            self.assertEqual(detail["minimum_reservation_date"], "2026-08-01")
            self.assertEqual(detail["allowed_weekdays"], [1, 6])

    def test_service_order_close_action_publishes_closure_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            result = create_service_order(
                document_number="87654321",
                password="secret",
                applicant_name="Client Two",
                priority=5,
                settings=settings,
            )
            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                close_response = _json_request(
                    f"{base_url}/api/v1/service-orders/{result.order_id}/close",
                    method="POST",
                    token="secret",
                    payload={
                        "closure_reason": "client_withdrew",
                        "closure_note": "Cliente cancelo",
                    },
                )
                self.assertEqual(close_response["status"], "ok")
                orders = _json_request(
                    f"{base_url}/api/v1/service-orders",
                    token="secret",
                )["service_orders"]

            self.assertEqual(orders[0]["status"], "archived")
            self.assertFalse(orders[0]["charge_required"])
            self.assertEqual(orders[0]["closure_reason"], "client_withdrew")
            self.assertEqual(orders[0]["closure_note"], "Cliente cancelo")
            self.assertIsNotNone(orders[0]["closed_at"])
            self.assertNotIn("password", orders[0])

    def test_runs_endpoints_and_worker_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            from appointment_bot.db.runs import create_run_record
            from appointment_bot.services.database_models import RunRecord

            create_run_record(
                settings,
                RunRecord(
                    run_id="run-api-1",
                    order_id=None,
                    status="unavailable",
                    message="No slots",
                    exit_code=0,
                    started_at="2026-06-16T01:00:00",
                    finished_at="2026-06-16T01:00:01",
                    duration_seconds=1.0,
                    reservation_attempted=False,
                    reservation_confirmed=False,
                    details={"dni": "12345678", "sede": "LIMA"},
                    screenshot_path="C:/tmp/evidence.png",
                ),
                ["C:/tmp/evidence.png"],
            )
            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                runs = _json_request(f"{base_url}/api/v1/runs?limit=1", token="secret")
                detail = _json_request(f"{base_url}/api/v1/runs/run-api-1", token="secret")
                detail_with_details = _json_request(
                    f"{base_url}/api/v1/runs/run-api-1?include_details=1",
                    token="secret",
                )
                pause = _json_request(
                    f"{base_url}/api/v1/worker/pause", method="POST", token="secret"
                )
                resume = _json_request(
                    f"{base_url}/api/v1/worker/resume", method="POST", token="secret"
                )

            self.assertEqual(len(runs["runs"]), 1)
            self.assertIn("order_id", runs["runs"][0])
            self.assertEqual(detail["screenshot_paths"], ["evidence.png"])
            self.assertIn("order_id", detail)
            self.assertNotIn("details", detail)
            self.assertEqual(detail_with_details["details"], {"sede": "LIMA"})
            self.assertTrue(pause["paused"])
            self.assertFalse(resume["paused"])

    def test_restart_requires_token_and_invokes_host_callback(self) -> None:
        restarted = threading.Event()
        with _running_server(restart_callback=restarted.set) as base_url:
            with self.assertRaises(HTTPError) as context:
                urlopen(
                    Request(f"{base_url}/api/v1/worker/restart", method="POST"),
                    timeout=3,
                )
            self.assertEqual(context.exception.code, 401)

            response = _json_request(
                f"{base_url}/api/v1/worker/restart",
                method="POST",
                token="secret",
            )

        self.assertEqual(response["status"], "restarting")
        self.assertTrue(restarted.is_set())


def _json_request(
    url: str,
    *,
    method: str = "GET",
    token: str,
    payload: dict | None = None,
) -> dict:
    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=3) as response:
        return json.loads(response.read())


if __name__ == "__main__":
    unittest.main()
