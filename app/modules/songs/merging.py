"""Applying a write that was based on a version the song has since moved past.

Two people editing different verses is the common case and must not surface as
a conflict; only genuinely overlapping lines do. The textual merge itself is
`shared.merge` — what lives here is the part that knows about songs: finding
the ancestor snapshot, and stamping the result like any other write.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from ...shared import merge as merge_utils
from . import markdown, revisions
from .models import Setlist, Song
from .schemas import SongLine, SongUpdate
from .service import apply_metadata, to_detail
from .setlists import next_rev


class MergeOutcome:
    """What happened to a write that arrived against an older version."""

    def __init__(self, detail=None, merged=False, overwritten=None, conflict=None):
        self.detail = detail
        #: True when the two sides were combined without asking the user.
        self.merged = merged
        #: Metadata fields this write took away from someone else's value.
        self.overwritten = overwritten or []
        #: Set when the same lines were touched from both sides.
        self.conflict = conflict


def update_song_with_merge(
    session: Session,
    setlist: Setlist,
    song: Song,
    payload: SongUpdate,
    base_rev: int,
    *,
    author: str | None = None,
) -> MergeOutcome:
    base = revisions.get(session, song.id, base_rev)
    if base is None:
        # History does not reach that far back — nothing to merge against, so
        # the honest answer is "reload".
        return MergeOutcome(conflict="no_base")

    sent = payload.model_dump(exclude_unset=True, by_alias=False)

    if "lines" in sent and payload.lines is not None:
        validated = [SongLine.model_validate(line) for line in payload.lines]
        incoming_body = markdown.lines_to_markdown(validated)
        result = merge_utils.merge_bodies(base.markdown_body, song.markdown_body, incoming_body)
        if result.conflicted:
            return MergeOutcome(conflict="lines")
        song.markdown_body = result.text

    overwritten = merge_utils.overwritten_metadata(base, song, sent)
    apply_metadata(song, payload)

    song.updated_at = datetime.utcnow()
    song.updated_by = author
    song.rev = next_rev(session, setlist)
    session.add(song)
    revisions.record(session, song)
    session.commit()
    session.refresh(song)
    return MergeOutcome(detail=to_detail(song, setlist), merged=True, overwritten=overwritten)
