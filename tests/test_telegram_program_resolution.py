from __future__ import annotations

from threading import Lock
from unittest.mock import Mock

from appointment_bot.services import telegram_control, telegram_program_resolution


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, dict | None]] = []

    def send_message(self, chat_id: str, text: str, *, reply_markup=None):
        self.messages.append((chat_id, text, reply_markup))
        return {}


class FakeAdminApi:
    def __init__(self, order: dict | None = None) -> None:
        self.order = order or {}
        self.resolutions: list[tuple[str, dict, str]] = []

    def get_service_order(self, order_id: str) -> dict:
        return self.order

    def resolve_service_order_programs(
        self, order_id: str, resolution: dict, *, actor: str
    ) -> dict:
        self.resolutions.append((order_id, resolution, actor))
        return {"status": "applied", "communication_preview": "Texto para revisar"}


def _multiple_pending_order(**overrides) -> dict:
    order = {
        "order_id": "order-1",
        "service_type": "reservation",
        "service_package": "standard",
        "preflight_status": "failed",
        "preflight_details": {
            "error_type": "multiple_pending_resolution_required",
            "listing_signature": "signed-listing",
            "pending_programs": [
                {"status": "PENDIENTE", "expediente": "EXP-1", "placa": "AAA111"},
                {"status": "CANCELADO", "expediente": "EXP-X", "placa": "XXX000"},
                {"status": "pendiente", "expediente": "EXP-2", "placa": "BBB222"},
            ],
        },
    }
    order.update(overrides)
    return order


def _listing_token(order: dict | None = None) -> str:
    current = order or _multiple_pending_order()
    return telegram_program_resolution._listing_token(current["preflight_details"])


def test_program_panel_only_exposes_pending_rows() -> None:
    text, markup = telegram_program_resolution.build_panel(
        "order-1", _multiple_pending_order()
    )
    callbacks = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
    assert "EXP-1" in text
    assert "EXP-2" in text
    assert "EXP-X" not in text
    token = _listing_token()
    assert f"pr:order-1:one0-{token}" in callbacks
    assert f"pr:order-1:one1-{token}" in callbacks
    assert f"pr:order-1:all-{token}" in callbacks
    assert f"pr:order-1:pause-{token}" in callbacks


def test_custom_program_resolution_is_sent_to_dashboard() -> None:
    text, markup = telegram_program_resolution.build_panel(
        "order-1", _multiple_pending_order(service_type="custom")
    )
    callbacks = [button["callback_data"] for row in markup["inline_keyboard"] for button in row]
    assert "Dashboard" in text
    assert not any(callback.endswith(":all") for callback in callbacks)
    assert not any(":one" in callback for callback in callbacks)
    assert f"pr:order-1:pause-{_listing_token()}" in callbacks


def test_all_resolution_requires_communication_decision_before_confirmation() -> None:
    telegram = FakeTelegram()
    pending: dict[str, telegram_control.PendingOrderChange] = {}

    telegram_program_resolution.request_resolution(
        "chat-1",
        "order-1",
        f"all-{_listing_token()}",
        telegram,
        FakeAdminApi(_multiple_pending_order()),
        pending,
        Lock(),
        telegram_control.PendingOrderChange,
        confirmation_ttl_seconds=telegram_control.CONFIRMATION_TTL_SECONDS,
    )

    change = next(iter(pending.values()))
    assert change.updated == {
        "listing_signature": "signed-listing",
        "resolution": "all",
        "confirm_same_commercial_terms": True,
    }
    assert "Telegram no enviara WhatsApp" in telegram.messages[-1][1]
    callbacks = telegram.messages[-1][2]["inline_keyboard"]
    assert callbacks[0][0]["callback_data"].endswith(":informed")
    assert callbacks[1][0]["callback_data"].endswith(":keep")


