from __future__ import annotations

import logging
import os
import threading
from dataclasses import replace
from pathlib import Path

from appointment_bot.config import load_settings
from appointment_bot.reports.status import generate_daily_report_image
from appointment_bot.services.captcha_shadow import configure_captcha_shadow
from appointment_bot.services.local_api import create_local_api_server
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.whatsapp_automation import WhatsAppAutomationDispatcher
from appointment_bot.worker.continuous_worker import (
    DAILY_CUTOFF_REASON,
    LEASE_UNAVAILABLE_REASON,
    ContinuousWorker,
)
from appointment_bot.worker.queue_runtime import run_rapid_queue_with_settings

logger = logging.getLogger(__name__)
RESTART_EXIT_CODE = 75
LEASE_UNAVAILABLE_EXIT_CODE = 76


def run_host(external_stop_event: threading.Event | None = None) -> int:
    _set_working_directory()
    settings = load_settings(require_login=True)
    setup_logging(settings)
    if not settings.continuous_worker_enabled:
        raise RuntimeError("CONTINUOUS_WORKER_ENABLED must be true to run the continuous worker.")

    stop_event = external_stop_event or threading.Event()
    restart_event = threading.Event()
    worker = ContinuousWorker(settings)
    server = create_local_api_server(
        worker_controller=worker,
        restart_callback=restart_event.set,
    )
    captcha_shadow_dispatcher = configure_captcha_shadow(settings)
    captcha_shadow_dispatcher.start()
    whatsapp_dispatcher = WhatsAppAutomationDispatcher(settings)
    worker_failure: list[BaseException] = []
    health_failure = False
    daily_cutoff_report_generated = False

    def run_worker() -> None:
        try:
            worker.run_forever()
        except BaseException as exc:
            worker_failure.append(exc)
            logger.exception("Continuous worker stopped unexpectedly")
        finally:
            stop_event.set()

    worker_thread = threading.Thread(
        target=run_worker,
        name="appointment-bot-worker",
        daemon=True,
    )
    server_thread = threading.Thread(
        target=server.serve_forever,
        name="appointment-bot-local-api",
        daemon=True,
    )
    host, port = server.server_address[:2]
    logger.info("Continuous worker API listening on http://%s:%s", host, port)
    worker_thread.start()
    if not worker.wait_until_ready(timeout=10):
        stop_event.set()
        worker_thread.join(timeout=5)
        captcha_shadow_dispatcher.stop()
        whatsapp_dispatcher.stop()
        if worker_failure:
            raise RuntimeError("Continuous worker failed during startup.") from worker_failure[0]
        raise RuntimeError("Continuous worker did not become ready before timeout.")
    if worker.shutdown_reason == LEASE_UNAVAILABLE_REASON:
        logger.warning("Another host owns the worker lease; retrying later.")
        server.server_close()
        worker_thread.join(timeout=5)
        captcha_shadow_dispatcher.stop()
        whatsapp_dispatcher.stop()
        return LEASE_UNAVAILABLE_EXIT_CODE
    if not worker.is_running and worker.shutdown_reason != DAILY_CUTOFF_REASON:
        captcha_shadow_dispatcher.stop()
        whatsapp_dispatcher.stop()
        if worker_failure:
            raise RuntimeError("Continuous worker failed during startup.") from worker_failure[0]
        raise RuntimeError("Continuous worker stopped during startup.")
    whatsapp_dispatcher.start()
    server_thread.start()
    try:
        while not stop_event.wait(1):
            if restart_event.is_set():
                logger.info("Controlled worker restart requested")
                break
            worker_status = worker.status()
            if worker_status.get("phase") == DAILY_CUTOFF_REASON:
                if not daily_cutoff_report_generated:
                    try:
                        if settings.final_ready_review_enabled:
                            _run_final_ready_review(settings)
                        else:
                            logger.info("Final ready-order review skipped by configuration.")
                        path = generate_daily_report_image()
                        logger.info("Final daily status report generated: %s", path)
                    except Exception:
                        logger.exception("Could not generate the final daily status report")
                    daily_cutoff_report_generated = True
            else:
                daily_cutoff_report_generated = False
            healthy, reason = worker.health()
            if not healthy:
                logger.error("Continuous worker health check failed: %s", reason)
                health_failure = True
                stop_event.set()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        worker.stop()
        worker_thread.join(
            timeout=(
                settings.reservation_timeout_seconds
                + settings.login_timeout_seconds
                + settings.postback_timeout_seconds
                + settings.read_timeout_seconds
                + 30
            )
        )
        if worker.shutdown_reason == DAILY_CUTOFF_REASON:
            try:
                if not daily_cutoff_report_generated and settings.final_ready_review_enabled:
                    _run_final_ready_review(settings)
                elif not settings.final_ready_review_enabled:
                    logger.info("Final ready-order review skipped by configuration.")
                path = generate_daily_report_image()
                logger.info("Final daily status report generated: %s", path)
            except Exception:
                logger.exception("Could not generate the final daily status report")
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=10)
        captcha_shadow_dispatcher.stop()
        whatsapp_dispatcher.stop()
        if worker_thread.is_alive():
            raise RuntimeError("Continuous worker did not stop within operation timeouts.")
    if worker_failure:
        raise RuntimeError("Continuous worker stopped unexpectedly.") from worker_failure[0]
    if health_failure or restart_event.is_set():
        return RESTART_EXIT_CODE
    if worker.shutdown_reason not in {None, DAILY_CUTOFF_REASON}:
        return RESTART_EXIT_CODE
    return 0


def _set_working_directory() -> None:
    configured = os.getenv("APPOINTMENT_BOT_WORKDIR", "").strip()
    workdir = Path(configured) if configured else Path(__file__).resolve().parents[3]
    if not workdir.exists():
        raise FileNotFoundError(f"Appointment bot working directory does not exist: {workdir}")
    os.chdir(workdir)


def _run_final_ready_review(settings) -> None:
    review_settings = replace(
        settings,
        auto_reserve=False,
        monitor_window_seconds=0,
        monitor_max_attempts=1,
        queue_delay_min_seconds=0,
        queue_delay_max_seconds=0,
        telegram_notify_unavailable=False,
    )
    report = run_rapid_queue_with_settings(
        review_settings,
        stop_on_available_without_reserve=False,
    )
    logger.info("Final ready-order review completed: %s", report.message)


def main() -> None:
    raise SystemExit(run_host())


if __name__ == "__main__":
    main()
