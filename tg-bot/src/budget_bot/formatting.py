"""Rendering of user-facing messages. Output is Telegram HTML."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from html import escape

from budget_bot.amounts import format_amount
from budget_bot.models import Expense
from budget_bot.periods import (
    LIMIT_PERIOD_TITLES,
    MONTHS_UK,
    MONTHS_UK_GENITIVE,
    Period,
    format_date_short,
    format_datetime,
    to_kyiv,
)
from budget_bot.services.income import Cashflow
from budget_bot.services.limits import LIMIT_PERIODS, WARN_PERCENT, LimitProgress, LimitStatus
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
    if expense.is_one_time:
        parts.append("разова")
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
    if expense.is_one_time:
        lines.append("🔁 Разова витрата")
    if expense.updated_at is not None and expense.updated_by is not None:
        lines.append(
            "✏️ Змінив(ла): "
            f"{escape(expense.updated_by.display_name)}, {format_datetime(expense.updated_at)}"
        )
    return "\n".join(lines)


def format_saved_expense(expense: Expense) -> str:
    return f"✅ Записано: {format_expense_line(expense)}"


def _cashflow_lines(cash: Cashflow, note_income_start: bool) -> list[str]:
    free = cash.free
    free_text = format_amount(free) if free >= 0 else f"−{format_amount(-free)} 🔴"
    lines = [f"Дохід: {format_amount(cash.income)}", f"Вільний кешфлоу: {free_text}"]
    if note_income_start and cash.first_month.month != 1:
        lines.append(f"(дохід враховано з {MONTHS_UK_GENITIVE[cash.first_month.month - 1]})")
    return lines


def format_report(
    report: Report,
    limits: Sequence[LimitProgress] = (),
    cashflow: Cashflow | None = None,
    note_income_start: bool = False,
) -> str:
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
    if cashflow is not None:
        lines.extend(_cashflow_lines(cashflow, note_income_start))

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


EMPTY_LIMITS_TEXT = "Лімітів ще немає. Додати — /setlimit"


def _limits_section_title(progress: LimitProgress) -> str:
    first = to_kyiv(progress.period.start).date()
    day = f"день {progress.day_index} з {progress.days_in_period}"
    if progress.period_type is Period.MONTH:
        return f"<b>Місяць ({MONTHS_UK[first.month - 1]}, {day}):</b>"
    last = to_kyiv(progress.period.end).date() - timedelta(days=1)
    return f"<b>Тиждень ({first:%d.%m}–{last:%d.%m}, {day}):</b>"


def _limit_line(progress: LimitProgress) -> str:
    line = (
        f"• {escape(progress.name)}: {format_amount(progress.spent)} / "
        f"{format_amount(progress.amount)} — {progress.percent}%"
    )
    if progress.status is LimitStatus.OVER:
        over = progress.spent - progress.amount
        line += f" 🔴 перевищено на {format_amount(over)}" if over else " 🔴 ліміт вичерпано"
        return line
    if progress.percent >= WARN_PERCENT:
        line += " ⚠️"
    line += f", лишилось {format_amount(progress.remaining)}"
    forecast_icon = " ⚠️" if progress.forecast > progress.amount else ""
    return f"{line}\n  прогноз: {format_amount(progress.forecast)}{forecast_icon}"


def format_limits(progress: Sequence[LimitProgress]) -> str:
    if not progress:
        return EMPTY_LIMITS_TEXT
    lines = ["📊 <b>Ліміти</b>"]
    for period_type in LIMIT_PERIODS:
        items = [item for item in progress if item.period_type is period_type]
        if not items:
            continue
        lines.extend(["", _limits_section_title(items[0])])
        lines.extend(_limit_line(item) for item in items)
    return "\n".join(lines)


def format_limit_alert(progress: LimitProgress) -> str:
    head = (
        f"{escape(progress.name)} ({LIMIT_PERIOD_TITLES[progress.period_type]}): "
        f"{format_amount(progress.spent)} / {format_amount(progress.amount)} — "
    )
    if progress.status is LimitStatus.OVER:
        over = progress.spent - progress.amount
        return f"🔴 {head}" + (
            f"перевищено на {format_amount(over)}" if over else "ліміт вичерпано"
        )
    return f"⚠️ {head}{progress.percent}%"


def format_income_saved(amount: int, previous: int | None, now: datetime) -> str:
    text = f"✅ Дохід: <b>{format_amount(amount)}</b>/міс"
    if previous is not None:
        text += f" (було {format_amount(previous)})"
    local = to_kyiv(now)
    return f"{text}, діє з {MONTHS_UK_GENITIVE[local.month - 1]} {local.year}"
