"""Router composition. Order matters: /cancel must win over FSM state handlers."""

from aiogram import Router

from budget_bot.bot.handlers import categories, common


def build_router() -> Router:
    router = Router(name="root")
    router.include_routers(common.router, categories.router)
    return router
