from __future__ import annotations

import logging
import mimetypes
import os
import secrets
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from appointment_bot.config import load_settings
from appointment_bot.services.local_api import DEFAULT_HOST, LocalApiHandler
from appointment_bot.services.logger import setup_logging

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_PORT = 8766
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class AdminApiHandler(LocalApiHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health" or path.startswith("/api/"):
            super().do_GET()
            return
        self._serve_dashboard(path)

    def _serve_dashboard(self, request_path: str) -> None:
        root = getattr(self.server, "dashboard_root", None)
        if root is None or not root.is_dir():
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "status": "dashboard_unavailable",
                    "message": "Run scripts/start-admin-dashboard.ps1 to build the dashboard.",
                },
            )
            return

        relative = unquote(request_path).lstrip("/") or "index.html"
        candidate = (root / relative).resolve()
        if root not in candidate.parents and candidate != root:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"status": "not_found", "message": "Dashboard asset not found."},
            )
            return
        if not candidate.is_file():
            candidate = root / "index.html"
        self._send_dashboard_file(candidate)

    def _send_dashboard_file(self, path: Path) -> None:
        body = path.read_bytes()
        content_type, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'",
        )
        session_token = getattr(self.server, "dashboard_session_token", "")
        self.send_header(
            "Set-Cookie",
            "appointment_bot_dashboard="
            f"{session_token}; Path=/; HttpOnly; SameSite=Strict",
        )
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)


def create_admin_api_server() -> ThreadingHTTPServer:
    host = os.getenv("APPOINTMENT_BOT_ADMIN_API_HOST", DEFAULT_HOST)
    serve_dashboard = os.getenv("APPOINTMENT_BOT_SERVE_DASHBOARD", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    token = os.getenv("APPOINTMENT_BOT_API_TOKEN", "").strip()
    if serve_dashboard and host not in LOOPBACK_HOSTS:
        raise ValueError("The bundled dashboard can only bind to a loopback interface.")
    if host not in LOOPBACK_HOSTS and not token:
        raise ValueError(
            "APPOINTMENT_BOT_API_TOKEN is required when the admin API binds "
            "outside the loopback interface."
        )
    port = int(os.getenv("APPOINTMENT_BOT_ADMIN_API_PORT", str(DEFAULT_ADMIN_PORT)))
    handler = AdminApiHandler if serve_dashboard else LocalApiHandler
    server = ThreadingHTTPServer((host, port), handler)
    server.worker_controller = None
    server.restart_callback = None
    server.dashboard_session_token = secrets.token_urlsafe(32) if serve_dashboard else ""
    server.dashboard_root = _dashboard_root() if serve_dashboard else None
    return server


def _dashboard_root() -> Path:
    configured = os.getenv("APPOINTMENT_BOT_DASHBOARD_DIR", "").strip()
    if configured:
        return Path(configured).resolve()
    return (Path(__file__).resolve().parents[3] / "dashboard/dist/dashboard/browser").resolve()


def run_admin_api() -> int:
    _set_working_directory()
    settings = load_settings(require_login=False)
    setup_logging(settings)
    server = create_admin_api_server()
    host, port = server.server_address[:2]
    logger.info("Admin API listening on http://%s:%s", host, port)
    if getattr(server, "dashboard_root", None) is not None:
        logger.info("Dashboard available on http://%s:%s/", host, port)
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
