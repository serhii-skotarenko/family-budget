"""Parsing and rendering of hryvnia amounts. Whole UAH only, no kopiykas."""

import re

MAX_AMOUNT = 10_000_000

_DIGITS = re.compile(r"\d+", re.ASCII)
_SEPARATORS = str.maketrans({" ": "", "\u00a0": "", "\u202f": "", "'": ""})


class AmountError(ValueError):
    """Raised when user input is not a valid whole-hryvnia amount."""


def parse_amount(raw: str) -> int:
    cleaned = raw.strip().translate(_SEPARATORS)
    if not _DIGITS.fullmatch(cleaned):
        raise AmountError("Сума має бути цілим числом гривень, наприклад: 250")
    value = int(cleaned)
    if value <= 0:
        raise AmountError("Сума має бути більшою за нуль.")
    if value > MAX_AMOUNT:
        raise AmountError(f"Сума завелика. Максимум — {format_amount(MAX_AMOUNT)}.")
    return value


def format_amount(value: int) -> str:
    return f"{value:,}".replace(",", "\u00a0") + "\u00a0₴"
