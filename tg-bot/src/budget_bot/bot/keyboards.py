"""Keyboard builders. Button labels are constants so handlers can match on them."""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from budget_bot.bot.callbacks import CategoryCb, FlowCb
from budget_bot.models import Category

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
