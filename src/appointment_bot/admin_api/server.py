from __future__ import annotations

import logging
import os
from http.server import ThreadingHTTPServer
from pathlib import Path

from appointment_bot.config import load_settings
from appointment_bot.services.local_api import DEFAULT_HOST, LocalApiHandler
from appointment_bot.services.logger import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_PORT = 8766


def create_admin_api_server() -> ThreadingHTTPServer:
    host = os.getenv("APPOINTMENT_BOT_ADMIN_API_HOST", DEFAULT_HOST)
    token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise ValueError(
            "APPOINTMENT_BOT_API_TOKEN is required when the admin API binds "
            "outside the loopback interface."
        )
    port = int(os.getenv("APPOINTMENT_BOT_ADMIN_API_PORT", str(DEFAULT_ADMIN_PORT)))
    server = ThreadingHTTPServer((host, port), LocalApiHandler)
    server.worker_controller = None
    server.restart_callback = None
    return server


def run_admin_api() -> int:
    _set_working_directory()
    settings = load_settings(require_login=False)
    setup_logging(settings)
    server = create_admin_api_server()
    host, port = server.server_address[:2]
    logger.info("Admin API listening on http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Admin API shutdown requested")
    finally:
        server.server_close()
    return 0


def _set_working_directory() -> None:
    configured = os.getenv("APPOINTMENT_BOT_WORKDIR", "").strip()
    workdir = Path(configured) if configured else Path(__file__).resolve().parents[3]
    if not workdir.exists():
        raise FileNotFoundError(f"Appointment bot working directory does not exist: {workdir}")
    os.chdir(workdir)


def main() -> None:
    raise SystemExit(run_admin_api())


if __name__ == "__main__":
    main()
