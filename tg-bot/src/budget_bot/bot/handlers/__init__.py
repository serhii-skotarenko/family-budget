"""Router composition. Order matters: /cancel must win over FSM state handlers."""

from aiogram import Router

from budget_bot.bot.handlers import (
    add_expense,
    categories,
    common,
    expense_delete,
    expense_edit,
    expense_list,
    filters,
)


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(
        common.router,
        add_expense.router,
        categories.router,
        expense_list.router,
        filters.router,
        expense_edit.router,
        expense_delete.router,
    )
    return router
