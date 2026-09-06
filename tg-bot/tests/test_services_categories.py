import pytest

from budget_bot.services.categories import (
    DEFAULT_CATEGORIES,
    CategoryNameError,
    DuplicateCategoryError,
    add_category,
    ensure_default_categories,
    get_category,
    list_categories,
    normalize_category_name,
)


async def test_seeds_nine_default_categories_in_canonical_order(session, household):
    await ensure_default_categories(session, household.id)

    names = [category.name for category in await list_categories(session, household.id)]
    assert names == list(DEFAULT_CATEGORIES)
    assert len(names) == 9


async def test_seeding_is_idempotent(session, household):
    await ensure_default_categories(session, household.id)
    await ensure_default_categories(session, household.id)

    assert len(await list_categories(session, household.id)) == 9


async def test_custom_categories_come_after_defaults(session, household):
    await ensure_default_categories(session, household.id)
    await add_category(session, household.id, "Кава")

    categories = await list_categories(session, household.id)
    assert categories[-1].name == "Кава"
    assert categories[-1].is_custom is True
    assert categories[0].is_custom is False


async def test_rejects_case_insensitive_duplicate_of_default(session, household):
    await ensure_default_categories(session, household.id)

    with pytest.raises(DuplicateCategoryError) as exc_info:
        await add_category(session, household.id, "  їжа ")
    assert exc_info.value.name == "Їжа"


async def test_rejects_case_insensitive_duplicate_of_custom(session, household):
    await add_category(session, household.id, "Кава")

    with pytest.raises(DuplicateCategoryError):
        await add_category(session, household.id, "КАВА")


async def test_collapses_inner_whitespace(session, household):
    category = await add_category(session, household.id, "  Дитячий   садок ")
    assert category.name == "Дитячий садок"


@pytest.mark.parametrize("raw", ["", "   ", "x" * 61])
async def test_rejects_invalid_names(session, household, raw):
    with pytest.raises(CategoryNameError):
        await add_category(session, household.id, raw)


async def test_get_category_is_scoped_to_household(session, household):
    category = await add_category(session, household.id, "Кава")

    assert await get_category(session, household.id, category.id) is not None
    assert await get_category(session, household.id + 1, category.id) is None


def test_normalization_handles_cyrillic_case():
    assert normalize_category_name(" ЇЖА ") == normalize_category_name("їжа")
