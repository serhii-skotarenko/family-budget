import os
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
