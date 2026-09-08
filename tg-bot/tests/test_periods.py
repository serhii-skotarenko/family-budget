from datetime import datetime

import pytest

from budget_bot.periods import (
    Period,
    format_date_short,
    format_datetime,
    parse_custom_range,
    period_range,
    to_kyiv,
)

# 2026-09-07 is a Monday. Kyiv is UTC+3 (EEST) in September.
NOW = datetime(2026, 9, 7, 9, 0)  # 12:00 Kyiv


def test_to_kyiv_adds_three_hours_in_summer():
    assert to_kyiv(NOW).hour == 12


def test_today_range():
    result = period_range(Period.TODAY, NOW)
    assert result.start == datetime(2026, 9, 6, 21, 0)
    assert result.end == datetime(2026, 9, 7, 21, 0)
    assert result.label == "сьогодні (07.09.2026)"


def test_week_starts_on_monday():
    result = period_range(Period.WEEK, NOW)
    assert result.start == datetime(2026, 9, 6, 21, 0)  # Mon 07.09 00:00 Kyiv
    assert result.end == datetime(2026, 9, 13, 21, 0)  # Mon 14.09 00:00 Kyiv
    assert result.label == "поточний тиждень (07.09–13.09.2026)"


def test_week_containing_sunday_still_starts_on_monday():
    sunday = datetime(2026, 9, 13, 9, 0)  # Sunday 12:00 Kyiv
    result = period_range(Period.WEEK, sunday)
    assert result.start == datetime(2026, 9, 6, 21, 0)
    assert result.end == datetime(2026, 9, 13, 21, 0)


def test_month_range_crossing_dst_end():
    # DST ends on 2026-10-25: October starts at UTC+3 and ends at UTC+2.
    october = datetime(2026, 10, 10, 9, 0)
    result = period_range(Period.MONTH, october)
    assert result.start == datetime(2026, 9, 30, 21, 0)
    assert result.end == datetime(2026, 10, 31, 22, 0)
    assert result.label == "поточний місяць (жовтень 2026)"


def test_year_range():
    result = period_range(Period.YEAR, NOW)
    assert result.start == datetime(2025, 12, 31, 22, 0)  # 01.01.2026 00:00 Kyiv (UTC+2)
    assert result.end == datetime(2026, 12, 31, 22, 0)
    assert result.label == "поточний рік (2026)"


def test_parse_custom_range_is_inclusive_of_the_last_day():
    result = parse_custom_range("01.09.2026-15.09.2026")
    assert result.start == datetime(2026, 8, 31, 21, 0)
    assert result.end == datetime(2026, 9, 15, 21, 0)
    assert result.label == "01.09.2026–15.09.2026"


@pytest.mark.parametrize(
    "raw",
    ["", "01.09.2026", "abc-def", "15.09.2026-01.09.2026", "32.09.2026-01.10.2026"],
)
def test_parse_custom_range_rejects_bad_input(raw):
    with pytest.raises(ValueError):
        parse_custom_range(raw)


def test_date_formatting_uses_kyiv_time():
    assert format_date_short(NOW) == "07.09"
    assert format_datetime(NOW) == "07.09.2026 12:00"
