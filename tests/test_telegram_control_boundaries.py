from __future__ import annotations

import inspect
from collections import defaultdict, deque
from dataclasses import replace
from io import BytesIO
from threading import Lock
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest

from appointment_bot.services.telegram.access import TelegramRateLimiter, _mutation_user_authorized
from appointment_bot.services.telegram.bot_api import TelegramBotApi
from appointment_bot.services.telegram.callbacks import _process_callback_query
from appointment_bot.services.telegram.constants import (
    MUTATION_RATE_LIMIT,
    RATE_LIMIT_WINDOW_SECONDS,
    RETRY_DELAY_SECONDS,
)
from appointment_bot.services.telegram.errors import TelegramControlError
from appointment_bot.services.telegram.models import (
    CaptchaReviewConversation,
    NewClientConversation,
    PendingClientCreation,
    PendingOrderChange,
    PendingWorkerConfirmation,
    RulesConversation,
    TelegramControlConfig,
)
from appointment_bot.services.telegram.runtime import run_control
from appointment_bot.services.telegram.state import (
    _load_next_offset,
    _remove_expired_captcha_state,
    _remove_expired_client_state,
    _remove_expired_confirmations,
    _remove_expired_order_state,
    _store_next_offset,
)
from appointment_bot.services.telegram.transport import (
    MAX_TELEGRAM_RESPONSE_BYTES,
    _read_json_response,
)


def _owner(symbol):
    return inspect.getmodule(symbol)


def _config(tmp_path):
    return TelegramControlConfig(
        bot_token="test-only",
        authorized_chat_ids=frozenset({"42"}),
        admin_api_url="http://example.invalid",
        admin_api_token="test-only",
        offset_path=tmp_path / "offset.json",
        poll_timeout_seconds=30,
        worker_monitor_enabled=False,
    )


def test_polling_advances_offset_only_after_completed_dispatch(tmp_path):
    config = _config(tmp_path)
    telegram = Mock()
    telegram.get_me.return_value = {"result": {"id": 1}}
    telegram.get_webhook_info.return_value = {"result": {}}
    telegram.get_updates.return_value = [{"update_id": 10}, {"update_id": 11}]
    stop = Mock()
    stop.is_set.side_effect = [False, True]
    runtime = _owner(run_control)
    with (
        patch.object(runtime, "load_settings"),
        patch.object(runtime, "setup_logging"),
        patch.object(runtime, "load_control_config", return_value=config),
        patch.object(runtime, "TelegramBotApi", return_value=telegram),
        patch.object(runtime, "AdminApiClient"),
        patch.object(runtime, "Event", return_value=stop),
        patch.object(runtime, "_install_signal_handlers"),
        patch.object(runtime, "ThreadPoolExecutor"),
        patch.object(runtime, "_record_audit_safe"),
        patch.object(
            runtime,
            "_process_update",
            side_effect=[
                None,
                TelegramControlError("dispatch failed"),
            ],
        ),
    ):
        assert run_control() == 0
    assert _load_next_offset(config.offset_path) == 11
    assert not config.offset_path.with_suffix(".json.tmp").exists()
    telegram.get_updates.assert_called_once_with(offset=None, timeout_seconds=30)
    stop.wait.assert_called_once_with(RETRY_DELAY_SECONDS)


def test_invalid_offset_is_ignored_and_valid_offset_is_atomic(tmp_path):
    path = tmp_path / "offset.json"
    assert _load_next_offset(path) is None
    path.write_text("{invalid", encoding="utf-8")
    assert _load_next_offset(path) is None
    _store_next_offset(path, 123)
    assert _load_next_offset(path) == 123
    assert not path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize(
    "chat,sender,users,allowed",
    [
        ({"id": 42, "type": "private"}, {"id": 42}, frozenset(), True),
        ({"id": 42, "type": "group"}, {"id": 42}, frozenset(), False),
        ({"id": 42, "type": "private"}, {"id": 7}, frozenset(), False),
        ({"id": 42, "type": "private"}, {"id": 7}, frozenset({"7"}), True),
        ({"id": 42, "type": "private"}, None, frozenset(), False),
    ],
)
def test_mutations_require_private_authorized_sender(tmp_path, chat, sender, users, allowed):
    config = replace(_config(tmp_path), authorized_user_ids=users)
    assert _mutation_user_authorized(config, chat, sender) is allowed


