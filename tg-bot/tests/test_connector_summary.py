from datetime import date, datetime

import pytest

from budget_bot.connector.analytics import (
    budget_overview,
    find_category,
    find_member,
    summarize_spending,
)
from budget_bot.connector.inputs import DateRange, InvalidRequest
from budget_bot.connector.schemas import CategorySpending, MemberSpending
from budget_bot.periods import kyiv_day_range
from budget_bot.services.access import SINGLETON_HOUSEHOLD_ID
from budget_bot.services.reports import build_report

SEPTEMBER_1_TO_14 = DateRange(date(2026, 9, 1), date(2026, 9, 14))
DEFAULT_CATEGORY_NAMES = [
    "Їжа",
    "Транспорт",
    "Комунальні",
    "Оренда житла",
    "Розваги",
    "Здоров'я",
    "Одяг",
    "Діти",
    "Інше",
]


@pytest.mark.parametrize("name", ["Їжа", "їжа", "  ЇЖА "])
async def test_category_is_found_ignoring_case_and_spacing(readonly_session_factory, name):
    async with readonly_session_factory() as session:
        category = await find_category(session, name)
    assert category.name == "Їжа"


async def test_member_is_found_ignoring_case(readonly_session_factory):
    async with readonly_session_factory() as session:
        member = await find_member(session, "ОЛЯ")
    assert member.display_name == "Оля"


async def test_no_name_means_no_filter(readonly_session_factory):
    async with readonly_session_factory() as session:
        assert await find_category(session, None) is None
        assert await find_member(session, None) is None


async def test_unknown_category_lists_the_known_ones(readonly_session_factory):
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_category(session, "Кава")
    message = str(excinfo.value)
    assert "Unknown category 'Кава'" in message
    assert "Known categories: Їжа, Транспорт, Комунальні" in message


async def test_unknown_member_lists_the_known_ones(readonly_session_factory):
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_member(session, "Петро")
    assert "Unknown member 'Петро'. Known members: Сергій, Оля" in str(excinfo.value)


async def test_member_names_differing_only_by_case_are_ambiguous(
    budget_writer, readonly_session_factory
):
    await budget_writer.add_member("ОЛЯ", telegram_id=333)
    async with readonly_session_factory() as session:
        with pytest.raises(InvalidRequest) as excinfo:
            await find_member(session, "оля")
    assert "ambiguous" in str(excinfo.value)


async def test_overview_describes_the_data(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        # 22:30 UTC on the 14th is already 01:30 on the 15th in Kyiv.
        overview = await budget_overview(session, now_utc=datetime(2026, 9, 14, 22, 30))

    assert overview.today == date(2026, 9, 15)
    assert (overview.timezone, overview.currency) == ("Europe/Kyiv", "UAH")
    assert overview.members == ["Сергій", "Оля"]
    assert [c.name for c in overview.categories] == DEFAULT_CATEGORY_NAMES
    assert not any(c.is_custom for c in overview.categories)
    assert overview.expense_count == 5
    assert overview.first_expense_date == date(2026, 8, 31)
    # Expense 4 is 21:10 UTC on the 14th, but the 15th in Kyiv.
    assert overview.last_expense_date == date(2026, 9, 15)


async def test_overview_without_expenses(readonly_session_factory):
    async with readonly_session_factory() as session:
        overview = await budget_overview(session, now_utc=datetime(2026, 9, 14, 12, 0))
    assert overview.expense_count == 0
    assert (overview.first_expense_date, overview.last_expense_date) == (None, None)


async def test_summary_totals_and_breakdowns(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, SEPTEMBER_1_TO_14, category=None, member=None)

    assert (summary.start_date, summary.end_date) == (date(2026, 9, 1), date(2026, 9, 14))
    assert (summary.category, summary.member) == (None, None)
    assert summary.total == 1550
    assert summary.expense_count == 3
    assert summary.by_category == [
        CategorySpending(name="Їжа", amount=1450, share_percent=93.5, count=2),
        CategorySpending(name="Транспорт", amount=100, share_percent=6.5, count=1),
    ]
    assert summary.by_member == [
        MemberSpending(name="Оля", amount=1300, count=2),
        MemberSpending(name="Сергій", amount=250, count=1),
    ]


@pytest.mark.parametrize(
    ("day", "total"),
    [
        (date(2026, 9, 14), 1200),  # 23:30 Kyiv still belongs to the 14th
        (date(2026, 9, 15), 600),  # 00:10 Kyiv belongs to the 15th, though UTC says the 14th
        (date(2026, 8, 31), 350),
    ],
)
async def test_days_are_kyiv_calendar_days(early_september, readonly_session_factory, day, total):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, DateRange(day, day), category=None, member=None)
    assert summary.total == total


