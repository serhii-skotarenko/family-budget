from datetime import datetime

from budget_bot.formatting import (
    format_expense_card,
    format_expense_line,
    format_expense_list,
    format_report,
    format_saved_expense,
)
from budget_bot.periods import Period, period_range
from budget_bot.services.expenses import create_expense, update_expense
from budget_bot.services.limits import LimitProgress
from budget_bot.services.reports import CategoryTotal, MemberTotal, Report
from tests.conftest import kyiv

NOW = datetime(2026, 9, 7, 9, 0)  # 12:00 Kyiv


async def make(session, household, member, category, **kwargs):
    return await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=kwargs.get("amount", 250),
        description=kwargs.get("description"),
        created_at=NOW,
    )


async def test_expense_line(session, household, member, category):
    expense = await make(session, household, member, category, description="кава")

    assert format_expense_line(expense) == "07.09 · 250\u00a0₴ · Їжа · Сергій — кава"


async def test_expense_line_without_description_and_with_index(
    session, household, member, category
):
    expense = await make(session, household, member, category)

    assert format_expense_line(expense, index=3) == "<b>3.</b> 07.09 · 250\u00a0₴ · Їжа · Сергій"


async def test_user_text_is_html_escaped(session, household, member, category):
    expense = await make(session, household, member, category, description="<b>hack</b>")

    assert "&lt;b&gt;hack&lt;/b&gt;" in format_expense_line(expense)
    assert "<b>hack</b>" not in format_expense_line(expense)


async def test_empty_list_uses_the_empty_message(session):
    assert format_expense_list([], "Останні витрати", "Витрат не знайдено") == (
        "Витрат не знайдено"
    )


async def test_list_is_numbered_from_one(session, household, member, category):
    first = await make(session, household, member, category, amount=1)
    second = await make(session, household, member, category, amount=2)

    text = format_expense_list([first, second], "Останні витрати", "порожньо")

    assert text.startswith("<b>Останні витрати</b>")
    assert "<b>1.</b>" in text and "<b>2.</b>" in text


async def test_card_shows_editor_when_edited(session, household, member, partner, category):
    expense = await make(session, household, member, category, description="кава")
    await update_expense(session, expense, editor_id=partner.id, amount=300)

    card = format_expense_card(expense)

    assert f"Витрата #{expense.id}" in card
    assert "300\u00a0₴" in card
    assert "Автор: Сергій" in card
    assert "Змінив(ла): Оля" in card


async def test_card_without_edit_has_no_editor_line(session, household, member, category):
    card = format_expense_card(await make(session, household, member, category))

    assert "Змінив(ла)" not in card


async def test_card_author_line_is_html_escaped(session, household, member, category):
    member.display_name = "<b>hack</b>"
    expense = await make(session, household, member, category)

    card = format_expense_card(expense)

    assert "&lt;b&gt;hack&lt;/b&gt;" in card
    assert "<b>hack</b>" not in card


async def test_saved_expense_confirmation(session, household, member, category):
    expense = await make(session, household, member, category)

    assert format_saved_expense(expense).startswith("✅ Записано:")


def test_report_with_data():
    report = Report(
        period_label="поточний тиждень (07.09–13.09.2026)",
        total=1000,
        by_category=[CategoryTotal("Їжа", 800, 80.0), CategoryTotal("Кава", 200, 20.0)],
        by_member=[MemberTotal("Сергій", 600), MemberTotal("Оля", 400)],
    )

    text = format_report(report)

    assert "поточний тиждень (07.09–13.09.2026)" in text
    assert "1\u00a0000\u00a0₴" in text
    assert "• Їжа — 800\u00a0₴ (80.0%)" in text
    assert "• Сергій — 600\u00a0₴" in text


def test_report_category_and_member_labels_are_html_escaped():
    report = Report(
        period_label="поточний рік (2026)",
        total=100,
        by_category=[CategoryTotal("<b>Їжа</b>", 100, 100.0)],
        by_member=[MemberTotal("<i>Сергій</i>", 100)],
    )

    text = format_report(report)

    assert "&lt;b&gt;Їжа&lt;/b&gt;" in text
    assert "<b>Їжа</b>" not in text
    assert "&lt;i&gt;Сергій&lt;/i&gt;" in text
    assert "<i>Сергій</i>" not in text


def test_empty_report_says_so_without_error():
    report = Report(period_label="поточний рік (2026)", total=0, by_category=[], by_member=[])

    text = format_report(report)

    assert "Витрат за цей період не знайдено" in text
    assert "%" not in text


def _progress(category_id, name, amount, spent, period=Period.MONTH):
    now = kyiv(2026, 10, 15)
    return LimitProgress(
        limit_id=1,
        period_type=period,
        category_id=category_id,
        category_name=name,
        amount=amount,
        spent=spent,
        period=period_range(period, now),
        day_index=15,
        days_in_period=31,
    )


def test_report_shows_one_time_and_limit_lines():
    report = Report(
        period_label="поточний місяць (жовтень 2026)",
        total=58400,
        by_category=[
            CategoryTotal("<b>Діти</b>", 19921, 34.1, one_time=16962, category_id=7),
            CategoryTotal("Їжа", 38479, 65.9, category_id=1),
        ],
        by_member=[MemberTotal("Сергій", 58400)],
        one_time_total=16962,
    )
    limits = [
        _progress(None, None, 50000, 41438),
        _progress(7, "<b>Діти</b>", 4000, 2959),
    ]

    text = format_report(report, limits)

    assert "Разом: <b>58 400 ₴</b> (з них разових 16 962 ₴)" in text
    assert "  ліміт 50 000 ₴ — використано 82% ⚠️" in text
    assert "• &lt;b&gt;Діти&lt;/b&gt; — 19 921 ₴ (34.1%)" in text
    assert "  з них разових: 16 962 ₴" in text
    assert "  ліміт 4 000 ₴ — використано 73%" in text  # 2959*100//4000 = 73
    assert text.count("ліміт") == 2  # Їжа has no limit


async def test_expense_line_marks_one_time(session, household, member, category):
    expense = await create_expense(
        session,
        household_id=household.id,
        member_id=member.id,
        category_id=category.id,
        amount=250,
        is_one_time=True,
        created_at=datetime(2026, 9, 7, 9, 0),
    )

    assert format_expense_line(expense) == "07.09 · 250 ₴ · Їжа · Сергій · разова"
