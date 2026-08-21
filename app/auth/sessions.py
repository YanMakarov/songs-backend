"""Creating, resolving and revoking sessions."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Response
from sqlmodel import Session, select

from ..config import settings
from ..models import AuthSession, User

#: 32 bytes of entropy, url-safe. Long enough that guessing is not a strategy
#: and short enough to sit in a cookie without thought.
_TOKEN_BYTES = 32

#: A session is only written back to when it has not been seen for this long.
#: Without it every GET would become a write, and on SQLite that means every
#: read takes the write lock.
_TOUCH_INTERVAL = timedelta(days=1)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(session: Session, user: User, user_agent: str | None = None) -> str:
    """Open a session for `user` and return the token to put in the cookie.

    The token is returned, never stored: the row keeps only its SHA-256, so a
    copy of the database cannot be turned back into a login.
    """

    token = secrets.token_urlsafe(_TOKEN_BYTES)
    now = datetime.utcnow()
    row = AuthSession(
        token_hash=hash_token(token),
        user_id=user.id,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_ttl_days),
        user_agent=(user_agent or "")[:200] or None,
    )
    session.add(row)
    session.commit()
    return token


def resolve_session(session: Session, token: str | None) -> User | None:
    """Return the signed-in user for a cookie value, or None.

    Expired rows are deleted on the way past, which keeps the table tidy
    without a scheduled job. A user who has been deactivated resolves to None
    even while their row is still there, so revoking access does not depend on
    the session sweep having run.
    """

    if not token:
        return None

    row = session.get(AuthSession, hash_token(token))
    if row is None:
        return None

    now = datetime.utcnow()
    if row.expires_at <= now:
        session.delete(row)
        session.commit()
        return None

    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        session.delete(row)
        session.commit()
        return None

    if now - row.last_seen_at > _TOUCH_INTERVAL:
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=settings.session_ttl_days)
        session.add(row)
        session.commit()

    return user


def revoke_session(session: Session, token: str | None) -> None:
    if not token:
        return
    row = session.get(AuthSession, hash_token(token))
    if row is not None:
        session.delete(row)
        session.commit()


def revoke_all_for_user(session: Session, user_id: str) -> int:
    """Sign a user out everywhere. Returns how many sessions were dropped."""

    rows = session.exec(select(AuthSession).where(AuthSession.user_id == user_id)).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)


def purge_expired(session: Session) -> int:
    rows = session.exec(
        select(AuthSession).where(AuthSession.expires_at <= datetime.utcnow())
    ).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_days * 24 * 60 * 60,
        # No `domain`: the cookie is only ever sent to the API host. The
        # frontend never reads it — it is HttpOnly — so scoping it wider would
        # only widen where it can leak.
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )


def clear_session_cookie(response: Response) -> None:
    # The attributes must match the ones the cookie was set with, or the
    # browser treats it as a different cookie and keeps the original.
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
    )
