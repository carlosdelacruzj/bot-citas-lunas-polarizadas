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

    def health(self):
        return True, "ok"

    def status(self):
        return {"phase": "monitoring_observer"}


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


if __name__ == "__main__":
    unittest.main()
