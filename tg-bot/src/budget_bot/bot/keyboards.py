"""Keyboard builders. Button labels are constants so handlers can match on them."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from budget_bot.bot.callbacks import CategoryCb, EditFieldCb, ExpenseCb, FilterCb, FlowCb, ReportCb
from budget_bot.models import Category, Expense, Member
from budget_bot.periods import PERIOD_TITLES, Period

BTN_ADD = "➕ Витрата"
BTN_LIST = "📋 Список"
BTN_REPORT = "📊 Звіт"
BTN_FILTER = "🔎 Фільтр"
BTN_CATEGORIES = "🏷 Категорії"


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_ADD)
    builder.button(text=BTN_LIST)
    builder.button(text=BTN_REPORT)
    builder.button(text=BTN_FILTER)
    builder.button(text=BTN_CATEGORIES)
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    return builder.as_markup()


def add_category_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати категорію", callback_data=FlowCb(action="add_category"))
    return builder.as_markup()


def categories_keyboard(
    categories: Sequence[Category], action: str = "pick"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in categories:
        builder.button(text=item.name, callback_data=CategoryCb(action=action, category_id=item.id))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def description_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустити", callback_data=FlowCb(action="skip"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Зберегти", callback_data=FlowCb(action="save"))
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


def expense_index_keyboard(expenses: Sequence[Expense]) -> InlineKeyboardMarkup:
    """One numbered button per listed row — the shortcut into the expense card."""
    builder = InlineKeyboardBuilder()
    for number, expense in enumerate(expenses, start=1):
        builder.button(
            text=str(number), callback_data=ExpenseCb(action="view", expense_id=expense.id)
        )
    builder.adjust(5)
    return builder.as_markup()


def expense_card_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✏️ Редагувати", callback_data=ExpenseCb(action="edit", expense_id=expense_id)
    )
    builder.button(
        text="🗑 Видалити", callback_data=ExpenseCb(action="delete", expense_id=expense_id)
    )
    builder.adjust(2)
    return builder.as_markup()


def delete_confirm_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🗑 Так, видалити",
        callback_data=ExpenseCb(action="delete_yes", expense_id=expense_id),
    )
    builder.button(text="↩️ Ні", callback_data=ExpenseCb(action="view", expense_id=expense_id))
    builder.adjust(2)
    return builder.as_markup()


def edit_fields_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Сума", callback_data=EditFieldCb(field="amount", expense_id=expense_id))
    builder.button(
        text="🏷 Категорія", callback_data=EditFieldCb(field="category", expense_id=expense_id)
    )
    builder.button(
        text="📝 Опис", callback_data=EditFieldCb(field="description", expense_id=expense_id)
    )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(3, 1)
    return builder.as_markup()


def filter_periods_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in (Period.TODAY, Period.WEEK, Period.MONTH):
        builder.button(
            text=PERIOD_TITLES[period],
            callback_data=FilterCb(step="period", value=period.value),
        )
    builder.button(
        text="📅 Довільний період", callback_data=FilterCb(step="period", value="custom")
    )
    builder.button(text="❌ Скасувати", callback_data=FlowCb(action="cancel"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def filter_categories_keyboard(categories: Sequence[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Усі категорії", callback_data=FilterCb(step="category", value="all"))
    for item in categories:
        builder.button(text=item.name, callback_data=FilterCb(step="category", value=str(item.id)))
    builder.adjust(1, 2)
    return builder.as_markup()


def filter_members_keyboard(members: Sequence[Member]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Усі учасники", callback_data=FilterCb(step="member", value="all"))
    for item in members:
        builder.button(
            text=item.display_name, callback_data=FilterCb(step="member", value=str(item.id))
        )
    builder.adjust(1, 2)
    return builder.as_markup()


def report_periods_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for period in (Period.WEEK, Period.MONTH, Period.YEAR):
        builder.button(text=PERIOD_TITLES[period], callback_data=ReportCb(period=period.value))
    builder.adjust(1)
    return builder.as_markup()
