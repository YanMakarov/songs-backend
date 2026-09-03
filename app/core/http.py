"""ETag / If-Match plumbing.

One number does both jobs: a row's `rev` is the entity tag *and* the
precondition for writes. Everything here is about being lenient with the wire
format so a client can hand back whatever it stored — the full ETag, the quoted
form, or just the number — without ever being lenient about *which* row it
names.

Only the parsing and comparison live here, because only those are generic. The
412 a failed precondition produces carries a song payload and a message in
Russian, which is the songs module's business: see modules/songs/versioning.py.
"""

from __future__ import annotations

import re

from fastapi import HTTPException

#: `W/"<id>-<rev>"`, `"<id>-<rev>"`, or a bare rev.
_TAG_RE = re.compile(r'^(?:W/)?"?(?:(?P<id>[0-9a-zA-Z_-]+)-)?(?P<rev>\d+)"?$')


def etag_for(resource_id: str, rev: int) -> str:
    """Weak tag: the body is regenerated from markdown on every read, so it is
    semantically — not byte-for-byte — identical across responses."""

    return f'W/"{resource_id}-{rev}"'


def parse_entity_tag(header: str | None) -> tuple[str | None, int] | None:
    """Extract `(resource_id, rev)` from an If-Match / If-None-Match header.

    Returns None when the header is absent or `*` (which matches any existing
    resource). Raises 400 on anything unparseable: silently ignoring a
    malformed precondition would turn a safety check into a no-op.
    """

    if header is None:
        return None
    value = header.strip()
    if not value or value == "*":
        return None
    # Only the first tag matters; our clients never send a list.
    match = _TAG_RE.match(value.split(",")[0].strip())
    if not match:
        raise HTTPException(status_code=400, detail="Malformed entity tag")
    return match.group("id"), int(match.group("rev"))


def matches(tag: tuple[str | None, int] | None, resource_id: str, rev: int) -> bool:
    """Whether a parsed tag identifies exactly this version of this row.

    The id half matters: two songs edited the same number of times share a rev,
    and comparing revs alone would let one song's tag validate another's.
    """

    if tag is None:
        return False
    tag_id, tag_rev = tag
    if tag_id is not None and tag_id != resource_id:
        return False
    return tag_rev == rev
