"""Sign-in, sign-out, and "who am I".

There is no registration route and no user administration over HTTP. Accounts
are created with the CLI in app/cli.py — an endpoint that does not exist
cannot be brute-forced, and for a band-sized deployment the account list
changes a few times a year.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from ...core.config import settings
from ...core.database import get_session
from .models import User
from . import throttle
from .passwords import hash_password, needs_rehash, verify_password
from .policy import current_user
from .schemas import AuthState, LoginRequest, UserOut
from .sessions import (
    clear_session_cookie,
    create_session,
    resolve_session,
    revoke_session,
    set_session_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    # nginx sits in front, so the socket address is always the proxy. Trusting
    # this header is only safe because nothing but the proxy can reach the
    # port; if the API is ever exposed directly, a client can forge it and
    # sidestep the per-IP half of the throttle.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


@router.post("/login", response_model=AuthState)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthState:
    username = payload.username.strip().lower()
    ip = _client_ip(request)

    wait = throttle.retry_after(username, ip)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"message": "Слишком много попыток входа. Попробуйте позже.", "retryAfter": wait},
            headers={"Retry-After": str(wait)},
        )

    user = session.exec(select(User).where(User.username == username)).first()
    # `verify_password` hashes even when there is no user, so a wrong name and
    # a wrong password take the same time and answer the same way.
    ok = verify_password(payload.password, user.password_hash if user else None)

    if not ok or user is None or not user.is_active:
        throttle.record_failure(username, ip)
        logger.info("Failed login for %r from %s", username, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Неверный логин или пароль"},
        )

    throttle.record_success(username, ip)

    # Argon2's recommended parameters move over time. Re-hashing on a
    # successful login is the only moment the plaintext is available to do it.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        session.add(user)
        session.commit()
        session.refresh(user)

    token = create_session(session, user, request.headers.get("user-agent"))
    set_session_cookie(response, token)
    logger.info("Login: %s from %s", username, ip)

    return AuthState(
        authenticated=True,
        user=UserOut.model_validate(user),
        auth_mode=settings.auth_mode.value,
    )


@router.post("/logout", response_model=AuthState)
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthState:
    """Drop the session. Succeeds even when there was not one to drop.

    Calling this with a stale cookie must still clear it, so the frontend can
    always get itself back to a clean state.
    """

    revoke_session(session, request.cookies.get(settings.session_cookie_name))
    clear_session_cookie(response)
    return AuthState(authenticated=False, user=None, auth_mode=settings.auth_mode.value)


@router.get("/me", response_model=AuthState)
def me(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> AuthState:
    """Who is calling — 200 whether or not that is anybody.

    In `required` mode the global gate does not run for this route, so the
    cookie is resolved here instead.
    """

    user = current_user(request)
    if user is None:
        user = resolve_session(session, request.cookies.get(settings.session_cookie_name))

    if user is None:
        # The cookie either expired or names a session the server has dropped.
        # Clearing it stops the browser resending a token that can never work.
        clear_session_cookie(response)
        return AuthState(authenticated=False, user=None, auth_mode=settings.auth_mode.value)

    return AuthState(
        authenticated=True,
        user=UserOut.model_validate(user),
        auth_mode=settings.auth_mode.value,
    )
