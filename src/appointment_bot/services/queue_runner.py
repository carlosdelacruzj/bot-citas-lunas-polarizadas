from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import asdict, replace

from appointment_bot.config import Settings, load_settings
from appointment_bot.main import RunReport, run_with_report, settings_for_client
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.database import (
    Client,
    client_backoff_seconds,
    list_active_clients,
    mark_client_done,
    update_client_state,
)
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.observer import run_observer_with_report
from appointment_bot.services.runtime import LockBusyError, single_run_lock

logger = logging.getLogger(__name__)


def run_queue() -> int:
    return run_queue_with_report().exit_code


def run_queue_with_report() -> RunReport:
    try:
        settings = load_settings(require_login=False)
        setup_logging(settings)
        cleanup_old_files(settings)
        return _run_queue_with_settings(settings)
    except LockBusyError as exc:
        logger.warning("%s", exc)
        return RunReport(
            status="skipped",
            message=str(exc),
            exit_code=0,
            details={
                "checked_clients": 0,
                "confirmed_reservations": 0,
                "uncertain_reservations": 0,
                "failed_clients": 0,
            },
        )
    except Exception as exc:
        logger.exception("Client queue failed")
        return RunReport(
            status="error",
            message=str(exc),
            exit_code=1,
            details={
                "checked_clients": 0,
                "confirmed_reservations": 0,
                "uncertain_reservations": 0,
                "failed_clients": 1,
                "error_type": type(exc).__name__,
            },
        )


