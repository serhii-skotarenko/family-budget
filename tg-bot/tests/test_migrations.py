import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

from budget_bot.models import Base

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_head_matches_models(tmp_path):
    """The migration and the models must describe the same schema."""
    db_path = tmp_path / "migrated.sqlite3"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_PATH": str(db_path)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    inspector = inspect(create_engine(f"sqlite:///{db_path}"))
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
