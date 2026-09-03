"""The access policy: what is closed, what is open, and who decides."""

from __future__ import annotations

import pytest

from app.modules.auth.policy import PUBLIC_ROUTES
from app.core.config import AuthMode, settings

# Endpoints that must never answer without a session. One per router, so a new
# router wired up without thinking shows up as a failure here rather than as
# an open door.
PROTECTED = [
    ("GET", "/setlists/setlist1"),
    ("GET", "/setlists/setlist1/songs/"),
    ("GET", "/setlists/setlist1/changes?since=0"),
    ("GET", "/movable-shapes/"),
]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_denied_without_session(client, method, path):
    assert client.request(method, path).status_code == 401


def test_health_is_public_and_reports_the_mode(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "auth": "required"}


def test_public_list_is_only_auth_routes_and_health():
    """The list is the whole security boundary, so changing it is deliberate.

    A new entry here means something became reachable without signing in. If
    that is intended, update this test in the same commit.
    """

    assert PUBLIC_ROUTES == frozenset(
        {
            ("GET", "/health"),
            ("POST", "/auth/login"),
            ("POST", "/auth/logout"),
            ("GET", "/auth/me"),
        }
    )


def test_every_route_is_closed_unless_listed(client):
    """Walks the actual routing table rather than a hand-written list.

    This is the test that catches the router somebody adds next year: it
    fails the moment a new endpoint answers without a session and nobody put
    it in `PUBLIC_ROUTES`.
    """

    from app.main import app as fastapi_app

    checked = 0
    for route in fastapi_app.routes:
        path = getattr(route, "path_format", None)
        methods = getattr(route, "methods", None) or set()
        if not path or "{" in path:
            # Parameterised paths need a real id to reach the handler; the
            # cases above cover them with a live setlist.
            continue
        for method in methods & {"GET", "POST", "PATCH", "DELETE"}:
            if (method, path) in PUBLIC_ROUTES:
                continue
            response = client.request(method, path)
            assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
            checked += 1
    assert checked > 0


def test_docs_are_not_published_in_required_mode(client):
    # Global dependencies do not cover FastAPI's own doc routes, so `main.py`
    # removes them instead. Without that they stay reachable with everything
    # else closed.
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404


def test_optional_mode_never_refuses(client):
    settings.auth_mode = AuthMode.OPTIONAL
    assert client.get("/setlists/setlist1/songs/").status_code == 200


def test_disabled_mode_never_refuses(client):
    settings.auth_mode = AuthMode.DISABLED
    assert client.get("/setlists/setlist1/songs/").status_code == 200
    assert client.get("/health").json()["auth"] == "disabled"


def test_setlist_named_health_does_not_slip_through(client):
    """The policy matches route templates, not filled-in paths.

    Matching on the concrete path would let a setlist slug collide with a
    public entry; matching on "/setlists/{setlist_slug}" cannot.
    """

    assert client.get("/setlists/health").status_code == 401
