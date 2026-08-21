"""User administration — the only way accounts are created or removed.

These drive `app.cli.main` the way the administrator does, rather than calling
the helpers underneath, because the point of the CLI is that a few ordinary
commands do the right thing.
"""

from __future__ import annotations

import io
import sys

import pytest

from sqlmodel import select

from app.cli import main as cli
from app.database import session_scope
from app.models import AuthSession, Song, SongRevision, User
from tests.conftest import PASSWORD

COOKIE = "songs_session"


def run(argv, password=None, monkeypatch=None):
    """Run a CLI command, feeding a password on stdin when one is asked for.

    A non-tty stdin is the CLI's own provisioning path, so this is the same
    route a setup script takes.
    """

    if password is not None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(password + "\n"))
    return cli(argv)


def test_add_creates_a_user_who_can_sign_in(client, monkeypatch):
    assert run(["user", "add", "petya", "--display-name", "Петя"], "a-long-password", monkeypatch) == 0

    response = client.post("/auth/login", json={"username": "petya", "password": "a-long-password"})
    assert response.status_code == 200
    assert response.json()["user"]["displayName"] == "Петя"


def test_the_username_is_stored_lowercased(monkeypatch):
    run(["user", "add", "PeTyA"], "a-long-password", monkeypatch)

    with session_scope() as session:
        assert session.exec(select(User)).one().username == "petya"


def test_the_display_name_defaults_to_the_login(monkeypatch):
    run(["user", "add", "petya"], "a-long-password", monkeypatch)

    with session_scope() as session:
        assert session.exec(select(User)).one().display_name == "petya"


def test_a_short_password_is_refused(monkeypatch):
    with pytest.raises(SystemExit):
        run(["user", "add", "petya"], "short", monkeypatch)

    with session_scope() as session:
        assert session.exec(select(User)).all() == []


def test_a_duplicate_login_is_refused(monkeypatch):
    run(["user", "add", "petya"], "a-long-password", monkeypatch)
    assert run(["user", "add", "petya"], "another-password", monkeypatch) == 1


def test_the_password_never_arrives_as_an_argument():
    """It would land in shell history and in the process list."""

    from app.cli import build_parser

    for action in build_parser()._actions:
        assert "password" not in (action.dest or "")


def test_disable_ends_every_session_immediately(signed_in, user, monkeypatch):
    assert signed_in.get("/setlists/setlist1").status_code == 200

    assert run(["user", "disable", user], None, monkeypatch) == 0

    assert signed_in.get("/setlists/setlist1").status_code == 401
    with session_scope() as session:
        assert session.exec(select(AuthSession)).all() == []


def test_disable_keeps_the_row_so_history_still_names_somebody(signed_in, user, monkeypatch):
    """Why `disable` and not `delete`: the edit history points at a name."""

    created = signed_in.post("/setlists/setlist1/songs/", json={"title": "Тест"})
    song_id = created.json()["id"]

    run(["user", "disable", user], None, monkeypatch)

    with session_scope() as session:
        account = session.exec(select(User)).one()
        assert account.is_active is False
        assert account.deactivated_at is not None

        # The attribution on the song and on its revisions is untouched by
        # the account losing access.
        assert session.get(Song, song_id).updated_by == "Вася"
        revisions = session.exec(select(SongRevision).where(SongRevision.song_id == song_id)).all()
        # Asserted separately so the comparison below cannot pass by being
        # empty if revision-keeping ever changes.
        assert revisions
        assert {r.updated_by for r in revisions} == {"Вася"}


def test_enable_restores_access(client, user, monkeypatch):
    run(["user", "disable", user], None, monkeypatch)
    assert client.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 401

    run(["user", "enable", user], None, monkeypatch)
    assert client.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 200


def test_changing_the_password_signs_every_device_out(signed_in, user, monkeypatch):
    assert run(["user", "passwd", user], "a-brand-new-password", monkeypatch) == 0

    assert signed_in.get("/setlists/setlist1").status_code == 401
    assert signed_in.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 401
    assert (
        signed_in.post(
            "/auth/login", json={"username": user, "password": "a-brand-new-password"}
        ).status_code
        == 200
    )


def test_logout_ends_sessions_without_touching_the_account(signed_in, user, monkeypatch):
    assert run(["user", "logout", user], None, monkeypatch) == 0

    assert signed_in.get("/setlists/setlist1").status_code == 401
    # Still able to sign back in — this is not deactivation.
    assert signed_in.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 200


def test_delete_removes_the_row(client, user, monkeypatch):
    assert run(["user", "delete", user, "--force"], None, monkeypatch) == 0

    with session_scope() as session:
        assert session.exec(select(User)).all() == []
    assert client.post("/auth/login", json={"username": user, "password": PASSWORD}).status_code == 401


def test_commands_against_a_missing_user_fail_cleanly(monkeypatch):
    for command in ("disable", "enable", "logout"):
        assert run(["user", command, "ghost"], None, monkeypatch) == 1


def test_list_runs_on_an_empty_database(capsys, monkeypatch):
    assert run(["user", "list"], None, monkeypatch) == 0
    assert "Пользователей нет" in capsys.readouterr().out
