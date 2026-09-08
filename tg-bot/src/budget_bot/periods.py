"""Calendar period boundaries in Europe/Kyiv, returned as UTC-naive ranges.

Boundaries are built in the `date` domain and only then converted to UTC, so
DST transitions (which happen at 03:00/04:00 local, never at midnight) cannot
shift a period start by an hour.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")

MONTHS_UK = (
    "січень",
    "лютий",
    "березень",
    "квітень",
    "травень",
    "червень",
    "липень",
    "серпень",
    "вересень",
    "жовтень",
    "листопад",
    "грудень",
)


class Period(StrEnum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


PERIOD_TITLES = {
    Period.TODAY: "Сьогодні",
    Period.WEEK: "Поточний тиждень",
    Period.MONTH: "Поточний місяць",
    Period.YEAR: "Поточний рік",
}


@dataclass(frozen=True)
class PeriodRange:
    """Half-open [start, end) range of UTC-naive datetimes."""

    start: datetime
    end: datetime
    label: str


def to_kyiv(dt_utc: datetime) -> datetime:
    return dt_utc.replace(tzinfo=UTC).astimezone(KYIV)


def _kyiv_midnight_as_utc(day: date) -> datetime:
    local = datetime(day.year, day.month, day.day, tzinfo=KYIV)
    return local.astimezone(UTC).replace(tzinfo=None)


def period_range(period: Period, now_utc: datetime) -> PeriodRange:
    today = to_kyiv(now_utc).date()

    if period is Period.TODAY:
        first, last = today, today
        label = f"сьогодні ({first:%d.%m.%Y})"
    elif period is Period.WEEK:
        first = today - timedelta(days=today.weekday())
        last = first + timedelta(days=6)
        label = f"поточний тиждень ({first:%d.%m}–{last:%d.%m.%Y})"
    elif period is Period.MONTH:
        first = today.replace(day=1)
        last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
        label = f"поточний місяць ({MONTHS_UK[first.month - 1]} {first.year})"
    else:
        first = date(today.year, 1, 1)
        last = date(today.year, 12, 31)
        label = f"поточний рік ({first.year})"

    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=label,
    )


def parse_custom_range(raw: str) -> PeriodRange:
    """Parse 'DD.MM.YYYY-DD.MM.YYYY' into an inclusive-of-last-day range."""
    parts = [chunk.strip() for chunk in raw.replace("—", "-").replace("–", "-").split("-")]
    if len(parts) != 2 or not all(parts):
        raise ValueError("Формат: ДД.ММ.РРРР-ДД.ММ.РРРР, наприклад 01.09.2026-15.09.2026")
    try:
        first = datetime.strptime(parts[0], "%d.%m.%Y").date()
        last = datetime.strptime(parts[1], "%d.%m.%Y").date()
    except ValueError as exc:
        raise ValueError("Формат: ДД.ММ.РРРР-ДД.ММ.РРРР, наприклад 01.09.2026-15.09.2026") from exc
    if last < first:
        raise ValueError("Кінцева дата має бути не раніше за початкову.")
    return PeriodRange(
        start=_kyiv_midnight_as_utc(first),
        end=_kyiv_midnight_as_utc(last + timedelta(days=1)),
        label=f"{first:%d.%m.%Y}–{last:%d.%m.%Y}",
    )


def format_date_short(dt_utc: datetime) -> str:
    return f"{to_kyiv(dt_utc):%d.%m}"


def format_datetime(dt_utc: datetime) -> str:
    return f"{to_kyiv(dt_utc):%d.%m.%Y %H:%M}"
