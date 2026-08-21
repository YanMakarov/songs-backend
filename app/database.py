"""Database session management."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import settings
from .migrations import run_migrations


logger = logging.getLogger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=connect_args
                       )


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):  # pragma: no cover - driver hook
        """WAL lets readers run while a write is in flight.

        Every song write also bumps the setlist's rev counter, so writes now
        touch two rows in one transaction; the default rollback journal would
        make concurrent readers wait on that lock.
        """

        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def init_db() -> None:
    """Create missing tables, then bring existing ones up to date."""

    SQLModel.metadata.create_all(engine)
    applied = run_migrations(engine)
    for name in applied:
        logger.info("Applied migration %s", name)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
