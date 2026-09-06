"""Category list management for a household."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category

DEFAULT_CATEGORIES: tuple[str, ...] = (
    "Їжа",
    "Транспорт",
    "Комунальні",
    "Оренда житла",
    "Розваги",
    "Здоров'я",
    "Одяг",
    "Діти",
    "Інше",
)

MAX_NAME_LENGTH = 60


class CategoryNameError(ValueError):
    """Raised when a category name is empty or too long."""


class DuplicateCategoryError(ValueError):
    """Raised when a category with the same normalized name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Категорія «{name}» вже існує.")


def normalize_category_name(name: str) -> str:
    """Collapse whitespace and casefold.

    str.casefold() is used instead of SQL LOWER(): SQLite's LOWER() only
    handles ASCII, so 'ЇЖА' and 'їжа' would not collide in the database.
    """
    return " ".join(name.split()).casefold()


async def ensure_default_categories(session: AsyncSession, household_id: int) -> None:
    """Seed the nine default categories, but only if the household has none yet."""
    existing = await session.scalar(
        select(func.count()).select_from(Category).where(Category.household_id == household_id)
    )
    if existing:
        return
    session.add_all(
        [
            Category(
                household_id=household_id,
                name=name,
                name_normalized=normalize_category_name(name),
                is_custom=False,
            )
            for name in DEFAULT_CATEGORIES
        ]
    )
    try:
        await session.flush()
    except IntegrityError:
        # A concurrent call already seeded this household between our
        # existence check and this flush. Treat it as already done.
        await session.rollback()


async def list_categories(session: AsyncSession, household_id: int) -> list[Category]:
    """Defaults first (in canonical order), then custom ones by creation order."""
    result = await session.scalars(
        select(Category)
        .where(Category.household_id == household_id)
        .order_by(Category.is_custom, Category.id)
    )
    return list(result)


async def get_category(
    session: AsyncSession, household_id: int, category_id: int
) -> Category | None:
    return await session.scalar(
        select(Category).where(Category.id == category_id, Category.household_id == household_id)
    )


async def _find_by_normalized_name(
    session: AsyncSession, household_id: int, normalized: str
) -> Category | None:
    return await session.scalar(
        select(Category).where(
            Category.household_id == household_id, Category.name_normalized == normalized
        )
    )


async def add_category(session: AsyncSession, household_id: int, raw_name: str) -> Category:
    name = " ".join(raw_name.split())
    if not name:
        raise CategoryNameError("Назва категорії не може бути порожньою.")
    if len(name) > MAX_NAME_LENGTH:
        raise CategoryNameError(f"Назва задовга — максимум {MAX_NAME_LENGTH} символів.")

    normalized = normalize_category_name(name)
    duplicate = await _find_by_normalized_name(session, household_id, normalized)
    if duplicate is not None:
        raise DuplicateCategoryError(duplicate.name)

    category = Category(
        household_id=household_id, name=name, name_normalized=normalized, is_custom=True
    )
    session.add(category)
    try:
        await session.flush()
    except IntegrityError:
        # Another call inserted the same name between our check above and
        # this flush (e.g. both household members adding it at once).
        await session.rollback()
        existing = await _find_by_normalized_name(session, household_id, normalized)
        raise DuplicateCategoryError(existing.name if existing else name) from None
    return category
