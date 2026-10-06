from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, Route


class ManualReviewGuard:
    """Allow authentication and reading a program, then freeze network interaction."""

    def __init__(self, page: Page, login_url: str) -> None:
        self.login_url = urlsplit(login_url)
        self.login_complete = False
        self.listing_path: str | None = None
        self.locked = False
        page.context.route("**/*", self._route)

    def _route(self, route: Route) -> None:
        request = route.request
        url = urlsplit(request.url)
        same_origin = (url.scheme, url.netloc) == (
            self.login_url.scheme, self.login_url.netloc
        )
        allowed = False
        if not self.locked and same_origin:
            if request.method == "GET":
                allowed = request.resource_type in {"stylesheet", "script", "image", "font"}
                if request.resource_type == "document":
                    allowed = (
                        url.path == self.login_url.path
                        or url.path.casefold() == "/lunasoscurecidas/seguimiento.aspx"
                        or (
                            not self.login_complete
                            and request.redirected_from is not None
                        )
                    ) and not url.query
            elif request.method == "POST":
                if not self.login_complete and url.path == self.login_url.path:
                    allowed = not url.query
                elif self.login_complete and not url.query:
                    fields = parse_qs(request.post_data or "", keep_blank_values=True)
                    target = fields.get("__EVENTTARGET", [""])
                    argument = fields.get("__EVENTARGUMENT", [""])
                    allowed = (
                        url.path == self.listing_path
                        and len(target) == len(argument) == 1
                        and (
                            bool(re.fullmatch(
                                r"ctl00\$MainContent\$gvProgramacion\$ctl\d+\$btnAccion",
                                target[0],
                            )) and argument == [""]
                            or target == ["ctl00$MainContent$gvProgramacion"]
                            and argument == ["accion$0"]
                        )
                        and not any(
                            re.search(r"(?:^|\$)(?:btn|btg|ibtn)", key, re.I)
                            for key in fields
                        )
                    )
        if allowed:
            route.continue_()
        else:
            route.abort("blockedbyclient")

    def freeze(self, page: Page) -> None:
        self.locked = True
        page.evaluate("""() => {
            const banner = document.createElement('div');
            banner.textContent = 'Consulta protegida: reservar, cancelar y reprogramar '
                + 'estan bloqueados. Cierra y vuelve a abrir para actualizar la consulta.';
            banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;'
                + 'padding:12px;background:#153c32;color:white;text-align:center';
            document.body.prepend(banner);
            document.querySelectorAll('button,input[type=submit],input[type=image]')
                .forEach(element => { element.disabled = true; });
            document.addEventListener('submit', event => event.preventDefault(), true);
        }""")
