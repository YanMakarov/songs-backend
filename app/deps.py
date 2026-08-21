"""Shared FastAPI dependencies."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import Header

MAX_NAME_LENGTH = 60


def get_author(
    x_client_name: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
) -> str | None:
    """Display name to record as the author of a write.

    Attribution for the interface, not an authorisation check: both headers are
    client-supplied and trivially forgeable. When real sign-in arrives this
    dependency starts reading the session instead and nothing else changes.

    The name arrives percent-encoded. HTTP header values are latin-1 at best,
    and `fetch` throws outright on a non-ISO-8859-1 value — so "Вася" cannot be
    sent raw. Clients encode with `encodeURIComponent`; a name that happens to
    be plain ASCII survives that round trip unchanged, so an un-encoded legacy
    client still works.

    Falls back to a short form of the client id, so an unnamed browser is still
    distinguishable from another one.
    """

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
