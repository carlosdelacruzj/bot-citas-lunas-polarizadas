from __future__ import annotations

import argparse
import json
import logging
import random
import threading
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict, replace

from appointment_bot.config import Settings, load_settings
from appointment_bot.domain import RunReport, public_report_dict
from appointment_bot.main import run_with_report
from appointment_bot.services.cleanup import cleanup_old_files
from appointment_bot.services.client_runtime import (
    report_is_programmed,
    settings_with_client_state_dir,
)
from appointment_bot.services.client_transitions import (
    client_can_submit,
    reconcile_pending_submission,
)
from appointment_bot.services.database import (
    Client,
    client_backoff_seconds,
    client_reservation_pending,
    get_client,
    list_active_clients,
    mark_client_done,
    mark_client_submission_intent,
    mark_client_submission_pending,
    update_client_state,
)
from appointment_bot.services.logger import setup_logging
from appointment_bot.services.observer import run_observer_with_report
from appointment_bot.services.run_reporting import settings_for_client
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


def _run_queue_with_settings(
    settings: Settings,
    *,
    use_lock: bool = True,
    initial_rapid_mode: bool = False,
    observe_when_empty: bool = True,
    initial_confirmed_reservations: int = 0,
    cancel_event: threading.Event | None = None,
    apply_unknown_backoff: bool = True,
    on_client_start: Callable[[Client], None] | None = None,
) -> RunReport:
    checked_clients = 0
    confirmed_reservations = initial_confirmed_reservations
    uncertain_reservations = 0
    failed_clients = 0
    results: list[dict[str, str]] = []
    rapid_reservation_mode = initial_rapid_mode

    lock_context = single_run_lock(settings) if use_lock else nullcontext()
    with lock_context:
        # La consulta ya excluye clientes terminados; por eso la cola
        # empieza siempre en el cliente pendiente de mayor prioridad.
        clients = list_active_clients(settings)
        if not clients:
            if not observe_when_empty:
                return RunReport(
                    status="completed",
                    message="No quedan clientes pendientes para la cola rapida.",
                    exit_code=0,
                    details={
                        "checked_clients": 0,
                        "confirmed_reservations": 0,
                        "uncertain_reservations": 0,
                        "failed_clients": 0,
                        "results": [],
                    },
                )
            # Sin clientes pendientes se usa la cuenta de .env solo como
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
            if cancel_event is not None and cancel_event.is_set():
                return RunReport(
                    status="paused",
                    message="La cola rapida fue interrumpida por una pausa.",
                    exit_code=0,
                    details={
                        "checked_clients": checked_clients,
                        "confirmed_reservations": (
                            confirmed_reservations - initial_confirmed_reservations
                        ),
                        "uncertain_reservations": uncertain_reservations,
                        "failed_clients": failed_clients,
                        "results": results,
                    },
                )
            # El valor 0 significa todos los pendientes; un valor positivo
            # conserva un limite opcional de reservas confirmadas por ejecucion.
            if _reservation_limit_reached(settings, confirmed_reservations):
                logger.info(
                    "Queue reservation limit reached: %s",
                    settings.queue_max_reservations_per_run,
                )
                break

            checked_clients += 1
            if on_client_start is not None:
                on_client_start(client)
            # Solo el primer cliente pendiente conserva la ventana de
            # monitoreo. Tras una reserva, los siguientes hacen una sola revision.
            report = _run_client(
                settings,
                client,
                rapid_mode=rapid_reservation_mode,
                cancel_event=cancel_event,
            )
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

            if report_is_programmed(report):
                # Programado y registered son los unicos estados que
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
                    _delay_between_clients(settings, cancel_event=cancel_event)
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
                # Un fallo tecnico o ambiguo detiene la cola para no
                # saltar al cliente prioritario ni repetir el problema en otras cuentas.
                if report.status == "unknown":
                    failed_clients += 1
                    update_client_state(
                        client.client_id,
                        status=report.status,
                        message=report.message,
                        exit_code=1,
                        backoff_seconds=(
                            settings.error_backoff_seconds if apply_unknown_backoff else None
                        ),
                        settings=settings,
                    )
                logger.warning(
                    "Stopping queue after terminal client result %s: %s",
                    report.status,
                    client.client_id,
                )
                break

            if report.status == "skipped":
                # Un backoff conserva al mismo cliente como prioritario;
                # no cuenta como exito ni permite avanzar a cuentas posteriores.
                logger.info("Stopping queue because client %s is in backoff", client.client_id)
                break

            if report.status == "available" and not settings.auto_reserve:
                logger.info(
                    "Stopping queue after availability alert with AUTO_RESERVE=false: %s",
                    client.client_id,
                )
                break

            # Sin reserva confirmada no se avanza al siguiente cliente.
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
    run_confirmed_reservations = confirmed_reservations - initial_confirmed_reservations
    message = (
        f"Cola finalizada con {failed_clients} cliente(s) con error y "
        f"{uncertain_reservations} reserva(s) sin confirmar. "
        f"Reservas confirmadas: {run_confirmed_reservations}. "
        f"Clientes revisados: {checked_clients}."
        if queue_has_errors
        else (
            f"Cola finalizada. Reservas confirmadas: {run_confirmed_reservations}. "
            f"Clientes revisados: {checked_clients}."
        )
    )
    return RunReport(
        status=queue_status,
        message=message,
        exit_code=exit_code,
        details={
            "checked_clients": checked_clients,
            "confirmed_reservations": run_confirmed_reservations,
            "uncertain_reservations": uncertain_reservations,
            "failed_clients": failed_clients,
            "results": results,
        },
    )


