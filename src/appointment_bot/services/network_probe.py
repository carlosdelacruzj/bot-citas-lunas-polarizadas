from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, Request, Response

from appointment_bot.utils.sanitization import sanitize_url


class SanitizedNetworkTrace:
    def __init__(self) -> None:
        self.phase = "startup"
        self._requests: dict[Request, dict[str, object]] = {}
        self._entries: list[dict[str, object]] = []

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response)

    def mark(self, phase: str) -> None:
        self.phase = phase

    def classify(self, *, preloaded: bool) -> str:
        if preloaded:
            return "preloaded"

        relevant = [
            entry
            for entry in self._entries
            if entry.get("phase") in {"hidden_postback", "site_selection"}
        ]
        if any(
            entry.get("method") == "POST"
            and str(entry.get("url") or "").lower().endswith(".aspx")
            and str(entry.get("mime_type") or "").lower().startswith("text/plain")
            for entry in relevant
        ):
            return "webforms_postback"
        if any(entry.get("resource_type") in {"xhr", "fetch"} for entry in relevant):
            return "ajax"
        if any(
            entry.get("method") == "POST" and entry.get("resource_type") == "document"
            for entry in relevant
        ):
            return "webforms_postback"
        return "unknown"

    def save(
        self,
        diagnostics_dir: Path,
        *,
        dom_states: list[dict[str, object]],
        network_source: str,
    ) -> tuple[Path, Path]:
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        har_path = diagnostics_dir / f"availability-probe-{stamp}.har"
        summary_path = diagnostics_dir / f"availability-probe-{stamp}.json"

        har_entries = [self._har_entry(entry) for entry in self._entries]
        har = {
            "log": {
                "version": "1.2",
                "creator": {"name": "appointment-bot-sanitized-probe", "version": "1"},
                "pages": [],
                "entries": har_entries,
                "comment": (
                    "Sanitized metadata only: no headers, cookies, bodies, credentials "
                    "or response content are stored."
                ),
            }
        }
        summary = {
            "network_source": network_source,
            "events": self._entries,
            "dom_states": dom_states,
            "sensitive_data_policy": {
                "headers": "omitted",
                "cookies": "omitted",
                "request_bodies": "omitted",
                "response_bodies": "omitted",
                "query_values": "redacted",
            },
        }
        har_path.write_text(json.dumps(har, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return har_path, summary_path

    def _on_request(self, request: Request) -> None:
        started = time.monotonic()
        entry = {
            "phase": self.phase,
            "started_at": datetime.now(UTC).isoformat(),
            "method": request.method,
            "url": sanitize_url(request.url),
            "resource_type": request.resource_type,
            "navigation": request.is_navigation_request(),
            "status": None,
            "mime_type": "",
            "size": None,
            "duration_ms": None,
        }
        self._requests[request] = {"started": started, "entry": entry}
        self._entries.append(entry)

    def _on_response(self, response: Response) -> None:
        tracked = self._requests.get(response.request)
        if tracked is None:
            return

        entry = tracked["entry"]
        entry["status"] = response.status
        entry["duration_ms"] = round(
            (time.monotonic() - float(tracked["started"])) * 1_000,
            1,
        )
        try:
            entry["mime_type"] = response.header_value("content-type") or ""
            content_length = response.header_value("content-length")
            entry["size"] = int(content_length) if content_length else None
        except (PlaywrightError, TypeError, ValueError):
            entry["size"] = None

    @staticmethod
    def _har_entry(entry: dict[str, object]) -> dict[str, object]:
        return {
            "startedDateTime": entry["started_at"],
            "time": entry["duration_ms"] or 0,
            "request": {
                "method": entry["method"],
                "url": entry["url"],
                "httpVersion": "",
                "headers": [],
                "queryString": [],
                "cookies": [],
                "headersSize": -1,
                "bodySize": -1,
            },
            "response": {
                "status": entry["status"] or 0,
                "statusText": "",
                "httpVersion": "",
                "headers": [],
                "cookies": [],
                "content": {
                    "size": entry["size"] or 0,
                    "mimeType": entry["mime_type"],
                },
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": entry["size"] or -1,
            },
            "cache": {},
            "timings": {"send": 0, "wait": entry["duration_ms"] or 0, "receive": 0},
            "comment": f"phase={entry['phase']}; resource_type={entry['resource_type']}",
        }
