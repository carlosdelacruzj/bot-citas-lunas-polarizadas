from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

SERVICE_USER_AGENT = "CitasLunasPolarizadas-Service/1.0"


class HostedRegistrationError(RuntimeError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True)
class ServiceCredentials:
    key_id: str
    secret: bytes

    @classmethod
    def from_environment(cls, prefix: str) -> ServiceCredentials:
        key_id = os.getenv(f"{prefix}_KEY_ID", "").strip()
        encoded_secret = os.getenv(f"{prefix}_SECRET", "").strip()
        if not key_id or not encoded_secret:
            raise HostedRegistrationError(
                503,
                "configuration_error",
                f"{prefix}_KEY_ID and {prefix}_SECRET are required.",
            )
        try:
            secret = _base64url_decode(encoded_secret)
        except ValueError as exc:
            raise HostedRegistrationError(
                503,
                "configuration_error",
                f"{prefix}_SECRET is not valid Base64 URL-safe data.",
            ) from exc
        if len(secret) < 32:
            raise HostedRegistrationError(
                503,
                "configuration_error",
                f"{prefix}_SECRET must contain at least 32 bytes.",
            )
        return cls(key_id=key_id, secret=secret)


class HostedRegistrationClient:
    def __init__(
        self,
        credentials: ServiceCredentials,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.credentials = credentials
        self.base_url = (
            base_url
            or os.getenv(
                "HOSTED_REGISTRATION_BASE_URL",
                "https://registro.citaspolarizadasperu.com/api/v1/",
            )
        ).rstrip("/") + "/"
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise HostedRegistrationError(
                503,
                "configuration_error",
                "HOSTED_REGISTRATION_BASE_URL must use HTTPS or local loopback.",
            )
        self.timeout_seconds = timeout_seconds

    @classmethod
    def operator(cls) -> HostedRegistrationClient:
        return cls(ServiceCredentials.from_environment("HOSTED_REGISTRATION_OPERATOR"))

    @classmethod
    def connector(cls) -> HostedRegistrationClient:
        return cls(ServiceCredentials.from_environment("HOSTED_REGISTRATION_CONNECTOR"))

    def create_invitation(self, contact_ref: str, phone_hint: str) -> dict[str, Any]:
        return self.request(
            "POST",
            "operator/invitations",
            {
                "contact_ref": contact_ref,
                "phone_hint": phone_hint,
                "source": "whatsapp_direct",
            },
            idempotency_key=str(uuid4()),
        )

    def list_invitations(self) -> list[dict[str, Any]]:
        response = self.request("GET", "operator/invitations")
        return list(response.get("items") or response.get("invitations") or [])

    def revoke_invitation(self, invitation_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"operator/invitations/{quote(invitation_id, safe='')}/revoke",
            {},
        )

    def reissue_invitation(self, invitation_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"operator/invitations/{quote(invitation_id, safe='')}/reissue",
            {},
            idempotency_key=str(uuid4()),
        )

    def claim(self, connector_id: str) -> list[dict[str, Any]]:
        response = self.request(
            "POST",
            "connector/requests/claim",
            {"connector_id": connector_id, "limit": 1, "lease_seconds": 300},
        )
        return list(response.get("items") or [])

    def renew(self, request_id: str, lease_token: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"connector/requests/{quote(request_id, safe='')}/lease/renew",
            {"lease_token": lease_token},
        )

    def complete(
        self,
        request_id: str,
        lease_token: str,
        *,
        outcome: str,
        public_result: str,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"connector/requests/{quote(request_id, safe='')}/complete",
            {
                "lease_token": lease_token,
                "outcome": outcome,
                "public_result": public_result,
            },
            idempotency_key=str(uuid4()),
        )

    def release(
        self,
        request_id: str,
        lease_token: str,
        *,
        category: str,
        retry_after_seconds: int,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"connector/requests/{quote(request_id, safe='')}/release",
            {
                "lease_token": lease_token,
                "reason": category,
                "retry_after_seconds": retry_after_seconds,
            },
        )

    def request(
        self,
        method: str,
        relative_path: str,
        payload: dict[str, Any] | None = None,
        *,
        query: list[tuple[str, str]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            if payload is not None
            else ""
        )
        body_bytes = body.encode("utf-8")
        sorted_query = sorted(query or [])
        query_string = urlencode(sorted_query)
        path = "/api/v1/" + relative_path.lstrip("/")
        timestamp = str(int(time.time()))
        nonce = _base64url_encode(secrets.token_bytes(16))
        body_hash = _base64url_encode(hashlib.sha256(body_bytes).digest())
        canonical = "\n".join(
            [
                "v1",
                self.credentials.key_id,
                timestamp,
                nonce,
                method.upper(),
                path,
                query_string,
                body_hash,
            ]
        )
        signature = _base64url_encode(
            hmac.new(
                self.credentials.secret,
                canonical.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        )
        headers = {
            "Accept": "application/json",
            "User-Agent": SERVICE_USER_AGENT,
            "X-Service-Key-Id": self.credentials.key_id,
            "X-Service-Timestamp": timestamp,
            "X-Service-Nonce": nonce,
            "X-Service-Signature": signature,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        url = urljoin(self.base_url, relative_path.lstrip("/"))
        if query_string:
            url = f"{url}?{query_string}"
        request = Request(
            url,
            data=body_bytes if payload is not None else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            raw = exc.read()
            try:
                error = json.loads(raw).get("error", {})
            except (UnicodeDecodeError, json.JSONDecodeError):
                error = {}
            raise HostedRegistrationError(
                exc.code,
                str(error.get("code") or "hosted_request_failed"),
                str(error.get("message") or "El servicio alojado rechazó la solicitud."),
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise HostedRegistrationError(
                503,
                "hosted_unavailable",
                "No se pudo contactar el servicio alojado.",
            ) from exc


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    if not value:
        raise ValueError("Empty Base64 URL-safe value.")
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)
