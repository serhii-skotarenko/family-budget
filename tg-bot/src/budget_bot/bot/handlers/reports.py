"""/report: текстовий звіт за календарний тиждень / місяць / рік."""

from datetime import date

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
from budget_bot.periods import Period, period_range, to_kyiv
from budget_bot.services.income import cashflow, month_first
from budget_bot.services.limits import LIMIT_PERIODS, limit_progress
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
    now = utcnow()
    report_period = Period(callback_data.period)
    report = await build_report(session, member.household_id, period_range(report_period, now))
    limits = (
        await limit_progress(session, member.household_id, report_period, now)
        if report_period in LIMIT_PERIODS
        else []
    )
    this_month = month_first(to_kyiv(now).date())
    if report_period is Period.MONTH:
        cash = await cashflow(session, member.household_id, this_month, this_month, now)
    elif report_period is Period.YEAR:
        january = date(this_month.year, 1, 1)
        cash = await cashflow(session, member.household_id, january, this_month, now)
    else:
        cash = None
    await edit_or_answer(
        callback,
        format_report(report, limits, cash, note_income_start=report_period is Period.YEAR),
    )
    await callback.answer()
