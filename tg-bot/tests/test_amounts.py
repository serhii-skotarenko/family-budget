import pytest

from budget_bot.amounts import AmountError, format_amount, parse_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("100", 100),
        ("  250  ", 250),
        ("1 000", 1000),
        ("1\u00a0000", 1000),
        ("1", 1),
    ],
)
def test_parses_positive_integers(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "12.5", "12,5", "-5", "0", "١٢٣", "10000001", "1e3"],
)
def test_rejects_invalid_amounts(raw):
    with pytest.raises(AmountError):
        parse_amount(raw)


def test_format_amount_groups_thousands_with_nbsp():
    assert format_amount(12500) == "12\u00a0500\u00a0₴"
    assert format_amount(250) == "250\u00a0₴"
