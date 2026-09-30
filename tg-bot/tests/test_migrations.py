import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine

from budget_bot.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_matches_models(tmp_path):
    """The migration and the models must describe the same schema.

    Comparing full metadata (not just table names) so column/constraint
    drift between a model change and its migration is caught too.
    """
    db_path = tmp_path / "migrated.sqlite3"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)
    assert diff == []


def _alembic(db_path: Path, *args: str) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), *args],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_0002_keeps_existing_expenses_regular_and_downgrades_cleanly(tmp_path):
    db_path = tmp_path / "old.sqlite3"
    _alembic(db_path, "upgrade", "0001")
    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "INSERT INTO households (id, name, created_at) VALUES (1, 'Тест', '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO members (id, household_id, telegram_id, display_name, created_at) "
            "VALUES (1, 1, 111, 'Сергій', '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO categories (id, household_id, name, name_normalized, is_custom, "
            "created_at) VALUES (1, 1, 'Їжа', 'їжа', 0, '2026-09-01')"
        )
        connection.execute(
            "INSERT INTO expenses (household_id, member_id, category_id, amount, created_at) "
            "VALUES (1, 1, 1, 250, '2026-09-01 10:00:00')"
        )
    connection.close()

    _alembic(db_path, "upgrade", "head")
    connection = sqlite3.connect(db_path)
    assert connection.execute("SELECT amount, is_one_time FROM expenses").fetchall() == [(250, 0)]
    connection.close()

    _alembic(db_path, "downgrade", "0001")
    connection = sqlite3.connect(db_path)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(expenses)")]
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master")]
    amounts = connection.execute("SELECT amount FROM expenses").fetchall()
    connection.close()
    assert "is_one_time" not in columns
    assert "limits" not in tables
    assert amounts == [(250,)]
