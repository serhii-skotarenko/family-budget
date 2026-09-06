import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from budget_bot.models import Category, Household
from budget_bot.services.categories import (
    CategoryNameError,
    DuplicateCategoryError,
    add_category,
    ensure_default_categories,
    get_category,
    list_categories,
    normalize_category_name,
)

# Independently spelled out (not imported from the module under test), so a
# future accidental edit to DEFAULT_CATEGORIES (reorder, wrong apostrophe,
# typo) fails this test instead of passing silently.
EXPECTED_DEFAULT_CATEGORIES = (
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


async def test_seeds_nine_default_categories_in_canonical_order(session, household):
    await ensure_default_categories(session, household.id)

    names = [category.name for category in await list_categories(session, household.id)]
    assert names == list(EXPECTED_DEFAULT_CATEGORIES)
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


async def test_add_category_converts_concurrent_duplicate_insert_error(
    session, household, monkeypatch
):
    """A duplicate that only appears between the pre-check and the flush (a
    race between two household members adding the same category at once)
    must still surface as DuplicateCategoryError, not a raw IntegrityError."""
    household_id = household.id
    winner = await add_category(session, household_id, "Кава")
    winner_id, winner_name = winner.id, winner.name
    # Committed, like a concurrent request's own transaction would be, so it
    # survives the rollback that the caught IntegrityError triggers below.
    # (That rollback also expires every object in the session, so capture
    # the plain values needed later above, before it happens.)
    await session.commit()

    real_scalar = AsyncSession.scalar
    call_count = 0

    async def racy_scalar(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate the pre-check missing the row a concurrent transaction
            # just committed.
            return None
        return await real_scalar(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", racy_scalar)

    with pytest.raises(DuplicateCategoryError) as exc_info:
        await add_category(session, household_id, "кава")
    assert exc_info.value.name == winner_name

    # The session must still be usable after the rollback triggered by the
    # caught IntegrityError.
    monkeypatch.undo()
    assert await get_category(session, household_id, winner_id) is not None


async def test_ensure_default_categories_survives_concurrent_seeding(
    session, household, monkeypatch
):
    """If two calls race for a brand-new household, the loser must end up
    idempotent (no exception), not fail with a raw IntegrityError."""
    household_id = household.id
    already_seeded = Category(
        household_id=household_id,
        name=EXPECTED_DEFAULT_CATEGORIES[0],
        name_normalized=normalize_category_name(EXPECTED_DEFAULT_CATEGORIES[0]),
        is_custom=False,
    )
    session.add(already_seeded)
    # Committed, like a concurrent call's own transaction would be, so it
    # survives the rollback that the caught IntegrityError triggers below.
    # (That rollback also expires every object in the session, so capture
    # household_id above, before it happens.)
    await session.commit()

    async def racy_scalar(self, *args, **kwargs):
        # Simulate the "household has no categories yet" check missing the
        # row a concurrent call just committed.
        return 0

    monkeypatch.setattr(AsyncSession, "scalar", racy_scalar)

    await ensure_default_categories(session, household_id)

    monkeypatch.undo()
    categories = await list_categories(session, household_id)
    assert len(categories) == 1
    assert categories[0].name == EXPECTED_DEFAULT_CATEGORIES[0]


async def test_race_recovery_preserves_other_uncommitted_work_in_session(
    session, household, monkeypatch
):
    """The duplicate-race recovery must be scoped to the failed insert (a
    SAVEPOINT), not roll back the whole transaction. This bot opens one
    session per Telegram update and commits once at the end, so anything
    else already flushed-but-not-committed earlier in that same session
    (e.g. a brand-new Household created moments before this handler ran)
    must survive a duplicate-category error untouched, with its attributes
    still readable without triggering a refresh."""
    await add_category(session, household.id, "Кава")

    # Work flushed earlier in the same session, not yet committed — this is
    # the shape of a first-ever Telegram update, where Household/Member rows
    # are flushed before any category handling runs.
    pending = Household(name="В процесі")
    session.add(pending)
    await session.flush()

    real_scalar = AsyncSession.scalar
    call_count = 0

    async def racy_scalar(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate the pre-check missing the row a concurrent transaction
            # just committed.
            return None
        return await real_scalar(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", racy_scalar)

    with pytest.raises(DuplicateCategoryError):
        await add_category(session, household.id, "кава")

    monkeypatch.undo()

    # Still pending (not discarded), and its attributes are readable without
    # a refresh — i.e. it was never expired by the recovery.
    assert pending.name == "В процесі"
    assert await session.get(Household, pending.id) is not None
