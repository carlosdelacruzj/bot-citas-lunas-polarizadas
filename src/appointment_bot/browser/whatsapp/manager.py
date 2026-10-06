from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from playwright.sync_api import BrowserContext, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.whatsapp.common import COMMAND_TIMEOUT_SECONDS, _result, logger
from appointment_bot.browser.whatsapp.drafts import _prepare_draft
from appointment_bot.browser.whatsapp.evidence import _save_context_failure_screenshot
from appointment_bot.browser.whatsapp.session import (
    _close_context,
    _ensure_context,
    _is_closed_target_error,
)


@dataclass
class _DraftCommand:
    draft: dict[str, object]
    response: queue.Queue[dict[str, object]]


class WhatsAppWebDraftManager:
    def __init__(self) -> None:
        self._commands: queue.Queue[_DraftCommand] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def prepare(self, draft: dict[str, object]) -> dict[str, object]:
        self._ensure_started()
        response: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        self._commands.put(_DraftCommand(draft=draft, response=response))
        try:
            return response.get(timeout=COMMAND_TIMEOUT_SECONDS)
        except queue.Empty:
            return _result(
                "web_unavailable",
                "WhatsApp Web no respondio a tiempo. "
                "Revisa la ventana abierta y vuelve a intentar.",
            )

    def _ensure_started(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                name="whatsapp-web-draft-manager",
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        context: BrowserContext | None = None
        context_headless: bool | None = None
        with sync_playwright() as playwright:
            while True:
                command = self._commands.get()
                requested_headless = bool(command.draft.get("headless"))
                try:
                    if context is not None and context_headless != requested_headless:
                        context = _close_context(context)
                        context_headless = None
                    context = _ensure_context(
                        playwright,
                        context,
                        headless=requested_headless,
                    )
                    context_headless = requested_headless
                    result = _prepare_draft(context, command.draft)
                except PlaywrightError as exc:
                    failure_evidence = _save_context_failure_screenshot(
                        context,
                        command.draft,
                    )
                    if _is_closed_target_error(exc):
                        if command.draft.get("disable_closed_target_retry"):
                            logger.warning(
                                "WhatsApp Web window closed while preparing draft; not retrying"
                            )
                            context = _close_context(context)
                            context_headless = None
                            result = _result(
                                "web_unavailable",
                                "WhatsApp Web se cerro durante la preparacion. "
                                "Si ya enviaste el mensaje, confirma el envio manualmente; "
                                "si no, vuelve a preparar el borrador.",
                                message_id=str(command.draft.get("message_id") or ""),
                                delivery_phase="send_state_unknown",
                                evidence_path=failure_evidence,
                            )
                            command.response.put(result)
                            continue
                        logger.warning(
                            "WhatsApp Web window closed while preparing draft; reopening once"
                        )
                        context = _close_context(context)
                        context_headless = None
                        try:
                            context = _ensure_context(
                                playwright,
                                context,
                                headless=requested_headless,
                            )
                            context_headless = requested_headless
                            result = _prepare_draft(context, command.draft)
                        except PlaywrightError as retry_exc:
                            retry_evidence = _save_context_failure_screenshot(
                                context,
                                command.draft,
                            )
                            logger.exception(
                                "Could not prepare WhatsApp Web draft after reopening"
                            )
                            context = _close_context(context)
                            context_headless = None
                            result = _result(
                                "web_unavailable",
                                f"No se pudo preparar WhatsApp Web: {retry_exc}",
                                delivery_phase="send_state_unknown",
                                evidence_path=retry_evidence,
                            )
                    else:
                        logger.exception("Could not prepare WhatsApp Web draft")
                        context = _close_context(context)
                        context_headless = None
                        result = _result(
                            "web_unavailable",
                            f"No se pudo preparar WhatsApp Web: {exc}",
                            delivery_phase="send_state_unknown",
                            evidence_path=failure_evidence,
                        )
                except Exception as exc:
                    failure_evidence = _save_context_failure_screenshot(
                        context,
                        command.draft,
                    )
                    logger.exception("Could not prepare WhatsApp Web draft")
                    if command.draft.get("close_on_error"):
                        context = _close_context(context)
                        context_headless = None
                    result = _result(
                        "web_unavailable",
                        f"No se pudo preparar WhatsApp Web: {exc}",
                        delivery_phase="send_state_unknown",
                        evidence_path=failure_evidence,
                    )
                command.response.put(result)


_MANAGER = WhatsAppWebDraftManager()
