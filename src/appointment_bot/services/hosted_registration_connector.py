from __future__ import annotations

import base64
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from appointment_bot.config import Settings, load_settings
from appointment_bot.db.hosted_registrations import (
    complete_local_registration,
    record_claim,
)
from appointment_bot.db.orders import create_service_order
from appointment_bot.services.hosted_registration_client import (
    HostedRegistrationClient,
    HostedRegistrationError,
)
from appointment_bot.services.order_preflight import validate_order_preflight

logger = logging.getLogger(__name__)


class HostedRegistrationConnector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings(require_login=False)
        self.enabled = os.getenv("HOSTED_REGISTRATION_CONNECTOR_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.mode = os.getenv("HOSTED_REGISTRATION_CONNECTOR_MODE", "production").strip().lower()
        self.connector_id = os.getenv(
            "HOSTED_REGISTRATION_CONNECTOR_ID",
            "primary-windows-pc",
        ).strip()
        self.poll_seconds = max(
            5.0,
            float(os.getenv("HOSTED_REGISTRATION_CONNECTOR_POLL_SECONDS", "20")),
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("Hosted registration connector is disabled.")
            return
        if self.mode not in {"production", "controlled"}:
            raise ValueError(
                "HOSTED_REGISTRATION_CONNECTOR_MODE must be production or controlled."
            )
        HostedRegistrationClient.connector()
        _load_private_key()
        self._thread = threading.Thread(
            target=self._run,
            name="hosted-registration-connector",
            daemon=True,
        )
        self._thread.start()
        logger.info("Hosted registration connector started in %s mode.", self.mode)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        client = HostedRegistrationClient.connector()
        while not self._stop_event.is_set():
            try:
                items = client.claim(self.connector_id)
                if items:
                    self._process(client, items[0])
            except HostedRegistrationError as exc:
                logger.warning(
                    "Hosted registration connector unavailable: category=%s status=%s",
                    exc.code,
                    exc.status,
                )
            except Exception:
                logger.exception("Hosted registration connector failed without exposing payload.")
            self._stop_event.wait(self.poll_seconds)

    def _process(
        self,
        client: HostedRegistrationClient,
        item: dict[str, Any],
    ) -> None:
        request_id = str(item["request_id"])
        invitation_id = str(item["invitation_id"])
        contact_ref = str(item["contact_ref"])
        lease_token = str(item["lease_token"])
        try:
            local_contact = record_claim(contact_ref, request_id, settings=self.settings)
        except ValueError:
            client.complete(
                request_id,
                lease_token,
                outcome="rejected",
                public_result="rejected",
            )
            return
        durable_state = str(local_contact["state"])
        if durable_state in {"accepted", "awaiting_restrictions"}:
            client.complete(
                request_id,
                lease_token,
                outcome="accepted",
                public_result="accepted",
            )
            return
        if durable_state == "credentials_invalid":
            client.complete(
                request_id,
                lease_token,
                outcome="credentials_invalid",
                public_result="credentials_invalid",
            )
            return
        if durable_state == "rejected":
            client.complete(
                request_id,
                lease_token,
                outcome="rejected",
                public_result="rejected",
            )
            return
        try:
            payload = decrypt_registration_payload(
                dict(item["envelope"]),
                invitation_id=invitation_id,
            )
        except (KeyError, TypeError, ValueError):
            complete_local_registration(
                contact_ref,
                request_id=request_id,
                state="rejected",
                error_category="invalid_envelope",
                settings=self.settings,
            )
            client.complete(
                request_id,
                lease_token,
                outcome="rejected",
                public_result="rejected",
            )
            return

        if self.mode == "controlled":
            complete_local_registration(
                contact_ref,
                request_id=request_id,
                state=(
                    "awaiting_restrictions"
                    if payload["availability_mode"] == "date_restrictions"
                    else "accepted"
                ),
                availability_mode=str(payload["availability_mode"]),
                settings=self.settings,
            )
            client.complete(
                request_id,
                lease_token,
                outcome="accepted",
                public_result="accepted",
            )
            return

        result = create_service_order(
            document_number=str(payload["username"]),
            document_type=str(payload["document_type"]),
            password=str(payload["password"]),
            contact_whatsapp=str(local_contact["whatsapp_phone"]),
            contact_name=str(local_contact["display_name"]),
            contact_source="whatsapp_direct",
            require_preflight=True,
            settings=self.settings,
        )
        availability_mode = str(payload["availability_mode"])
        if availability_mode == "date_restrictions":
            complete_local_registration(
                contact_ref,
                request_id=request_id,
                state="awaiting_restrictions",
                availability_mode=availability_mode,
                order_id=result.order_id,
                settings=self.settings,
            )
            client.complete(
                request_id,
                lease_token,
                outcome="accepted",
                public_result="accepted",
            )
            return

        heartbeat = _LeaseHeartbeat(client, request_id, lease_token)
        heartbeat.start()
        try:
            validation = validate_order_preflight(result.order_id, settings=self.settings)
        finally:
            heartbeat.stop()
        if validation.get("status") == "validated":
            complete_local_registration(
                contact_ref,
                request_id=request_id,
                state="accepted",
                availability_mode=availability_mode,
                order_id=result.order_id,
                settings=self.settings,
            )
            client.complete(
                request_id,
                lease_token,
                outcome="accepted",
                public_result="accepted",
            )
            return
        if validation.get("error_type") == "invalid_credentials":
            complete_local_registration(
                contact_ref,
                request_id=request_id,
                state="credentials_invalid",
                availability_mode=availability_mode,
                order_id=result.order_id,
                error_category="credentials_invalid",
                settings=self.settings,
            )
            client.complete(
                request_id,
                lease_token,
                outcome="credentials_invalid",
                public_result="credentials_invalid",
            )
            return
        complete_local_registration(
            contact_ref,
            request_id=request_id,
            state="retry_wait",
            availability_mode=availability_mode,
            order_id=result.order_id,
            error_category="preflight_retryable",
            settings=self.settings,
        )
        client.release(
            request_id,
            lease_token,
            category="local_validation_unavailable",
            retry_after_seconds=300,
        )


class _LeaseHeartbeat:
    def __init__(
        self,
        client: HostedRegistrationClient,
        request_id: str,
        lease_token: str,
    ) -> None:
        self.client = client
        self.request_id = request_id
        self.lease_token = lease_token
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.wait(60):
            try:
                self.client.renew(self.request_id, self.lease_token)
            except HostedRegistrationError:
                logger.warning(
                    "Hosted registration lease renewal failed: request=%s",
                    self.request_id,
                )


def decrypt_registration_payload(
    envelope: dict[str, Any],
    *,
    invitation_id: str,
) -> dict[str, Any]:
    expected_keys = {
        "envelope_version",
        "schema_version",
        "key_id",
        "key_wrap_algorithm",
        "content_algorithm",
        "encrypted_key",
        "iv",
        "ciphertext",
        "aad",
    }
    if set(envelope) != expected_keys:
        raise ValueError("Invalid envelope fields.")
    key_id = str(envelope["key_id"])
    if (
        envelope["envelope_version"] != 1
        or envelope["schema_version"] != 1
        or envelope["key_wrap_algorithm"] != "RSA-OAEP-256"
        or envelope["content_algorithm"] != "AES-256-GCM"
        or key_id != os.getenv("HOSTED_REGISTRATION_PRIVATE_KEY_ID", "").strip()
    ):
        raise ValueError("Unsupported envelope.")
    aad_value = {
        "envelope_version": 1,
        "schema_version": 1,
        "key_id": key_id,
        "invitation_id": invitation_id,
    }
    aad = json.dumps(aad_value, separators=(",", ":")).encode("utf-8")
    if not _constant_time_equal(_base64url_decode(str(envelope["aad"])), aad):
        raise ValueError("Invalid envelope AAD.")
    private_key = _load_private_key()
    content_key = private_key.decrypt(
        _base64url_decode(str(envelope["encrypted_key"])),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    plaintext = AESGCM(content_key).decrypt(
        _base64url_decode(str(envelope["iv"])),
        _base64url_decode(str(envelope["ciphertext"])),
        aad,
    )
    payload = json.loads(plaintext)
    _validate_payload(payload)
    return payload


def _validate_payload(payload: Any) -> None:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "document_type",
        "username",
        "password",
        "availability_mode",
        "consent",
    }:
        raise ValueError("Invalid registration payload.")
    consent = payload.get("consent")
    if (
        payload.get("schema_version") != 1
        or payload.get("document_type") not in {"dni", "foreign_resident_card"}
        or not isinstance(payload.get("username"), str)
        or not 1 <= len(payload["username"]) <= 32
        or not isinstance(payload.get("password"), str)
        or not 4 <= len(payload["password"]) <= 128
        or payload.get("availability_mode") not in {"any_date", "date_restrictions"}
        or not isinstance(consent, dict)
        or set(consent) != {"version", "accepted"}
        or consent.get("version") != "privacy-v1"
        or consent.get("accepted") is not True
    ):
        raise ValueError("Invalid registration payload.")


def _load_private_key():
    path_value = os.getenv("HOSTED_REGISTRATION_PRIVATE_KEY_PATH", "").strip()
    if not path_value:
        raise ValueError("HOSTED_REGISTRATION_PRIVATE_KEY_PATH is required.")
    key_path = Path(path_value).expanduser().resolve()
    if not key_path.is_file():
        raise ValueError("The hosted registration private key file does not exist.")
    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 3072:
        raise ValueError("The hosted registration private key must be RSA with at least 3072 bits.")
    return private_key


def _base64url_decode(value: str) -> bytes:
    padding_value = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding_value)


def _constant_time_equal(left: bytes, right: bytes) -> bool:
    import hmac

    return hmac.compare_digest(left, right)
