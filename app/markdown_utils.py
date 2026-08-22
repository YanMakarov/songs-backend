"""Helpers to convert between structured song lines and Markdown."""

from __future__ import annotations

import re
from typing import Iterable, List

from .models import generate_public_id
from .schemas import SongChord, SongLine

_REPEAT_RE = re.compile(r"^[xх](\d{1,3})$", re.IGNORECASE)
_VOICING_RE = re.compile(r"^[0-9a-f]{6}$")
#: Explicit column for a chord that sits past the end of its lyrics.
#: Chord symbols never contain "@", so this cannot collide with one.
_COLUMN_RE = re.compile(r"^(.*)@(\d{1,4})$")


def _format_chord_token(chord: SongChord) -> str:
    symbol = chord.chord.strip()
    if chord.voicing and _VOICING_RE.match(chord.voicing):
        return f"{symbol}:{chord.voicing}"
    return symbol


def _split_chord_token(token: str) -> tuple[str, str | None]:
    if ":" in token:
        symbol, _, code = token.rpartition(":")
        if symbol and _VOICING_RE.match(code):
            return symbol, code
    return token, None


def _split_column(token: str) -> tuple[str, int | None]:
    """Peel an explicit "@column" suffix off a chord token.

    Written by `_render_lyric_line` only for chords that sit past the end of
    the lyrics, so a token without it keeps meaning exactly what it did
    before and old songs parse unchanged.
    """

    match = _COLUMN_RE.match(token)
    if not match:
        return token, None
    symbol = match.group(1).strip()
    if not symbol:
        return token, None
    return symbol, int(match.group(2))


def _ensure_line(line: SongLine | dict) -> SongLine:
    return line if isinstance(line, SongLine) else SongLine.model_validate(line)


def _ensure_chord(chord: SongChord | dict) -> SongChord:
    return chord if isinstance(chord, SongChord) else SongChord.model_validate(chord)


def lines_to_markdown(lines: Iterable[SongLine | dict]) -> str:
    rendered: List[str] = []
    for raw_line in lines:
        line = _ensure_line(raw_line)
        if line.type == "pagebreak":
            rendered.append("---")
            continue
        if line.type == "section":
            label = (line.label or "").strip()
            key_suffix = f" {{key={line.key.strip()}}}" if line.key else ""
            rendered.append(f"## {label}{key_suffix}".rstrip())
            continue
        if line.type == "chords":
            chord_str = " ".join(_format_chord_token(ch) for ch in sorted(line.chords, key=lambda c: c.position) if ch.chord)
            parts = [chord_str] if chord_str else []
            if line.repeat_count and line.repeat_count > 1:
                parts.append(f"x{line.repeat_count}")
            body = " ".join(parts)
            rendered.append(f":: {body}".rstrip() if body else "::")
            continue
        rendered.append(_render_lyric_line(line))
    return "\n".join(rendered).strip() or ""


def _render_lyric_line(line: SongLine) -> str:
    """Write a lyrics line with its chords.

    Chords live inside the text — `[Am7]слово` — so a chord's column is just
    an index into it. That leaves nowhere to put a chord placed past the end
    of the line, which happens whenever one syllable is held under a run of
    changes: "А" with three chords over it. Clamping such a chord to
    `len(text)` was silently piling them onto the same column.

    Those chords are written after the text with an explicit column instead:
    `А[Dmaj7@4]`. Chords that do fit are untouched, so an existing song
    re-renders byte for byte as before.
    """

    text = line.lyrics or ""
    if not line.chords:
        return text
    sorted_chords = sorted(line.chords, key=lambda c: c.position)
    acc: List[str] = []
    cursor = 0
    trailing: List[SongChord] = []
    for chord in sorted_chords:
        if not chord.chord.strip():
            continue
        if chord.position > len(text):
            trailing.append(chord)
            continue
        pos = max(0, chord.position)
        acc.append(text[cursor:pos])
        acc.append(f"[{_format_chord_token(chord)}]")
        cursor = pos
    acc.append(text[cursor:])
    for chord in trailing:
        acc.append(f"[{_format_chord_token(chord)}@{chord.position}]")
    return "".join(acc)


def markdown_to_lines(markdown: str) -> List[SongLine]:
    raw_lines = markdown.splitlines() if markdown else []
    lines: List[SongLine] = []
    for raw in raw_lines:
        stripped = raw.rstrip()
        if stripped == "---":
            lines.append(SongLine(id=generate_public_id(), type="pagebreak", chords=[]))
        elif stripped.startswith("##"):
            lines.append(_parse_section_line(stripped))
        elif stripped.startswith("::"):
            lines.append(_parse_chords_line(stripped))
        else:
            lines.append(_parse_lyric_line(stripped))
    if not lines:
        lines.append(empty_line())
    return lines


def _parse_section_line(raw: str) -> SongLine:
    content = raw.lstrip("#").strip()
    key = None
    if "{key=" in content and content.endswith("}"):
        start = content.rfind("{key=")
        key = content[start + 5 : -1].strip()
        content = content[:start].rstrip()
    return SongLine(id=generate_public_id(), type="section", label=content, key=key, chords=[])


def _parse_chords_line(raw: str) -> SongLine:
    payload = raw[2:].strip()
    tokens = [token for token in payload.split() if token]
    repeat_count = None
    if tokens:
        match = _REPEAT_RE.match(tokens[-1])
        if match:
            repeat_count = int(match.group(1))
            tokens = tokens[:-1]
    chords = []
    for index, token in enumerate(tokens):
        symbol, voicing = _split_chord_token(token)
        chords.append(SongChord(id=generate_public_id(), position=index, chord=symbol, voicing=voicing))
    return SongLine(
        id=generate_public_id(),
        type="chords",
        chords=chords,
        repeat_count=repeat_count,
    )


def _parse_lyric_line(raw: str) -> SongLine:
    text_parts: List[str] = []
    chords: List[SongChord] = []
    idx = 0
    while idx < len(raw):
        if raw[idx] == "[":
            closing = raw.find("]", idx + 1)
            if closing == -1:
                text_parts.append(raw[idx])
                idx += 1
                continue
            chord_text = raw[idx + 1 : closing].strip()
            if chord_text:
                chord_text, explicit_column = _split_column(chord_text)
                # An explicit column wins: it is there precisely because the
                # chord sits where the running text offset cannot express it.
                position = explicit_column if explicit_column is not None else len("".join(text_parts))
                symbol, voicing = _split_chord_token(chord_text)
                chords.append(SongChord(id=generate_public_id(), position=position, chord=symbol, voicing=voicing))
            idx = closing + 1
        else:
            text_parts.append(raw[idx])
            idx += 1
    lyrics = "".join(text_parts)
    return SongLine(id=generate_public_id(), type="line", lyrics=lyrics, chords=chords)


def empty_line() -> SongLine:
    return SongLine(id=generate_public_id(), type="line", lyrics="", chords=[])


def default_lines() -> List[SongLine]:
    return [empty_line()]
