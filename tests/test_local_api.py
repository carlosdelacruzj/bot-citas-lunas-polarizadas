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

from appointment_bot.services.database import add_client
from appointment_bot.services.local_api import create_local_api_server
from tests.helpers import make_settings


class _Controller:
    is_running = True
    is_starting_or_running = True
    pause_called = False
    resume_called = False

    def health(self):
        return True, "ok"

    def status(self):
        return {"phase": "monitoring_observer"}

    def pause(self):
        self.pause_called = True
        return {"phase": "paused", "paused": True}

    def resume(self):
        self.resume_called = True
        return {"phase": "starting", "paused": False}


@contextmanager
def _running_server(extra_environment: dict[str, str] | None = None):
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
        server = create_local_api_server(worker_controller=_Controller())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


class LocalApiTests(unittest.TestCase):
    def test_health_is_public_but_status_requires_token(self) -> None:
        with _running_server() as base_url:
            with urlopen(f"{base_url}/health", timeout=3) as response:
                self.assertEqual(response.status, 200)
                health = json.loads(response.read())
            self.assertEqual(health["status"], "ok")
            self.assertTrue(health["worker_running"])

            with self.assertRaises(HTTPError) as context:
                urlopen(f"{base_url}/status", timeout=3)
            self.assertEqual(context.exception.code, 401)

            request = Request(
                f"{base_url}/status",
                headers={"Authorization": "Bearer secret"},
            )
            with urlopen(request, timeout=3) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["phase"], "monitoring_observer")

    def test_api_clients_requires_token_and_does_not_expose_password(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            add_client("client-1", "Test", "12345678", "secret", 1, settings=settings)

            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                with self.assertRaises(HTTPError) as context:
                    urlopen(f"{base_url}/api/v1/clients", timeout=3)
                self.assertEqual(context.exception.code, 401)

                request = Request(
                    f"{base_url}/api/v1/clients",
                    headers={"Authorization": "Bearer secret"},
                )
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read())

            self.assertEqual(payload["clients"][0]["client_id"], "client-1")
            self.assertEqual(payload["clients"][0]["username_masked"], "12***8")
            self.assertNotIn("password", payload["clients"][0])

    def test_client_create_update_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            with _running_server({"APPOINTMENT_DATABASE_URL": settings.database_url}) as base_url:
                create_payload = {
                    "client_id": "client-2",
                    "name": "Client Two",
                    "username": "87654321",
                    "password": "secret",
                    "priority": 5,
                }
                response = _json_request(
                    f"{base_url}/api/v1/clients",
                    method="POST",
                    token="secret",
                    payload=create_payload,
                )
                self.assertEqual(response["status"], "created")

                update = _json_request(
                    f"{base_url}/api/v1/clients/client-2",
                    method="PATCH",
                    token="secret",
                    payload={"name": "Updated", "priority": 7},
                )
                self.assertEqual(update["status"], "ok")

                for action in ("pause", "activate", "done"):
                    result = _json_request(
                        f"{base_url}/api/v1/clients/client-2/{action}",
                        method="POST",
                        token="secret",
                    )
                    self.assertEqual(result["status"], "ok")

                request = Request(
                    f"{base_url}/api/v1/clients",
                    headers={"Authorization": "Bearer secret"},
                )
                with urlopen(request, timeout=3) as response:
                    clients = json.loads(response.read())["clients"]

            self.assertEqual(clients[0]["client_id"], "client-2")
            self.assertEqual(clients[0]["priority"], 7)
            self.assertTrue(clients[0]["done"])

    def test_runs_endpoints_and_legacy_worker_actions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            from appointment_bot.services.database import create_run_record
            from appointment_bot.services.database_models import RunRecord

            create_run_record(
                settings,
                RunRecord(
                    run_id="run-api-1",
                    client_id=None,
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
                pause = _json_request(f"{base_url}/pause", method="POST", token="secret")
                resume = _json_request(f"{base_url}/resume", method="POST", token="secret")

            self.assertEqual(len(runs["runs"]), 1)
            self.assertEqual(detail["screenshot_paths"], ["evidence.png"])
            self.assertEqual(detail["details"], {"sede": "LIMA"})
            self.assertTrue(pause["paused"])
            self.assertFalse(resume["paused"])


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
