from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol


class ApiTransport(Protocol):
    server: Any
    client_address: tuple[str, int]

    def _require_authorized(self, *, strict: bool = False) -> bool: ...

    def _authenticated_actor(self) -> str: ...

    def _read_json(self) -> dict[str, Any]: ...

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class ApiRequest:
    transport: ApiTransport
    path: str
    query: dict[str, list[str]]
    match: Any = None


@dataclass(frozen=True)
class Route:
    pattern: str | Callable[[str], Any | None]
    handle: Callable[[ApiRequest], None]
    authenticated: bool = True


def dispatch(request: ApiRequest, routes: Sequence[Route]) -> bool:
    for route in routes:
        match = (
            (True if request.path == route.pattern else None)
            if isinstance(route.pattern, str)
            else route.pattern(request.path)
        )
        # Some legacy parsers deliberately return an empty identifier for a 404 after auth.
        if match is None:
            continue
        if route.authenticated and not request.transport._require_authorized(strict=True):
            return True
        route.handle(replace(request, match=match))
        return True
    return False
