from datetime import date

import pytest

from budget_bot.connector.inputs import (
    DateRange,
    InvalidRequest,
    check_limit,
    check_not_negative,
    parse_date_range,
)


def test_parses_an_inclusive_range():
    assert parse_date_range("2026-09-01", "2026-09-14") == DateRange(
        date(2026, 9, 1), date(2026, 9, 14)
    )


def test_accepts_a_single_day_and_the_edges_of_supported_years():
    assert parse_date_range("2026-09-14", "2026-09-14") == DateRange(
        date(2026, 9, 14), date(2026, 9, 14)
    )
    assert parse_date_range("2000-01-01", "2100-12-31") == DateRange(
        date(2000, 1, 1), date(2100, 12, 31)
    )


@pytest.mark.parametrize(
    ("start_date", "end_date", "hint"),
    [
        ("14.09.2026", "2026-09-30", "start_date must be a valid calendar date in YYYY-MM-DD"),
        ("2026-09-01", "2026-02-30", "end_date must be a valid calendar date in YYYY-MM-DD"),
        ("1999-12-31", "2026-09-30", "start_date must be between 2000-01-01 and 2100-12-31"),
        ("2026-09-01", "2101-01-01", "end_date must be between 2000-01-01 and 2100-12-31"),
        ("2026-09-30", "2026-09-01", "end_date 2026-09-01 is before start_date 2026-09-30"),
    ],
)
def test_bad_ranges_are_rejected_with_a_hint(start_date, end_date, hint):
    with pytest.raises(InvalidRequest) as excinfo:
        parse_date_range(start_date, end_date)
    assert hint in str(excinfo.value)


@pytest.mark.parametrize("limit", [1, 200])
def test_limit_bounds_are_inclusive(limit):
    check_limit(limit)


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_outside_bounds_is_rejected(limit):
    with pytest.raises(InvalidRequest) as excinfo:
        check_limit(limit)
    assert f"limit must be between 1 and 200, got {limit}" in str(excinfo.value)


def test_negative_value_is_rejected_by_name():
    with pytest.raises(InvalidRequest) as excinfo:
        check_not_negative("offset", -1)
    assert "offset must be 0 or greater, got -1" in str(excinfo.value)


@pytest.mark.parametrize("value", [None, 0, 5])
def test_absent_zero_and_positive_values_pass(value):
    check_not_negative("min_amount", value)
