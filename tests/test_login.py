"""Signing in, signing out, and what a session is worth."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from sqlmodel import select

from app.auth import throttle
from app.auth.sessions import hash_token
from app.config import settings
from app.database import session_scope
from app.models import AuthSession, User
from tests.conftest import PASSWORD

COOKIE = "songs_session"


def test_login_sets_a_cookie_and_returns_the_user(client, user):
    response = client.post("/auth/login", json={"username": user, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["displayName"] == "Вася"
    assert COOKIE in client.cookies


def test_username_is_case_insensitive(client, user):
    response = client.post("/auth/login", json={"username": "VaSyA", "password": PASSWORD})
    assert response.status_code == 200


def test_wrong_password_is_refused(client, user):
    response = client.post("/auth/login", json={"username": user, "password": "nope"})

    assert response.status_code == 401
    assert COOKIE not in client.cookies


def test_unknown_user_answers_exactly_like_a_wrong_password(client, user):
    """Otherwise the response tells an attacker which logins exist."""

    wrong_password = client.post("/auth/login", json={"username": user, "password": "nope"})
    no_such_user = client.post("/auth/login", json={"username": "ghost", "password": "nope"})

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json() == no_such_user.json()


def test_session_opens_the_protected_routes(signed_in):
    assert signed_in.get("/setlists/setlist1/songs/").status_code == 200


def test_logout_revokes_the_session(signed_in):
    assert signed_in.post("/auth/logout").status_code == 200
    assert signed_in.get("/setlists/setlist1/songs/").status_code == 401

    with session_scope() as session:
        assert session.exec(select(AuthSession)).all() == []


def test_logout_works_without_a_session(client):
    """The frontend has to be able to reach a clean state unconditionally."""

    assert client.post("/auth/logout").status_code == 200


def test_me_is_200_when_nobody_is_signed_in(client):
    """A 401 here could not be told apart from an expired session."""

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False


def test_me_reports_the_signed_in_user(signed_in):
    body = signed_in.get("/auth/me").json()

    assert body["authenticated"] is True
    assert body["user"]["username"] == "vasya"


def test_401_separates_an_expired_session_from_no_session(client, user):
    """The frontend keeps the offline cache for one and not the other."""

    anonymous = client.get("/setlists/setlist1")
    assert anonymous.json()["detail"]["reason"] == "anonymous"

    client.cookies.set(COOKIE, "a-token-the-server-has-never-seen")
    stale = client.get("/setlists/setlist1")
    assert stale.json()["detail"]["reason"] == "expired"


def test_no_www_authenticate_header(client):
    """It would make the browser open its own credential dialog."""

    assert "www-authenticate" not in {k.lower() for k in client.get("/setlists/setlist1").headers}


def test_the_raw_token_is_never_stored(signed_in):
    token = signed_in.cookies[COOKIE]

    with session_scope() as session:
        rows = session.exec(select(AuthSession)).all()
        assert len(rows) == 1
        assert rows[0].token_hash == hash_token(token)
        assert token not in rows[0].token_hash

    # And nowhere else in the file either — a leaked database must not be
    # replayable as a login.
    path = settings.database_url.removeprefix("sqlite:///")
    with sqlite3.connect(path) as db:
        dump = "\n".join(db.iterdump())
    assert token not in dump


def test_an_expired_session_is_refused_and_deleted(signed_in):
    with session_scope() as session:
        row = session.exec(select(AuthSession)).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        session.add(row)

    assert signed_in.get("/setlists/setlist1").status_code == 401

    with session_scope() as session:
        assert session.exec(select(AuthSession)).all() == []


def test_deactivating_a_user_takes_effect_on_the_next_request(signed_in):
    """Revocation must not wait for the session sweep to run."""

    with session_scope() as session:
        account = session.exec(select(User)).one()
        account.is_active = False
        session.add(account)

    assert signed_in.get("/setlists/setlist1").status_code == 401


def test_the_author_of_a_write_comes_from_the_session(signed_in):
    """A forged attribution header must not outrank the signed-in account."""

    response = signed_in.post(
        "/setlists/setlist1/songs/",
        json={"title": "Тест"},
        # "Хакер", percent-encoded — header values cannot carry Cyrillic raw.
        headers={"X-Client-Name": "%D0%A5%D0%B0%D0%BA%D0%B5%D1%80"},
    )

    assert response.status_code == 201
    assert response.json()["updatedBy"] == "Вася"


def test_repeated_failures_lock_the_account_out(client, user):
    codes = [
        client.post("/auth/login", json={"username": user, "password": "nope"}).status_code
        for _ in range(9)
    ]

    assert codes[: throttle.FREE_ATTEMPTS] == [401] * throttle.FREE_ATTEMPTS
    assert codes[-1] == 429


def test_the_lockout_holds_even_for_the_right_password(client, user):
    for _ in range(9):
        client.post("/auth/login", json={"username": user, "password": "nope"})

    blocked = client.post("/auth/login", json={"username": user, "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"]

    throttle.reset()
    assert client.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 200


def test_a_successful_login_clears_the_failure_count(client, user):
    for _ in range(throttle.FREE_ATTEMPTS - 1):
        client.post("/auth/login", json={"username": user, "password": "nope"})

    assert client.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 200
    assert throttle.retry_after(user, "testclient") == 0