async def test_summary_narrowed_to_a_category_and_a_member(
    early_september, readonly_session_factory
):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(
            session,
            SEPTEMBER_1_TO_14,
            category=await find_category(session, "їжа"),
            member=await find_member(session, "оля"),
        )
    assert (summary.category, summary.member) == ("Їжа", "Оля")
    assert summary.total == 1200
    assert summary.by_member == [MemberSpending(name="Оля", amount=1200, count=1)]


async def test_empty_range_is_zero_not_an_error(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(
            session, DateRange(date(2026, 7, 1), date(2026, 7, 31)), category=None, member=None
        )
    assert (summary.total, summary.expense_count) == (0, 0)
    assert (summary.by_category, summary.by_member) == ([], [])


async def test_summary_agrees_with_the_bots_report(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        summary = await summarize_spending(session, SEPTEMBER_1_TO_14, category=None, member=None)
        report = await build_report(
            session, SINGLETON_HOUSEHOLD_ID, kyiv_day_range(date(2026, 9, 1), date(2026, 9, 14))
        )
    assert summary.total == report.total
    assert [(c.name, c.amount, c.share_percent) for c in summary.by_category] == [
        (c.name, c.amount, c.share) for c in report.by_category
    ]
    assert [(m.name, m.amount) for m in summary.by_member] == [
        (m.display_name, m.amount) for m in report.by_member
    ]


async def _summary(session_factory, one_time):
    async with session_factory() as session:
        return await summarize_spending(
            session, SEPTEMBER_1_TO_14, category=None, member=None, one_time=one_time
        )


async def test_summary_all_reports_one_time_parts(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "all")

    assert summary.one_time == "all"
    assert (summary.total, summary.one_time_amount, summary.expense_count) == (6850, 5300, 5)
    assert summary.by_category == [
        CategorySpending(
            name="Діти", amount=5000, share_percent=73.0, count=1, one_time_amount=5000
        ),
        CategorySpending(name="Їжа", amount=1750, share_percent=25.5, count=3, one_time_amount=300),
        CategorySpending(name="Транспорт", amount=100, share_percent=1.5, count=1),
    ]
    assert summary.by_member == [
        MemberSpending(name="Оля", amount=6300, count=3, one_time_amount=5000),
        MemberSpending(name="Сергій", amount=550, count=2, one_time_amount=300),
    ]


async def test_summary_exclude_is_regular_only(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "exclude")

    assert (summary.total, summary.one_time_amount) == (1550, 0)
    assert [(c.name, c.amount, c.one_time_amount) for c in summary.by_category] == [
        ("Їжа", 1450, 0),
        ("Транспорт", 100, 0),
    ]


async def test_summary_only_one_time(september_one_time, readonly_session_factory):
    summary = await _summary(readonly_session_factory, "only")

    assert (summary.total, summary.one_time_amount, summary.expense_count) == (5300, 5300, 2)
    assert [(c.name, c.amount, c.share_percent) for c in summary.by_category] == [
        ("Діти", 5000, 94.3),
        ("Їжа", 300, 5.7),
    ]


async def test_summary_only_without_one_time_expenses_is_zero(
    early_september, readonly_session_factory
):
    summary = await _summary(readonly_session_factory, "only")

    assert (summary.total, summary.one_time_amount, summary.expense_count) == (0, 0, 0)
    assert (summary.by_category, summary.by_member) == ([], [])
