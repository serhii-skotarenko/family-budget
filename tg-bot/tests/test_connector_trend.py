from datetime import date

import pytest

from budget_bot.connector.analytics import (
    BucketSpan,
    find_member,
    spending_trend,
    trend_buckets,
)
from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import BreakdownItem, TrendBucket
from tests.conftest import kyiv

SEPTEMBER_1_TO_14 = DateRange(date(2026, 9, 1), date(2026, 9, 14))


def test_weeks_run_monday_to_sunday_and_clipped_edges_are_partial():
    # 1 September 2026 is a Tuesday, 14 September a Monday.
    assert trend_buckets(SEPTEMBER_1_TO_14, "week") == [
        BucketSpan(date(2026, 9, 1), date(2026, 9, 6), partial=True),
        BucketSpan(date(2026, 9, 7), date(2026, 9, 13), partial=False),
        BucketSpan(date(2026, 9, 14), date(2026, 9, 14), partial=True),
    ]


def test_months_are_calendar_months():
    assert trend_buckets(DateRange(date(2026, 1, 15), date(2026, 3, 31)), "month") == [
        BucketSpan(date(2026, 1, 15), date(2026, 1, 31), partial=True),
        BucketSpan(date(2026, 2, 1), date(2026, 2, 28), partial=False),
        BucketSpan(date(2026, 3, 1), date(2026, 3, 31), partial=False),
    ]


def test_sixty_buckets_are_allowed():
    assert len(trend_buckets(DateRange(date(2021, 1, 1), date(2025, 12, 31)), "month")) == 60


@pytest.mark.parametrize(
    ("date_range", "granularity", "hint"),
    [
        (
            DateRange(date(2025, 1, 1), date(2026, 12, 31)),
            "week",
            'gives 105 week buckets (max 60); use granularity="month" or a shorter date range',
        ),
        (
            DateRange(date(2021, 1, 1), date(2026, 1, 1)),
            "month",
            "gives 61 month buckets (max 60); use a shorter date range",
        ),
    ],
)
def test_too_many_buckets_are_rejected_with_a_hint(date_range, granularity, hint):
    with pytest.raises(InvalidRequest) as excinfo:
        trend_buckets(date_range, granularity)
    assert hint in str(excinfo.value)


async def test_weekly_trend_split_by_category(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="category",
            category=None,
            member=None,
        )
    assert trend.buckets == [
        TrendBucket(
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 6),
            partial=True,
            total=350,
            count=2,
            breakdown=[
                BreakdownItem(name="Їжа", amount=250, count=1),
                BreakdownItem(name="Транспорт", amount=100, count=1),
            ],
        ),
        TrendBucket(
            start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 13),
            partial=False,
            total=0,
            count=0,
            breakdown=[],
        ),
        TrendBucket(
            start_date=date(2026, 9, 14),
            end_date=date(2026, 9, 14),
            partial=True,
            total=1200,
            count=1,
            breakdown=[BreakdownItem(name="Їжа", amount=1200, count=1)],
        ),
    ]


async def test_split_by_member_and_no_split(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        by_member = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="member",
            category=None,
            member=None,
        )
        unsplit = await spending_trend(
            session,
            SEPTEMBER_1_TO_14,
            granularity="week",
            split_by="none",
            category=None,
            member=None,
        )
    assert by_member.buckets[0].breakdown == [
        BreakdownItem(name="Сергій", amount=250, count=1),
        BreakdownItem(name="Оля", amount=100, count=1),
    ]
    assert [b.total for b in unsplit.buckets] == [350, 0, 1200]
    assert [b.breakdown for b in unsplit.buckets] == [None, None, None]


async def test_monthly_trend_for_one_member(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            DateRange(date(2026, 8, 1), date(2026, 9, 30)),
            granularity="month",
            split_by="none",
            category=None,
            member=await find_member(session, "Сергій"),
        )
    assert trend.member == "Сергій"
    assert [(b.start_date, b.end_date, b.partial, b.total, b.count) for b in trend.buckets] == [
        (date(2026, 8, 1), date(2026, 8, 31), False, 350, 1),
        (date(2026, 9, 1), date(2026, 9, 30), False, 850, 2),
    ]


async def test_week_boundary_follows_kyiv_time_across_the_dst_switch(
    budget_writer, readonly_session_factory
):
    # Kyiv leaves summer time at 04:00 on Sunday 25 October 2026 (UTC+3 -> UTC+2).
    # Both expenses fall on 25 October in UTC but in different Kyiv weeks.
    await budget_writer.add_expense(
        category="Їжа", member="Сергій", amount=300, at=kyiv(2026, 10, 25, 23, 30)
    )
    await budget_writer.add_expense(
        category="Їжа", member="Оля", amount=200, at=kyiv(2026, 10, 26, 0, 30)
    )
    async with readonly_session_factory() as session:
        trend = await spending_trend(
            session,
            DateRange(date(2026, 10, 19), date(2026, 10, 26)),
            granularity="week",
            split_by="none",
            category=None,
            member=None,
        )
    assert [(b.start_date, b.end_date, b.partial, b.total) for b in trend.buckets] == [
        (date(2026, 10, 19), date(2026, 10, 25), False, 300),
        (date(2026, 10, 26), date(2026, 10, 26), True, 200),
    ]
