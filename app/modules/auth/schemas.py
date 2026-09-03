"""Payloads for the auth routes."""

from __future__ import annotations

from pydantic import Field

from ...core.schema import APIModel


class LoginRequest(APIModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=256)


class UserOut(APIModel):
    id: str
    username: str
    display_name: str
    is_admin: bool


class AuthState(APIModel):
    """Answer to "who am I?".

    Always 200, including when nobody is signed in — the frontend asks this on
    every cold start, and a 401 there is indistinguishable from a session that
    has just run out, which is a different situation with a different
    recovery.
    """

    authenticated: bool
    user: UserOut | None = None
    #: Which mode the API is running in, so the frontend can skip the login
    #: screen entirely on a deployment with auth disabled.
    auth_mode: str
