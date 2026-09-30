"""Rendering of user-facing messages. Output is Telegram HTML."""

from collections.abc import Sequence
from html import escape

from budget_bot.amounts import format_amount
from budget_bot.models import Expense
from budget_bot.periods import LIMIT_PERIOD_TITLES, Period, format_date_short, format_datetime
from budget_bot.services.limits import LimitProgress, LimitStatus
from budget_bot.services.reports import Report

STATUS_ICONS = {LimitStatus.OK: "", LimitStatus.WARN: " ⚠️", LimitStatus.OVER: " 🔴"}


def _limit_usage_line(progress: LimitProgress) -> str:
    return (
        f"  ліміт {format_amount(progress.amount)} — використано {progress.percent}%"
        f"{STATUS_ICONS[progress.status]}"
    )


def format_expense_line(expense: Expense, index: int | None = None) -> str:
    parts = [
        format_date_short(expense.created_at),
        format_amount(expense.amount),
        escape(expense.category.name),
        escape(expense.author.display_name),
    ]
    line = " · ".join(parts)
    if expense.description:
        line += f" — {escape(expense.description)}"
    if index is not None:
        line = f"<b>{index}.</b> {line}"
    return line


def format_expense_list(expenses: Sequence[Expense], header: str, empty_message: str) -> str:
    if not expenses:
        return empty_message
    lines = [f"<b>{escape(header)}</b>", ""]
    lines.extend(
        format_expense_line(expense, index=number)
        for number, expense in enumerate(expenses, start=1)
    )
    return "\n".join(lines)


def format_expense_card(expense: Expense) -> str:
    lines = [
        f"🧾 <b>Витрата #{expense.id}</b>",
        f"Сума: <b>{format_amount(expense.amount)}</b>",
        f"Категорія: {escape(expense.category.name)}",
        f"Автор: {escape(expense.author.display_name)}",
        f"Дата: {format_datetime(expense.created_at)}",
    ]
    if expense.description:
        lines.append(f"Опис: {escape(expense.description)}")
    if expense.updated_at is not None and expense.updated_by is not None:
        lines.append(
            "✏️ Змінив(ла): "
            f"{escape(expense.updated_by.display_name)}, {format_datetime(expense.updated_at)}"
        )
    return "\n".join(lines)


def format_saved_expense(expense: Expense) -> str:
    return f"✅ Записано: {format_expense_line(expense)}"


def format_report(report: Report, limits: Sequence[LimitProgress] = ()) -> str:
    header = f"📊 <b>Звіт — {escape(report.period_label)}</b>"
    if report.total == 0:
        return f"{header}\n\nВитрат за цей період не знайдено."

    limit_by_category = {progress.category_id: progress for progress in limits}
    total_line = f"Разом: <b>{format_amount(report.total)}</b>"
    if report.one_time_total:
        total_line += f" (з них разових {format_amount(report.one_time_total)})"
    lines = [header, total_line]
    if None in limit_by_category:
        lines.append(_limit_usage_line(limit_by_category[None]))

    lines.extend(["", "<b>За категоріями:</b>"])
    for item in report.by_category:
        lines.append(f"• {escape(item.name)} — {format_amount(item.amount)} ({item.share:.1f}%)")
        if item.one_time:
            lines.append(f"  з них разових: {format_amount(item.one_time)}")
        if item.category_id is not None and item.category_id in limit_by_category:
            lines.append(_limit_usage_line(limit_by_category[item.category_id]))

    lines.extend(["", "<b>За учасниками:</b>"])
    lines.extend(
        f"• {escape(item.display_name)} — {format_amount(item.amount)}" for item in report.by_member
    )
    return "\n".join(lines)


def format_limit_saved(period_type: Period, name: str, amount: int, previous: int | None) -> str:
    text = (
        f"✅ Ліміт на {LIMIT_PERIOD_TITLES[period_type]} · {escape(name)}: "
        f"<b>{format_amount(amount)}</b>"
    )
    if previous is not None:
        text += f" (було {format_amount(previous)})"
    return text
