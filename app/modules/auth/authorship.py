"""Who to record as the author of a write.

Lives in auth because that is where the answer comes from, and is published
from this module's `__init__.py` so the songs routes can depend on "the
current author" without depending on how sessions work.
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import Header, Request

from .policy import current_user

MAX_NAME_LENGTH = 60


def get_author(
    request: Request,
    x_client_name: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> str | None:
    """Display name to record as the author of a write.

    Now taken from the session: `Song.updated_by` stays a display name, so
    sign-in changed where the name comes from and nothing about how it is
    stored — old rows and old revisions read exactly as before.

    The header path below survives for the one case that has no session:
    running with `SONGS_API_AUTH_MODE=disabled` locally. It is attribution for
    the interface and nothing more — the headers are client-supplied and
    trivially forgeable, which is precisely why they no longer decide anything
    once auth is on.

    The name arrives percent-encoded. HTTP header values are latin-1 at best,
    and `fetch` throws outright on a non-ISO-8859-1 value — so "Вася" cannot be
    sent raw. Clients encode with `encodeURIComponent`; a name that happens to
    be plain ASCII survives that round trip unchanged, so an un-encoded legacy
    client still works.

    Falls back to a short form of the client id, so an unnamed browser is still
    distinguishable from another one.
    """

    user = current_user(request)
    if user is not None:
        return user.display_name[:MAX_NAME_LENGTH]

    name = _decode(x_client_name)
    if name:
        return name[:MAX_NAME_LENGTH]
    client_id = (x_client_id or "").strip()
    if client_id:
        return f"anon-{client_id[:8]}"
    return None


def _decode(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return unquote(raw, errors="strict").strip()
    except UnicodeDecodeError:
        # Not valid percent-encoded UTF-8 — keep whatever was sent rather than
        # dropping the attribution entirely.
        return raw.strip()