def test_one_resolution_uses_canonical_exact_program_fields() -> None:
    telegram = FakeTelegram()
    pending: dict[str, telegram_control.PendingOrderChange] = {}

    telegram_program_resolution.request_resolution(
        "chat-1",
        "order-1",
        f"one0-{_listing_token()}",
        telegram,
        FakeAdminApi(_multiple_pending_order()),
        pending,
        Lock(),
        telegram_control.PendingOrderChange,
        confirmation_ttl_seconds=telegram_control.CONFIRMATION_TTL_SECONDS,
    )

    change = next(iter(pending.values()))
    assert change.updated == {
        "listing_signature": "signed-listing",
        "resolution": "one",
        "program_expediente": "EXP-1",
        "program_plate": "AAA111",
    }


def test_pause_requires_explicit_communication_decision() -> None:
    draft = telegram_program_resolution.prepare_resolution(
        _multiple_pending_order(), f"pause-{_listing_token()}"
    )

    assert draft.requires_communication_decision is True
    assert draft.payload == {
        "listing_signature": "signed-listing",
        "resolution": "pause",
    }


def test_stale_panel_action_cannot_select_a_new_listing_by_index() -> None:
    changed = _multiple_pending_order()
    changed["preflight_details"]["listing_signature"] = "new-signed-listing"

    try:
        telegram_program_resolution.prepare_resolution(
            changed, f"one0-{_listing_token()}"
        )
    except telegram_program_resolution.ProgramResolutionError as exc:
        assert "listado cambio" in str(exc)
    else:
        raise AssertionError("A stale panel action must not select a current row by index.")


def test_execute_resolution_displays_preview_without_sending() -> None:
    telegram = FakeTelegram()
    admin_api = FakeAdminApi()
    change = telegram_control.PendingOrderChange(
        operation_id="abcdef123456",
        chat_id="chat-1",
        action="program_resolution",
        order_id="order-1",
        original={"description": "resolver uno"},
        updated={
            "resolution": "one",
            "listing_signature": "signed-listing",
            "program_expediente": "EXP-1",
            "communication_decision": "keep_without_send",
        },
        expires_at=999999999.0,
    )
    audit = Mock()
    telegram_program_resolution.execute_resolution(
        change,
        telegram,
        admin_api,
        actor="telegram:chat-1",
        audit=audit,
        display_text=telegram_control._display_text,
    )

    assert len(admin_api.resolutions) == 1
    assert "VISTA PREVIA - NO ENVIADA" in telegram.messages[-1][1]
    assert "WhatsApp: no enviado" in telegram.messages[-1][1]


def test_program_resolution_client_uses_actor_header_boundary() -> None:
    client = telegram_control.AdminApiClient("http://127.0.0.1:8766", "token")
    client._request = Mock(return_value={"status": "applied"})
    payload = {"resolution": "pause", "listing_signature": "signature"}

    result = client.resolve_service_order_programs(
        "order/with slash", payload, actor="telegram:123"
    )

    assert result == {"status": "applied"}
    client._request.assert_called_once_with(
        "POST",
        "/api/v1/service-orders/order%2Fwith%20slash/program-resolution",
        payload=payload,
        actor="telegram:123",
    )


def test_stale_resolution_requests_refresh_and_does_not_claim_success() -> None:
    telegram = FakeTelegram()
    admin_api = FakeAdminApi()
    admin_api.resolve_service_order_programs = Mock(
        side_effect=telegram_control.TelegramControlError(
            "Admin API rejected the action with HTTP 409."
        )
    )
    change = telegram_control.PendingOrderChange(
        operation_id="abcdef123456",
        chat_id="chat-1",
        action="program_resolution",
        order_id="order-1",
        original={"description": "resolver uno"},
        updated={
            "resolution": "one",
            "listing_signature": "old-signature",
            "program_expediente": "EXP-1",
            "communication_decision": "keep_without_send",
        },
        expires_at=999999999.0,
    )
    audit = Mock()
    telegram_program_resolution.execute_resolution(
        change,
        telegram,
        admin_api,
        actor="telegram:chat-1",
        audit=audit,
        display_text=telegram_control._display_text,
    )

    _, text, markup = telegram.messages[-1]
    assert "listado cambio" in text
    assert "No aplique nada" in text
    assert markup["inline_keyboard"][0][0]["callback_data"] == "pr:order-1:show"
