from budget_bot.formatting import EMPTY_LIMITS_TEXT, format_limit_alert, format_limits
from budget_bot.periods import Period, period_range
from budget_bot.services.limits import LimitProgress, period_days
from tests.conftest import kyiv

NOW = kyiv(2026, 10, 15, 12)


def progress(period, category_id, name, amount, spent):
    period_bounds = period_range(period, NOW)
    day_index, days = period_days(period_bounds, NOW)
    return LimitProgress(
        limit_id=1,
        period_type=period,
        category_id=category_id,
        category_name=name,
        amount=amount,
        spent=spent,
        period=period_bounds,
        day_index=day_index,
        days_in_period=days,
    )


def test_empty():
    assert format_limits([]) == EMPTY_LIMITS_TEXT


def test_month_and_week_sections():
    text = format_limits(
        [
            progress(Period.MONTH, None, None, 50000, 38000),
            progress(Period.MONTH, 1, "Їжа", 12000, 9800),
            progress(Period.WEEK, 2, "<b>Кава</b>", 1000, 1300),
        ]
    )

    assert "<b>Місяць (жовтень, день 15 з 31):</b>" in text
    # 38000*100//50000 = 76; forecast 38000/15*31 = 78533 > 50000 → ⚠️
    assert (
        "• Загальний: 38 000 ₴ / 50 000 ₴ — 76%, " "лишилось 12 000 ₴\n  прогноз: 78 533 ₴ ⚠️"
    ) in text
    # 9800*100//12000 = 81 → ⚠️ on the usage line
    assert "• Їжа: 9 800 ₴ / 12 000 ₴ — 81% ⚠️, лишилось 2 200 ₴" in text
    assert "<b>Тиждень (12.10–18.10, день 4 з 7):</b>" in text
    assert ("• &lt;b&gt;Кава&lt;/b&gt;: 1 300 ₴ / 1 000 ₴ — 130% 🔴 " "перевищено на 300 ₴") in text
    assert text.index("Місяць") < text.index("Тиждень")


def test_exactly_at_limit_says_exhausted():
    text = format_limits([progress(Period.WEEK, None, None, 1000, 1000)])

    assert "— 100% 🔴 ліміт вичерпано" in text


def test_zero_spending():
    text = format_limits([progress(Period.MONTH, None, None, 1000, 0)])

    assert "0 ₴ / 1 000 ₴ — 0%, лишилось 1 000 ₴\n  прогноз: 0 ₴" in text


def test_limit_alerts():
    warn = progress(Period.MONTH, 1, "<i>Їжа</i>", 12000, 9800)
    over = progress(Period.WEEK, None, None, 10000, 10400)

    assert format_limit_alert(warn) == (
        "⚠️ &lt;i&gt;Їжа&lt;/i&gt; (місяць): 9 800 ₴ / 12 000 ₴ — 81%"
    )
    assert format_limit_alert(over) == (
        "🔴 Загальний (тиждень): 10 400 ₴ / 10 000 ₴ — перевищено на 400 ₴"
    )
