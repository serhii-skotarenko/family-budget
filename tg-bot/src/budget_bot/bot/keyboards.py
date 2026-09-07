"""Keyboard builders. Button labels are constants so handlers can match on them."""

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from budget_bot.bot.callbacks import FlowCb

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
