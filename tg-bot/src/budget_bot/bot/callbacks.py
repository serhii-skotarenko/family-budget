"""Typed callback-data factories shared by keyboards and handlers."""

from aiogram.filters.callback_data import CallbackData


class CategoryCb(CallbackData, prefix="cat"):
    action: str  # "pick" | "filter" | "edit"
    category_id: int


class ExpenseCb(CallbackData, prefix="exp"):
    action: str  # "view" | "edit" | "delete" | "delete_yes" | "back"
    expense_id: int


class EditFieldCb(CallbackData, prefix="edit"):
    field: str  # "amount" | "category" | "description"
    expense_id: int


class ReportCb(CallbackData, prefix="rep"):
    period: str  # a budget_bot.periods.Period value


class FilterCb(CallbackData, prefix="flt"):
    step: str  # "period" | "category" | "member" | "apply"
    value: str


class FlowCb(CallbackData, prefix="flow"):
    action: str  # "cancel" | "skip" | "save" | "add_category" | "toggle_one_time"


class LimitCb(CallbackData, prefix="lim"):
    action: str  # "period" | "category" | "add" | "edit" | "delete" | "delete_yes"
    period_type: str = ""  # a budget_bot.periods.Period value (week | month)
    category_id: int = 0  # 0 = the household-wide limit
