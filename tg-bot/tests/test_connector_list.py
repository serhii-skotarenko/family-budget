from datetime import date

import pytest

from budget_bot.connector.analytics import find_category, find_member, list_expenses
from budget_bot.connector.inputs import DateRange
from budget_bot.connector.schemas import ExpensePage

ALL_DAYS = DateRange(date(2026, 8, 31), date(2026, 9, 15))


async def list_page(session_factory, **overrides) -> ExpensePage:
    arguments = {
        "date_range": ALL_DAYS,
        "category": None,
        "member": None,
        "search": None,
        "min_amount": None,
        "sort": "newest",
        "limit": 50,
        "offset": 0,
    } | overrides
    date_range = arguments.pop("date_range")
    async with session_factory() as session:
        return await list_expenses(session, date_range, **arguments)


@pytest.mark.parametrize(
    ("sort", "amounts"),
    [
        ("newest", [600, 1200, 100, 250, 350]),
        ("oldest", [350, 250, 100, 1200, 600]),
        ("largest", [1200, 600, 350, 250, 100]),
    ],
)
async def test_sort_orders(early_september, readonly_session_factory, sort, amounts):
    page = await list_page(readonly_session_factory, sort=sort)
    assert [item.amount for item in page.items] == amounts
    assert page.total_count == 5


async def test_items_carry_the_bot_id_kyiv_time_and_names(
    early_september, readonly_session_factory
):
    page = await list_page(
        readonly_session_factory, date_range=DateRange(date(2026, 9, 14), date(2026, 9, 14))
    )
    assert [item.model_dump(mode="json") for item in page.items] == [
        {
            "id": 3,
            "datetime": "2026-09-14T23:30:00+03:00",
            "amount": 1200,
            "category": "Їжа",
            "member": "Оля",
            "description": "Сільпо",
        }
    ]


async def test_search_ignores_case_in_cyrillic(early_september, readonly_session_factory):
    page = await list_page(readonly_session_factory, search="ТАКСІ")
    assert [item.description for item in page.items] == ["Таксі додому"]
    assert page.total_count == 1


async def test_min_amount_is_inclusive(early_september, readonly_session_factory):
    page = await list_page(readonly_session_factory, min_amount=350)
    assert [item.amount for item in page.items] == [600, 1200, 350]


async def test_category_and_member_filters(early_september, readonly_session_factory):
    async with readonly_session_factory() as session:
        food = await find_category(session, "Їжа")
        serhii = await find_member(session, "Сергій")
    page = await list_page(readonly_session_factory, category=food, member=serhii)
    assert [item.amount for item in page.items] == [250, 350]


@pytest.mark.parametrize(
    ("offset", "amounts", "next_offset"),
    [(0, [600, 1200], 2), (2, [100, 250], 4), (4, [350], None), (6, [], None)],
)
async def test_pages(early_september, readonly_session_factory, offset, amounts, next_offset):
    page = await list_page(readonly_session_factory, limit=2, offset=offset)
    assert [item.amount for item in page.items] == amounts
    assert (page.total_count, page.offset, page.next_offset) == (5, offset, next_offset)


async def test_total_count_is_taken_after_search(early_september, readonly_session_factory):
    # "к" occurs in "кава", "Таксі додому" and "Кіно"; expense 5 has no description.
    page = await list_page(readonly_session_factory, search="к", limit=1)
    assert (len(page.items), page.total_count, page.next_offset) == (1, 3, 1)
