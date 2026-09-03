"""Fixtures for the auth suite.

Two things have to happen before `app` is imported at all: `DATABASE_URL` has
to point somewhere disposable, and `SONGS_API_AUTH_MODE` has to be the mode
the app was built for. `app.config.settings` is a module-level object read at
import time, and `app.database.engine` is created from it — so setting these
afterwards would be too late.

The mode is then varied per test by assigning to `settings.auth_mode`, which
`enforce_auth` re-reads on every request. The one thing that cannot be changed
after import is whether the docs routes exist, since `main.py` decides that
while building the app.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="songs-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["SONGS_API_AUTH_MODE"] = "required"
os.environ["SONGS_API_SESSION_COOKIE_SECURE"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.modules.auth import throttle  # noqa: E402
from app.modules.auth.passwords import hash_password  # noqa: E402
from app.core.config import AuthMode, settings  # noqa: E402
from sqlmodel import select  # noqa: E402

from app.core.database import session_scope  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.auth.models import AuthSession, User  # noqa: E402
from app.modules.songs.models import Song, SongRevision  # noqa: E402
from app.tables import init_database  # noqa: E402

PASSWORD = "correct-horse-battery"

# Created once, here, rather than as a side effect of the `client` fixture
# starting the app: a module that only tests pure functions still gets the
# autouse cleanup below, and that cleanup queries these tables.
init_database()


@pytest.fixture(autouse=True)
def clean_state():
    """Every test starts with no users, no sessions and no lockouts."""

    throttle.reset()
    settings.auth_mode = AuthMode.REQUIRED
    yield
    with session_scope() as session:
        # Children before parents: foreign keys are enforced (see the PRAGMA
        # in database.py), so sessions go before users and revisions before
        # songs. The setlist stays — startup recreates it, and every test
        # addresses it by slug.
        for model in (AuthSession, User, SongRevision, Song):
            for row in session.exec(select(model)).all():
                session.delete(row)
    throttle.reset()


@pytest.fixture
def client():
    # As a context manager so startup runs and the default setlist exists.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def user():
    """An active account. Returns its username."""

    with session_scope() as session:
        session.add(
            User(
                username="vasya",
                password_hash=hash_password(PASSWORD),
                display_name="Вася",
            )
        )
    return "vasya"


@pytest.fixture
def signed_in(client, user):
    """A client with a live session cookie."""

    response = client.post("/auth/login", json={"username": user, "password": PASSWORD})
    assert response.status_code == 200
    return client
