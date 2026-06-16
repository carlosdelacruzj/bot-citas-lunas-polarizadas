from __future__ import annotations

import json
import os
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from appointment_bot.services.local_api import create_local_api_server


class _Controller:
    is_running = True
    is_starting_or_running = True

    def health(self):
        return True, "ok"

    def status(self):
        return {"phase": "monitoring_observer"}


@contextmanager
def _running_server():
    environment = patch.dict(
        os.environ,
        {
            "APPOINTMENT_BOT_API_HOST": "127.0.0.1",
            "APPOINTMENT_BOT_API_PORT": "0",
            "APPOINTMENT_BOT_API_TOKEN": "secret",
        },
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


if __name__ == "__main__":
    unittest.main()
