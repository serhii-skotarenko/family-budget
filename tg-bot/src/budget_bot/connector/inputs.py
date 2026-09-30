"""Parsing and validation of connector tool arguments.

Everything here raises InvalidRequest with a message meant for the model: it
names the argument, says what was wrong and what a valid value looks like.
"""

from dataclasses import dataclass
from datetime import date, datetime

MIN_YEAR = 2000
MAX_YEAR = 2100
MAX_LIST_LIMIT = 200
MAX_TREND_BUCKETS = 60


class InvalidRequest(ValueError):
    """A problem with tool arguments that the caller can fix."""


@dataclass(frozen=True)
class DateRange:
    """Kyiv calendar days, both ends inclusive."""

    first: date
    last: date


def parse_date_range(start_date: str, end_date: str) -> DateRange:
    first = parse_day("start_date", start_date)
    last = parse_day("end_date", end_date)
    if last < first:
        raise InvalidRequest(
            f"end_date {last.isoformat()} is before start_date {first.isoformat()}"
        )
    return DateRange(first=first, last=last)


def check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise InvalidRequest(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {limit}")


def check_not_negative(name: str, value: int | None) -> None:
    if value is not None and value < 0:
        raise InvalidRequest(f"{name} must be 0 or greater, got {value}")


def parse_day(name: str, raw: str) -> date:
    try:
        day = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidRequest(
            f"{name} must be a valid calendar date in YYYY-MM-DD format, got {raw!r}"
        ) from None
    if not MIN_YEAR <= day.year <= MAX_YEAR:
        raise InvalidRequest(
            f"{name} must be between {MIN_YEAR}-01-01 and {MAX_YEAR}-12-31, got {raw!r}"
        )
    return day