def _run_queue_with_settings(settings: Settings) -> RunReport:
    checked_clients = 0
    confirmed_reservations = 0
    uncertain_reservations = 0
    failed_clients = 0
    results: list[dict[str, str]] = []
    rapid_reservation_mode = False

    with single_run_lock(settings):
        # TEMP REVIEW: La consulta ya excluye clientes terminados; por eso la cola
        # empieza siempre en el cliente pendiente de mayor prioridad.
        clients = list_active_clients(settings)
        if not clients:
            # TEMP REVIEW: Sin clientes pendientes se usa la cuenta de .env solo como
            # observadora. Este flujo no contiene captcha ni boton final de reserva.
            logger.info("No active clients; starting observer availability check")
            return run_observer_with_report(
                settings,
                use_lock=False,
                diagnostic=False,
                visible=False,
                notify=True,
            )

        logger.info("Starting client queue with %s active clients", len(clients))
        for client in clients:
            # TEMP REVIEW: El valor 0 significa todos los pendientes; un valor positivo
            # conserva un limite opcional de reservas confirmadas por ejecucion.
            if _reservation_limit_reached(settings, confirmed_reservations):
                logger.info(
                    "Queue reservation limit reached: %s",
                    settings.queue_max_reservations_per_run,
                )
                break

            checked_clients += 1
            # TEMP REVIEW: Solo el primer cliente pendiente conserva la ventana de
            # monitoreo. Tras una reserva, los siguientes hacen una sola revision.
            report = _run_client(settings, client, rapid_mode=rapid_reservation_mode)
            results.append(
                {
                    "client_id": client.client_id,
                    "mode": "rapid" if rapid_reservation_mode else "monitor",
                    "status": report.status,
                    "message": report.message,
                }
            )
            _update_state_from_report(settings, client, report)
            if report.exit_code != 0 or report.status == "error":
                failed_clients += 1

            if _is_programmed(report):
                # TEMP REVIEW: Programado y registered son los unicos estados que
                # excluyen automaticamente al cliente de ejecuciones futuras.
                mark_client_done(client.client_id, status="programmed", settings=settings)
                logger.info("Client marked as done: %s", client.client_id)
                continue

            if report.status == "registered":
                confirmed_reservations += 1
                rapid_reservation_mode = True
                mark_client_done(client.client_id, settings=settings)
                logger.info("Reservation confirmed for client: %s", client.client_id)
                if not _reservation_limit_reached(settings, confirmed_reservations):
                    _delay_between_clients(settings)
                continue

            if report.status == "reservation_unconfirmed":
                uncertain_reservations += 1
                update_client_state(
                    client.client_id,
                    status=report.status,
                    message=report.message,
                    exit_code=report.exit_code,
                    backoff_seconds=settings.error_backoff_seconds,
                    settings=settings,
                )
                logger.warning(
                    "Stopping queue after an unconfirmed reservation attempt: %s",
                    client.client_id,
                )
                break

            if report.status in {"error", "unknown"} or report.exit_code != 0:
                # TEMP REVIEW: Un fallo tecnico o ambiguo detiene la cola para no
                # saltar al cliente prioritario ni repetir el problema en otras cuentas.
                if report.status == "unknown":
                    failed_clients += 1
                    update_client_state(
                        client.client_id,
                        status=report.status,
                        message=report.message,
                        exit_code=1,
                        backoff_seconds=settings.error_backoff_seconds,
                        settings=settings,
                    )
                logger.warning(
                    "Stopping queue after terminal client result %s: %s",
                    report.status,
                    client.client_id,
                )
                break

            if report.status == "skipped":
                # TEMP REVIEW: Un backoff conserva al mismo cliente como prioritario;
                # no cuenta como exito ni permite avanzar a cuentas posteriores.
                logger.info("Stopping queue because client %s is in backoff", client.client_id)
                break

            if report.status == "available" and not settings.auto_reserve:
                logger.info(
                    "Stopping queue after availability alert with AUTO_RESERVE=false: %s",
                    client.client_id,
                )
                break

            # TEMP REVIEW: Sin reserva confirmada no se avanza al siguiente cliente.
            # La proxima ejecucion volvera a monitorear este mismo cliente prioritario.
            if report.status in {"unavailable", "partial", "available", "completed"}:
                logger.info(
                    "Stopping queue because client %s did not confirm a reservation",
                    client.client_id,
                )
                break

    queue_has_errors = bool(failed_clients or uncertain_reservations)
    queue_status = "error" if queue_has_errors else "completed"
    exit_code = 1 if queue_has_errors else 0
    message = (
        f"Cola finalizada con {failed_clients} cliente(s) con error y "
        f"{uncertain_reservations} reserva(s) sin confirmar. "
        f"Reservas confirmadas: {confirmed_reservations}. "
        f"Clientes revisados: {checked_clients}."
        if queue_has_errors
        else (
            f"Cola finalizada. Reservas confirmadas: {confirmed_reservations}. "
            f"Clientes revisados: {checked_clients}."
        )
    )
    return RunReport(
        status=queue_status,
        message=message,
        exit_code=exit_code,
        details={
            "checked_clients": checked_clients,
            "confirmed_reservations": confirmed_reservations,
            "uncertain_reservations": uncertain_reservations,
            "failed_clients": failed_clients,
            "results": results,
        },
    )


def _run_client(
    settings: Settings,
    client: Client,
    *,
    rapid_mode: bool = False,
) -> RunReport:
    logger.info("Starting queued appointment check for client %s", client.client_id)
    backoff_seconds = client_backoff_seconds(client.client_id, settings=settings)
    if backoff_seconds > 0:
        return RunReport(
            status="skipped",
            message=(
                f"Revision omitida por backoff del cliente. "
                f"Faltan {backoff_seconds} segundos."
            ),
            exit_code=0,
            client_id=client.client_id,
        )

    client_settings = settings_for_client(
        settings,
        username=client.username,
        password=client.password,
    )
    client_settings = _settings_with_client_state_dir(client_settings, client)
    if rapid_mode:
        client_settings = replace(
            client_settings,
            monitor_window_seconds=0,
            monitor_max_attempts=1,
        )
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
    if report.status in {"skipped", "unknown", "reservation_unconfirmed"}:
        return

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


def _reservation_limit_reached(
    settings: Settings,
    confirmed_reservations: int,
) -> bool:
    limit = settings.queue_max_reservations_per_run
    return limit > 0 and confirmed_reservations >= limit


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
