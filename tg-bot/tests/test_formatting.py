from datetime import datetime

from budget_bot.formatting import (
    format_expense_card,
    format_expense_line,
    format_expense_list,
    format_report,
    format_saved_expense,
)
from budget_bot.services.expenses import create_expense, update_expense
from budget_bot.services.reports import CategoryTotal, MemberTotal, Report

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
