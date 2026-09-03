"""Turning a failed precondition into the 412 this API promises.

The generic half — parsing an entity tag and comparing it — is `core.http`.
What is song-specific, and therefore here, is the body: a message the
interface shows verbatim, and the current song so the client can recover
without a second round trip.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from ...core.http import matches
from .schemas import SongDetail


def require_match(
    tag: tuple[str | None, int] | None, song_id: str, current_rev: int, current: SongDetail
) -> None:
    """Fail the write when the client based it on a version we no longer have.

    An absent precondition is allowed — not every caller is version-aware yet.
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
