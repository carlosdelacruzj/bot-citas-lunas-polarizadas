from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from functools import wraps
from inspect import signature

from appointment_bot.core.models import AvailabilityResult
from appointment_bot.core.rules import parse_appointment_date


@dataclass
class AppointmentBudget:
    date_limit: int = 2
    hour_limit: int = 2
    submission_limit: int = 1
    predicate: Callable[[str, str], bool] | None = None
    dates: set[str] = field(default_factory=set)
    date_stages: set[tuple[str, str]] = field(default_factory=set)
    hours: int = 0
    submissions: int = 0
    requests: int = 0
    exhausted: bool = False

    def allowed_date(self, text: str) -> bool:
        return parse_appointment_date(text) is not None and (
            self.predicate is None or self.predicate(text, "00:00")
        )

    def candidates(self, dates: list[str]) -> list[str]:
        compatible = sorted(
            {text for text in dates if self.allowed_date(text)},
            key=parse_appointment_date,
        )
        return compatible[:self.date_limit]

    def admit_date(self, text: str, stage: str) -> bool:
        parsed = parse_appointment_date(text)
        if parsed is None:
            return False
        key = parsed.isoformat()
        if (key, stage) in self.date_stages or (
            key not in self.dates and len(self.dates) >= self.date_limit
        ):
            self.exhausted = True
            return False
        self.dates.add(key)
        self.date_stages.add((key, stage))
        return True

    def admit_hour(self) -> bool:
        if self.hours >= self.hour_limit:
            self.exhausted = True
            return False
        self.hours += 1
        return True

    def admit_submission(self) -> bool:
        if self.submissions >= self.submission_limit:
            self.exhausted = True
            return False
        self.submissions += 1
        return True

    def details(self) -> dict[str, object]:
        return {
            "date_limit": self.date_limit, "dates_consulted": len(self.dates),
            "hour_limit": self.hour_limit, "hours_checked": self.hours,
            "submission_limit": self.submission_limit, "submissions": self.submissions,
            "http_requests": self.requests, "budget_exhausted": self.exhausted,
        }


_CURRENT: ContextVar[AppointmentBudget | None] = ContextVar("appointment_budget", default=None)


def current_appointment_budget() -> AppointmentBudget | None:
    return _CURRENT.get()


def bounded_appointment_review(*, observer: bool = False):
    def decorate(function):
        parameters = signature(function)

        @wraps(function)
        def bounded(*args, **kwargs):
            if _CURRENT.get() is not None:
                return function(*args, **kwargs)
            arguments = parameters.bind(*args, **kwargs).arguments
            budget = AppointmentBudget(
                date_limit=1 if observer else 2,
                hour_limit=1 if observer else 2,
                submission_limit=0 if observer else 1,
                predicate=arguments.get("is_allowed_appointment"),
            )
            token = _CURRENT.set(budget)
            page = arguments.get("page")

            def count_request(_request):
                budget.requests += 1

            try:
                if page is not None and hasattr(page, "on"):
                    page.on("request", count_request)
                result = function(*args, **kwargs)
                if isinstance(result, tuple) and isinstance(result[0], AvailabilityResult):
                    result = (replace(result[0], details={
                        **(result[0].details or {}), "review_budget": budget.details(),
                    }), *result[1:])
                return result
            finally:
                if page is not None and hasattr(page, "remove_listener"):
                    page.remove_listener("request", count_request)
                _CURRENT.reset(token)

        return bounded
    return decorate