def run_rapid_queue_with_settings(
    settings: Settings,
    *,
    initial_confirmed_reservations: int = 0,
    cancel_event: threading.Event | None = None,
    on_client_start: Callable[[Client], None] | None = None,
) -> RunReport:
    return _run_queue_with_settings(
        settings,
        use_lock=False,
        initial_rapid_mode=True,
        observe_when_empty=False,
        initial_confirmed_reservations=initial_confirmed_reservations,
        cancel_event=cancel_event,
        apply_unknown_backoff=False,
        on_client_start=on_client_start,
    )


def _run_client(
    settings: Settings,
    client: Client,
    *,
    rapid_mode: bool = False,
    cancel_event: threading.Event | None = None,
) -> RunReport:
    logger.info("Starting queued appointment check for client %s", client.client_id)
    current_client = get_client(client.client_id, settings=settings)
    if current_client is None or not current_client.active or current_client.done:
        return RunReport(
            status="skipped",
            message="El cliente dejo de estar activo antes de iniciar la revision.",
            exit_code=0,
            client_id=client.client_id,
        )

    backoff_seconds = client_backoff_seconds(client.client_id, settings=settings)
    if backoff_seconds > 0:
        return RunReport(
            status="skipped",
            message=(
                f"Revision omitida por backoff del cliente. Faltan {backoff_seconds} segundos."
            ),
            exit_code=0,
            client_id=client.client_id,
        )

    client = current_client
    client_settings = settings_for_client(
        settings,
        username=client.username,
        password=client.password,
    )
    client_settings = settings_with_client_state_dir(client_settings, client)
    pending_submission = client_reservation_pending(
        client.client_id,
        settings=settings,
    )
    if pending_submission:
        client_settings = replace(client_settings, auto_reserve=False)
    if rapid_mode:
        client_settings = replace(
            client_settings,
            monitor_window_seconds=0,
            monitor_max_attempts=1,
        )
    report = run_with_report(
        client_settings,
        client_id=client.client_id,
        use_lock=False,
        apply_jitter=False,
        cleanup_files=False,
        record_history=True,
        cancel_event=cancel_event,
        enforce_run_timeout=not rapid_mode,
        can_submit=lambda: client_can_submit(client.client_id, settings),
        on_submission_intent=lambda: mark_client_submission_intent(
            client.client_id,
            settings=settings,
        ),
        on_submission_started=lambda: mark_client_submission_pending(
            client.client_id,
            settings=settings,
        ),
    )
    if pending_submission and not report_is_programmed(report):
        if reconcile_pending_submission(client.client_id, report, settings):
            return report
        return replace(
            report,
            status="reservation_unconfirmed",
            message=(
                "Existe un envio de reserva pendiente. Se verifico el portal sin "
                "intentar una nueva reserva."
            ),
            exit_code=1,
        )
    return report


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


def _reservation_limit_reached(
    settings: Settings,
    confirmed_reservations: int,
) -> bool:
    limit = settings.queue_max_reservations_per_run
    return limit > 0 and confirmed_reservations >= limit


def _delay_between_clients(
    settings: Settings,
    *,
    cancel_event: threading.Event | None = None,
) -> None:
    if settings.queue_delay_max_seconds <= 0:
        return

    delay = random.randint(
        settings.queue_delay_min_seconds,
        settings.queue_delay_max_seconds,
    )
    if delay <= 0:
        return

    logger.info("Waiting %s seconds before the next queued client", delay)
    if cancel_event is not None:
        cancel_event.wait(delay)
    else:
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
        print(json.dumps(public_report_dict(report), ensure_ascii=False))
    else:
        print(asdict(report))
    raise SystemExit(report.exit_code)


if __name__ == "__main__":
    main()