def test_rate_limits_are_separate_and_expire_at_window_boundary():
    limiter = TelegramRateLimiter()
    for _ in range(MUTATION_RATE_LIMIT):
        assert limiter.allow("42", mutation=True, now=100)
    assert not limiter.allow("42", mutation=True, now=100)
    assert limiter.allow("42", mutation=False, now=100)
    assert limiter.allow("43", mutation=True, now=100)
    assert limiter.allow("42", mutation=True, now=100 + RATE_LIMIT_WINDOW_SECONDS)


@pytest.mark.parametrize("action", ["yes", "no"])
def test_worker_confirmation_is_consumed_once(tmp_path, action):
    telegram, admin_api, executor = Mock(), Mock(), Mock()
    pending = {"one": PendingWorkerConfirmation("one", "42", "pause", 200)}
    query = {
        "id": "callback",
        "data": f"wc:one:{action}",
        "from": {"id": 42},
        "message": {"message_id": 1, "chat": {"id": 42, "type": "private"}},
    }
    owner = _owner(_process_callback_query)
    with patch.object(owner, "_record_audit_safe"), patch("time.monotonic", return_value=100):
        for _ in range(2):
            _process_callback_query(
                query,
                _config(tmp_path),
                telegram,
                admin_api,
                pending,
                {},
                {},
                {},
                {},
                {},
                {},
                defaultdict(deque),
                TelegramRateLimiter(),
                Lock(),
                executor,
            )
    assert pending == {}
    assert executor.submit.call_count == (1 if action == "yes" else 0)
    telegram.answer_callback_query.assert_called_with("callback", "La confirmacion ya vencio.")
    assert admin_api.mock_calls == []


def test_expiration_removes_only_expired_conversations_and_pending_changes():
    telegram = Mock()
    pending = {
        "expired": PendingWorkerConfirmation("expired", "42", "pause", 100),
        "live": PendingWorkerConfirmation("live", "43", "pause", 101),
    }
    clients = {"42": NewClientConversation("42", "session", {"password": "fake"}, 0, 100)}
    creations = {"expired": PendingClientCreation("expired", "42", {}, 100)}
    captchas = {"42": CaptchaReviewConversation("42", "session", 100)}
    changes = {"expired": PendingOrderChange("expired", "42", "rules", "test", {}, {}, 100)}
    rules = {"42": RulesConversation("42", "test", {}, {}, 0, 100)}
    with patch("time.monotonic", return_value=100):
        _remove_expired_confirmations(pending, Lock())
        _remove_expired_order_state(changes, rules, Lock())
        _remove_expired_client_state(clients, creations, telegram, Lock())
        _remove_expired_captcha_state(captchas, telegram)
    assert set(pending) == {"live"}
    assert not any((clients, creations, captchas, changes, rules))
    assert telegram.send_message.call_count == 3


def test_bot_polling_contract_and_invalid_response():
    bot = TelegramBotApi("test-only")
    with patch.object(
        bot, "_request", return_value={"result": [{"update_id": 3}, None]}
    ) as request:
        assert bot.get_updates(offset=3, timeout_seconds=20) == [{"update_id": 3}]
        assert request.call_args.args[0] == "getUpdates"
        assert request.call_args.args[1]["offset"] == "3"
        assert request.call_args.kwargs == {"request_timeout": 30}
    with patch.object(bot, "_request", return_value={"result": {}}):
        with pytest.raises(TelegramControlError, match="invalid updates list"):
            bot.get_updates(offset=None, timeout_seconds=20)


def test_bot_http_failure_does_not_retry_or_expose_token():
    bot = TelegramBotApi("test-only-secret")
    failure = HTTPError(bot.base_url, 429, "limited", {}, None)
    with patch.object(_owner(TelegramBotApi), "urlopen", side_effect=failure) as request:
        with pytest.raises(TelegramControlError) as error:
            bot.answer_callback_query("callback", "received")
    request.assert_called_once()
    assert str(error.value) == "Telegram answerCallbackQuery failed with HTTP 429."
    assert "test-only-secret" not in str(error.value)


def test_bot_rejects_invalid_and_oversized_json():
    for body in (b"[]", b"not-json", b"x" * (MAX_TELEGRAM_RESPONSE_BYTES + 1)):
        with pytest.raises(TelegramControlError):
            _read_json_response(BytesIO(body))
