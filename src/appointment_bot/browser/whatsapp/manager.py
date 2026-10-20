from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

from playwright.sync_api import BrowserContext, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from appointment_bot.browser.whatsapp.common import (
    COMMAND_TIMEOUT_SECONDS,
    DAILY_SUMMARY_IMAGE_BATCH_SIZE,
    _result,
    logger,
)
from appointment_bot.browser.whatsapp.drafts import _prepare_draft
from appointment_bot.browser.whatsapp.evidence import _save_context_failure_screenshot
from appointment_bot.browser.whatsapp.progress import reset_delivery_progress, set_delivery_progress
from appointment_bot.browser.whatsapp.session import (
    _close_context,
    _ensure_context,
    _is_closed_target_error,
)


@dataclass
class _DraftCommand:
    draft: dict[str, object]
    response: queue.Queue[dict[str, object]]
    expires_at: float


def _command_timeout_seconds(draft: dict[str, object]) -> int:
    if draft.get("document_items"):
        return min(510, 120 + 60 * len(draft["document_items"]))
    if draft.get("album_items"):
        return 240
    if draft.get("action") != "daily_slot_summary":
        return COMMAND_TIMEOUT_SECONDS
    image_count = len(draft.get("attachment_paths") or [])
    batch_count = (
        image_count + DAILY_SUMMARY_IMAGE_BATCH_SIZE - 1
    ) // DAILY_SUMMARY_IMAGE_BATCH_SIZE
    # Leave a minute before the dispatcher's ten-minute lease expires.
    return min(510, COMMAND_TIMEOUT_SECONDS + 75 * batch_count)


class WhatsAppWebDraftManager:
    def __init__(self) -> None:
        self._commands: queue.Queue[_DraftCommand] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._busy = threading.Event()

    @property
    def busy(self) -> bool:
        return self._busy.is_set() or not self._commands.empty()

    def prepare(self, draft: dict[str, object]) -> dict[str, object]:
        self._ensure_started()
        response: queue.Queue[dict[str, object]] = queue.Queue(maxsize=1)
        progress = draft.get("delivery_progress")
        if progress is not None:
            progress.dispatched = True
        started = time.monotonic()
        timeout = _command_timeout_seconds(draft)
        self._commands.put(_DraftCommand(
            draft=draft, response=response,
            expires_at=started + timeout + min(60, 570 - timeout),
        ))
        try:
            return response.get(timeout=timeout)
        except queue.Empty:
            if progress is not None:
                progress.cancel()
                progress.notify_delayed()
            # Stop new components, but allow the in-flight confirmation to finish.
            try:
                result = response.get(timeout=min(60, 570 - timeout))
                result["confirmation_delayed"] = True
                return result
            except queue.Empty:
                pass
            return _result(
                "web_unavailable",
                "confirmation_deadline_exceeded:"
                f"{progress.attempt_id if progress is not None else 'manual'} "
                "El envio de WhatsApp alcanzo el limite de tiempo. "
                "Revisa los componentes confirmados y pendientes antes de recuperar el envio; "
                "no se reintentara automaticamente.",
                delivery_components=dict(progress.states) if progress is not None else None,
            )
        finally:
            logger.info(
                "WhatsApp command wait: action=%s elapsed=%.3fs budget=%ss",
                draft.get("action", "package"), time.monotonic() - started, timeout,
            )

    @staticmethod
    def _complete_progress(command, result):
        progress = command.draft.get("delivery_progress")
        if progress is not None:
            try:
                progress.complete()
            except Exception:
                logger.exception("Could not persist WhatsApp command completion")
                return _result(
                    "web_unavailable",
                    "No se pudo registrar el cierre del intento. "
                    "Revisa el chat; no se reintentara automaticamente.",
                )
        return result

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
                self._busy.set()
                if time.monotonic() >= command.expires_at:
                    result = _result("web_unavailable", "El comando vencio antes de iniciarse.")
                    command.response.put(self._complete_progress(command, result))
                    self._busy.clear()
                    continue
                token = set_delivery_progress(command.draft.get("delivery_progress"))
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
                        logger.warning("WhatsApp Web window closed; not repeating the draft")
                        context = _close_context(context)
                        context_headless = None
                        result = _result(
                            "web_unavailable",
                            "WhatsApp Web se cerro durante la preparacion. "
                            "Revisa el chat antes de preparar o recuperar el mensaje; "
                            "no se repetira automaticamente.",
                            message_id=str(command.draft.get("message_id") or ""),
                            delivery_phase="send_state_unknown",
                            evidence_path=failure_evidence,
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
                result = self._complete_progress(command, result)
                reset_delivery_progress(token)
                command.response.put(result)
                self._busy.clear()


_MANAGER = WhatsAppWebDraftManager()
