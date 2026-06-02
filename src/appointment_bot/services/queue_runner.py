from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import asdict, replace

from appointment_bot.config import Settings, load_settings
from appointment_bot.main import RunReport, run_with_report, settings_for_client
from appointment_bot.services.database import (
    Client,
    list_active_clients,
    mark_client_done,
    update_client_state,
)
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.runtime import single_run_lock

logger = logging.getLogger(__name__)


def run_queue() -> int:
    return run_queue_with_report().exit_code


def run_queue_with_report() -> RunReport:
    settings = load_settings(require_login=False)
    setup_logging(settings)

    checked_clients = 0
    confirmed_reservations = 0
    results: list[dict[str, str]] = []

    with single_run_lock(settings):
        clients = list_active_clients(settings)
        if not clients:
            logger.info("Client queue skipped: no active clients")
            return RunReport(
                status="skipped",
                message="No hay clientes activos para revisar.",
                exit_code=0,
                details={"checked_clients": "0", "confirmed_reservations": "0"},
            )

        logger.info("Starting client queue with %s active clients", len(clients))
        for client in clients:
            if confirmed_reservations >= settings.queue_max_reservations_per_run:
                logger.info(
                    "Queue reservation limit reached: %s",
                    settings.queue_max_reservations_per_run,
                )
                break

            checked_clients += 1
            report = _run_client(settings, client)
            results.append(
                {
                    "client_id": client.client_id,
                    "status": report.status,
                    "message": report.message,
                }
            )
            _update_state_from_report(settings, client, report)

            if _is_programmed(report):
                mark_client_done(client.client_id, settings=settings)
                logger.info("Client marked as done: %s", client.client_id)

            if report.status == "registered":
                confirmed_reservations += 1
                mark_client_done(client.client_id, settings=settings)
                logger.info("Reservation confirmed for client: %s", client.client_id)
                if confirmed_reservations < settings.queue_max_reservations_per_run:
                    _delay_between_clients(settings)
                continue

            if report.status == "reservation_unconfirmed":
                update_client_state(
                    client.client_id,
                    status=report.status,
                    message=report.message,
                    exit_code=report.exit_code,
                    backoff_seconds=settings.error_backoff_seconds,
                    settings=settings,
                )
                _delay_between_clients(settings)
                continue

            if report.status == "available" and not settings.auto_reserve:
                logger.info(
                    "Stopping queue after availability alert with AUTO_RESERVE=false: %s",
                    client.client_id,
                )
                break

    return RunReport(
        status="completed",
        message=(
            f"Cola finalizada. Reservas confirmadas: {confirmed_reservations}. "
            f"Clientes revisados: {checked_clients}."
        ),
        exit_code=0,
        details={
            "checked_clients": str(checked_clients),
            "confirmed_reservations": str(confirmed_reservations),
            "results": str(results),
        },
    )


def _run_client(settings: Settings, client: Client) -> RunReport:
    logger.info("Starting queued appointment check for client %s", client.client_id)
    client_settings = settings_for_client(
        settings,
        username=client.username,
        password=client.password,
    )
    client_settings = _settings_with_client_state_dir(client_settings, client)
    return run_with_report(
        client_settings,
        client_id=client.client_id,
        use_lock=False,
        apply_jitter=False,
        cleanup_files=False,
        record_history=True,
    )


def _settings_with_client_state_dir(settings: Settings, client: Client) -> Settings:
    safe_client_id = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in client.client_id
    )
    return replace(settings, state_dir=settings.state_dir / "clients" / safe_client_id)


def _update_state_from_report(settings: Settings, client: Client, report: RunReport) -> None:
    update_client_state(
        client.client_id,
        status=report.status,
        message=report.message,
        exit_code=report.exit_code,
        settings=settings,
    )


def _is_programmed(report: RunReport) -> bool:
    details = report.details or {}
    status = str(details.get("estado") or "").strip().lower()
    return report.status == "completed" and status == "programado"


def _delay_between_clients(settings: Settings) -> None:
    if settings.queue_delay_max_seconds <= 0:
        return

    delay = random.randint(
        settings.queue_delay_min_seconds,
        settings.queue_delay_max_seconds,
    )
    if delay <= 0:
        return

    logger.info("Waiting %s seconds before the next queued client", delay)
    time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="appointment-bot",
        description="Ejecuta la cola multi-cliente del appointment bot.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON report after the queue run.",
    )
    args = parser.parse_args()

    report = run_queue_with_report()
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False))
    else:
        print(asdict(report))
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
