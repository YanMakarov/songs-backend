"""Three-way merge of song bodies.

Two people editing different verses of the same song should not have to think
about it. Only a genuine overlap — the same lines touched from both sides —
is worth interrupting someone for.

Merging happens here rather than on the client because the server already
holds both the ancestor snapshot and the current state, and markdown is its
canonical form. Doing it in the browser would mean shipping a second
implementation of the line serialiser and keeping the two in step.

The merge is textual, line by line, deliberately: `markdown_to_lines`
generates fresh ids on every read, so the same verse has different ids in two
consecutive responses. Those ids cannot anchor anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import merge3


@dataclass
class MergeResult:
    #: Merged body. Meaningless when `conflicted` is True.
    text: str = ""
    conflicted: bool = False
    #: Metadata fields where the incoming write overwrote a different value.
    overwritten: List[str] = field(default_factory=list)


def merge_bodies(base: str, current: str, incoming: str) -> MergeResult:
    """Merge `incoming` into `current`, both descended from `base`.

    Returns a conflicted result rather than a body with markers in it: half a
    merge is worse than none, and the caller has a UI for asking.
    """

    if incoming == current:
        return MergeResult(text=current)
    if current == base:
        # Nobody else has written since — an ordinary update that only looked
        # stale because the rev moved for another reason.
        return MergeResult(text=incoming)
    if incoming == base:
        # This client changed nothing in the body; keep the other side's work.
        return MergeResult(text=current)

    merger = merge3.Merge3(
        _lines(base),
        _lines(current),
        _lines(incoming),
    )
    for group in merger.merge_groups():
        if group[0] == "conflict":
            return MergeResult(conflicted=True)
    return MergeResult(text="".join(merger.merge_lines()).rstrip("\n"))


def _lines(text: str) -> List[str]:
    return (text or "").splitlines(keepends=True)


#: Metadata that is not merged: last write wins, but the caller is told which
#: fields it stepped on so the interface can mention it.
MERGEABLE_METADATA = ("title", "key", "original_key", "bpm", "time_signature")


def overwritten_metadata(base, current, incoming: dict) -> List[str]:
    """Fields the incoming write changes away from a value someone else set.

    A field only counts as overwritten when the other side moved it *and* this
    write disagrees; matching edits are not worth mentioning.
    """

    stepped_on: List[str] = []
    for name in MERGEABLE_METADATA:
        if name not in incoming:
            continue
        base_value = getattr(base, name, None)
        current_value = getattr(current, name, None)
        if current_value == base_value:
            continue
        if incoming[name] != current_value:
            stepped_on.append(name)
    return stepped_on
