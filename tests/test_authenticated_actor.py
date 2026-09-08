from __future__ import annotations

import hashlib
import hmac
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from appointment_bot.services.api.http import authenticated_actor, require_authorized


class AuthenticatedActorTests(unittest.TestCase):
    def test_bearer_actor_is_derived_from_credential_and_ignores_claimed_actor(self) -> None:
        handler = SimpleNamespace(
            headers={
                "Authorization": "Bearer secret",
                "X-Appointment-Actor": "forged-owner",
            },
            server=SimpleNamespace(dashboard_session_token=""),
            client_address=("127.0.0.1", 1234),
        )

        with patch.dict(os.environ, {"APPOINTMENT_BOT_API_TOKEN": "secret"}):
            self.assertTrue(require_authorized(handler, strict=True))

        fingerprint = hashlib.sha256(b"secret").hexdigest()[:12]
        self.assertEqual(authenticated_actor(handler), f"api:sha256:{fingerprint}")
        self.assertNotIn("forged-owner", authenticated_actor(handler))

    def test_dashboard_actor_is_derived_from_trusted_local_session(self) -> None:
        handler = SimpleNamespace(
            headers={"Cookie": "appointment_bot_dashboard=session-secret"},
            server=SimpleNamespace(dashboard_session_token="session-secret"),
            client_address=("127.0.0.1", 1234),
        )

        self.assertTrue(require_authorized(handler, strict=True))
        self.assertEqual(authenticated_actor(handler), "dashboard:local")

    def test_signed_telegram_actor_is_accepted_after_bearer_authentication(self) -> None:
        actor = "telegram:123456789abc"
        signature = hmac.new(b"secret", actor.encode("utf-8"), hashlib.sha256).hexdigest()
        handler = SimpleNamespace(
            headers={
                "Authorization": "Bearer secret",
                "X-Appointment-Actor": actor,
                "X-Appointment-Actor-Signature": signature,
            },
            server=SimpleNamespace(dashboard_session_token=""),
            client_address=("127.0.0.1", 1234),
        )

        with patch.dict(os.environ, {"APPOINTMENT_BOT_API_TOKEN": "secret"}):
            self.assertTrue(require_authorized(handler, strict=True))

        self.assertEqual(authenticated_actor(handler), actor)


if __name__ == "__main__":
    unittest.main()
