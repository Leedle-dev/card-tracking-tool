"""SQLAlchemy session helpers.

Example:
    from card_tracker.db import session_scope
    from card_tracker.db.models import Card

    with session_scope() as session:
        cards = session.query(Card).filter(Card.name.ilike("%Houndoom%")).all()
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "card_tracker.sqlite"


def sqlite_url(db_path: str | Path = DEFAULT_DB_PATH) -> str:
    """Return a SQLAlchemy SQLite URL for a local database path."""

    return f"sqlite:///{Path(db_path).resolve().as_posix()}"


def create_sqlite_engine(db_path: str | Path = DEFAULT_DB_PATH, echo: bool = False) -> Engine:
    """Create an engine for the local SQLite database.

    Example:
        engine = create_sqlite_engine("data/card_tracker.sqlite", echo=True)
    """

    engine = create_engine(sqlite_url(db_path), echo=echo, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def create_session_factory(engine: Engine | None = None, db_path: str | Path = DEFAULT_DB_PATH) -> sessionmaker[Session]:
    """Create a session factory for scripts that need multiple sessions."""

    return sessionmaker(bind=engine or create_sqlite_engine(db_path), autoflush=False, future=True)


@contextmanager
def session_scope(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[Session]:
    """Open a session, commit on success, and roll back on error."""

    session_factory = create_session_factory(db_path=db_path)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
