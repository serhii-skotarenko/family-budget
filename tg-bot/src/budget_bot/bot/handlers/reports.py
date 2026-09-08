"""/report: текстовий звіт за календарний тиждень / місяць / рік."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.bot.callbacks import ReportCb
from budget_bot.bot.keyboards import BTN_REPORT, report_periods_keyboard
from budget_bot.bot.replies import edit_or_answer
from budget_bot.clock import utcnow
from budget_bot.formatting import format_report
from budget_bot.models import Member
from budget_bot.periods import Period, period_range
from budget_bot.services.reports import build_report

router = Router(name="reports")


@router.message(Command("report"))
@router.message(F.text == BTN_REPORT)
async def cmd_report(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Оберіть період звіту:", reply_markup=report_periods_keyboard())


@router.callback_query(ReportCb.filter())
async def cb_report(
    callback: CallbackQuery,
    callback_data: ReportCb,
    session: AsyncSession,
    member: Member,
) -> None:
    period = period_range(Period(callback_data.period), utcnow())
    report = await build_report(session, member.household_id, period)
    await edit_or_answer(callback, format_report(report))
    await callback.answer()
