"""Who may call what.

Everything is closed unless it is named here. The check is installed as an
application-wide dependency in main.py, so a route is protected by existing,
not by being wired to the right router — a new file under app/api/ is denied
by default until somebody opens it on purpose.

Opening a route means adding one line to `PUBLIC_ROUTES`. That is also the
answer to "what is reachable without signing in?": read this list, rather than
grepping decorators across every router.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from ...core.config import AuthMode, settings
from ...core.database import get_session
from .models import User
from .sessions import resolve_session

logger = logging.getLogger(__name__)

#: (method, route template) pairs reachable without a session. The template is
#: the one FastAPI registered — "/setlists/{setlist_slug}/songs", never a
#: filled-in path — so a setlist that happens to be called "health" cannot
#: match its way in.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/health"),
        # Signing in cannot itself require a session. `logout` and `me` are
        # open for the same reason: both have to be callable with a cookie
        # that has already stopped being valid — `me` is how the frontend
        # learns that, and `logout` still needs to clear it.
        ("POST", "/auth/login"),
        ("POST", "/auth/logout"),
        ("GET", "/auth/me"),
    }
)


def _route_key(request: Request) -> tuple[str, str | None]:
    # FastAPI puts the matched route in the ASGI scope before dependencies
    # run, so the template is available here without re-resolving the path.
    route = request.scope.get("route")
    return (request.method.upper(), getattr(route, "path_format", None))


def is_public(request: Request) -> bool:
    return _route_key(request) in PUBLIC_ROUTES


def enforce_auth(request: Request, session: Session = Depends(get_session)) -> None:
    """Application-wide gate. Attaches the user, refuses if one is required.

    The resolved user is left on `request.state` so that `current_user` and
    `require_user` are free: the session lookup happens once per request, not
    once per dependency that wants to know who is calling.
    """

    request.state.user = None

    if settings.auth_mode is AuthMode.DISABLED:
        return

    token = request.cookies.get(settings.session_cookie_name)
    request.state.user = resolve_session(session, token)

    if request.state.user is not None:
        return
    if settings.auth_mode is AuthMode.OPTIONAL:
        return
    if is_public(request):
        return

    raise _unauthorized(token_present=bool(token))


def _unauthorized(*, token_present: bool) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "message": "Требуется вход",
            # Lets the frontend tell "your session ran out" (keep the offline
            # cache, show a banner) apart from "you were never signed in"
            # (go to the login screen).
            "reason": "expired" if token_present else "anonymous",
        },
        # Deliberately no WWW-Authenticate header: it would make the browser
        # pop its own credential dialog, which is the thing this replaced.
    )


def current_user(request: Request) -> User | None:
    """The signed-in user, or None. Never refuses.

    For handlers that will serve anonymous callers once parts of the app go
    public.
    """

    return getattr(request.state, "user", None)


def require_user(request: Request) -> User:
    """The signed-in user, or 401.

    Use on anything that must have a real account behind it regardless of the
    mode the deployment runs in — writes, and later anything scoped to a band.
    """

    user = current_user(request)
    if user is None:
        raise _unauthorized(token_present=bool(request.cookies.get(settings.session_cookie_name)))
    return user


def log_startup_banner() -> None:
    """Say out loud when the deployment is not protecting itself."""

    if settings.auth_mode is AuthMode.REQUIRED:
        logger.info("Auth mode: required (%d public routes)", len(PUBLIC_ROUTES))
        return
    logger.warning(
        "=" * 62 + "\n"
        "  AUTH MODE: %s — the API is not fully protected.\n"
        "  Set SONGS_API_AUTH_MODE=required to close it.\n" + "=" * 62,
        settings.auth_mode.value.upper(),
    )
