"""Single source of 'now' for the whole app.

Everything stored in SQLite is UTC-naive: SQLite has no timezone type and the
SQLAlchemy SQLite dialect silently drops tzinfo, so we drop it explicitly.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
