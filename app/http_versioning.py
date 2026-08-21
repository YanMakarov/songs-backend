"""ETag / If-Match plumbing for song resources.

One number does both jobs: `Song.rev` is the entity tag *and* the precondition
for writes. Everything here is about being lenient with the wire format so a
client can hand back whatever it stored — the full ETag, the quoted form, or
just the number — without ever being lenient about *which* song it names.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, status

from .schemas import SongDetail

#: `W/"<song id>-<rev>"`, `"<song id>-<rev>"`, or a bare rev.
_TAG_RE = re.compile(r'^(?:W/)?"?(?:(?P<id>[0-9a-zA-Z_-]+)-)?(?P<rev>\d+)"?$')


def etag_for(song_id: str, rev: int) -> str:
    """Weak tag: the body is regenerated from markdown on every read, so it is
    semantically — not byte-for-byte — identical across responses."""

    return f'W/"{song_id}-{rev}"'


def parse_entity_tag(header: str | None) -> tuple[str | None, int] | None:
    """Extract `(song_id, rev)` from an If-Match / If-None-Match header.

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


def matches(tag: tuple[str | None, int] | None, song_id: str, rev: int) -> bool:
    """Whether a parsed tag identifies exactly this version of this song.

    The id half matters: two songs edited the same number of times share a rev,
    and comparing revs alone would let one song's tag validate another's.
    """

    if tag is None:
        return False
    tag_id, tag_rev = tag
    if tag_id is not None and tag_id != song_id:
        return False
    return tag_rev == rev


def require_match(
    tag: tuple[str | None, int] | None, song_id: str, current_rev: int, current: SongDetail
) -> None:
    """Fail the write when the client based it on a version we no longer have.

    An absent precondition is allowed — not every caller is version-aware yet.
    The 412 carries the current state so the client can recover (show a banner,
    reload, and from phase 4 on merge) without a second round trip.
    """

    if tag is None or matches(tag, song_id, current_rev):
        return
    raise HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={
            "message": "Песня изменилась на сервере",
            "songId": song_id,
            "expectedRev": tag[1],
            "currentRev": current_rev,
            "current": current.model_dump(by_alias=True, mode="json"),
        },
    )
