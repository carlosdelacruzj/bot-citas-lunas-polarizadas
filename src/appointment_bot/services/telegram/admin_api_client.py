from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.transport import (
    MAX_TELEGRAM_RESPONSE_BYTES,
    _read_json_response,
)


class AdminApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def record_remote_control_audit(
        self,
        *,
        actor: str,
        action: str,
        status: str,
        target_type: str | None = None,
        target_id: str | None = None,
        operation_id: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/remote-control-audit",
            payload={
                "action": action,
                "status": status,
                "target_type": target_type,
                "target_id": target_id,
                "operation_id": operation_id,
                "detail": detail,
            },
            actor=actor,
        )

    def get_worker(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/worker")

    def get_health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def get_service_orders(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/v1/service-orders")
        orders = payload.get("service_orders", [])
        if not isinstance(orders, list):
            raise TelegramControlError("Admin API returned an invalid service order list.")
        return [item for item in orders if isinstance(item, dict)]

    def get_operator_inbox(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/operator-inbox")

    def get_appointment_reminders(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/appointment-reminders")

    def get_service_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/service-orders/{quote(order_id, safe='')}")

    def mark_payment_paid(
        self,
        order_id: str,
        *,
        amount_paid: str,
        amount_agreed: str,
        expected_amount_paid: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/payment/paid",
            payload={
                "amount_paid": amount_paid,
                "amount_agreed": amount_agreed,
                "expected_payment_status": "pending",
                "expected_amount_agreed": amount_agreed,
                "expected_amount_paid": expected_amount_paid,
            },
            actor=actor,
        )

    def record_partial_payment(
        self,
        order_id: str,
        *,
        amount_paid: str,
        amount_agreed: str,
        expected_amount_paid: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/payment/partial",
            payload={
                "amount_paid": amount_paid,
                "amount_agreed": amount_agreed,
                "expected_payment_status": "pending",
                "expected_amount_agreed": amount_agreed,
                "expected_amount_paid": expected_amount_paid,
            },
            actor=actor,
        )

    def search_service_orders(self, query: str) -> list[dict[str, Any]]:
        payload = self._request("POST", "/api/v1/service-orders/search", payload={"query": query})
        orders = payload.get("service_orders", [])
        if not isinstance(orders, list):
            raise TelegramControlError("Admin API returned an invalid search result.")
        return [item for item in orders if isinstance(item, dict)]

    def get_service_order_credentials(self, order_id: str) -> dict[str, Any]:
        return self._request(
            "GET", f"/api/v1/service-orders/{quote(order_id, safe='')}/credentials"
        )

    def update_service_order_credentials(
        self,
        order_id: str,
        *,
        document_number: str,
        document_type: str,
        password: str,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/credentials",
            payload={
                "document_number": document_number,
                "document_type": document_type,
                "password": password,
            },
            actor=actor,
        )

    def create_service_order(self, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/service-orders",
            payload=values,
            actor=actor,
            request_timeout=15,
        )

    def get_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._request("GET", f"/api/v1/runs?limit={limit}")
        runs = payload.get("runs", [])
        if not isinstance(runs, list):
            raise TelegramControlError("Admin API returned an invalid run list.")
        return [item for item in runs if isinstance(item, dict)]

    def get_captcha_summary(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/captcha-shadow/summary")

    def get_pending_captcha_events(
        self,
        *,
        page: int = 1,
        targeted: bool = True,
    ) -> dict[str, Any]:
        query = urlencode(
            {
                "page": page,
                "page_size": 48,
                "review_status": "pending",
                "review_scope": "targeted" if targeted else "all",
                "sort": "review_priority" if targeted else "oldest",
            }
        )
        return self._request("GET", f"/api/v1/captcha-shadow/events?{query}")

    def get_captcha_image(self, event_id: str) -> tuple[bytes, str]:
        return self._request_bytes(
            "GET",
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/image",
        )

    def save_captcha_human_label(
        self,
        event_id: str,
        answer: str,
        image_sha256: str,
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/captcha-shadow/events/{quote(event_id, safe='')}/human-label",
            payload={
                "answer": answer,
                "expected_image_sha256": image_sha256,
                "expected_unlabeled": True,
                "note": "Validated from Telegram review queue.",
            },
            actor=actor,
        )

    def update_order_priority(
        self,
        order_id: str,
        priority: int,
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/priority",
            payload={"priority": priority},
            actor=actor,
        )

    def update_order_rules(
        self,
        order_id: str,
        rules: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/restrictions",
            payload=rules,
            actor=actor,
        )

    def revalidate_service_order(self, order_id: str, *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/validate",
            payload={},
            actor=actor,
        )

    def resolve_service_order_programs(
        self,
        order_id: str,
        resolution: dict[str, Any],
        *,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/service-orders/{quote(order_id, safe='')}/program-resolution",
            payload=resolution,
            actor=actor,
        )

    def enqueue_worker_command(self, command: str, *, actor: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/worker/{command}",
            payload={},
            actor=actor,
        )

    def get_worker_command(self, command_id: str) -> dict[str, Any] | None:
        payload = self._request("GET", "/api/v1/worker/commands?limit=100")
        commands = payload.get("commands", [])
        if not isinstance(commands, list):
            raise TelegramControlError("Admin API returned an invalid command list.")
        return next(
            (
                item
                for item in commands
                if isinstance(item, dict) and item.get("command_id") == command_id
            ),
            None,
        )

    def get_opportunity_control(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/runtime-controls/opportunity")

    def update_opportunity_control(
        self,
        *,
        action: str,
        target: str,
        reason: str,
        expected_revision: int,
        actor: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/runtime-controls/opportunity",
            payload={
                "action": action,
                "target": target,
                "reason": reason,
                "expected_revision": expected_revision,
            },
            actor=actor,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        actor: str | None = None,
        request_timeout: int = 5,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        if actor:
            headers["X-Appointment-Actor"] = actor
            headers["X-Appointment-Actor-Signature"] = hmac.new(
                self.token.encode("utf-8"),
                actor.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=request_timeout) as response:
                return _read_json_response(response)
        except HTTPError as exc:
            raise TelegramControlError(
                f"Admin API rejected the action with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError("Admin API is not reachable.") from exc

    def _request_bytes(self, method: str, path: str) -> tuple[bytes, str]:
        request = Request(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self.token}"},
            method=method,
        )
        try:
            with urlopen(request, timeout=5) as response:
                content_type = response.headers.get_content_type()
                return response.read(MAX_TELEGRAM_RESPONSE_BYTES + 1), content_type
        except HTTPError as exc:
            raise TelegramControlError(
                f"Admin API rejected the action with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise TelegramControlError("Admin API is not reachable.") from exc
