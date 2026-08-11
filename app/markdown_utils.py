"""Helpers to convert between structured song lines and Markdown."""

from __future__ import annotations

from typing import Iterable, List

from .models import generate_public_id
from .schemas import SongChord, SongLine


def _ensure_line(line: SongLine | dict) -> SongLine:
    return line if isinstance(line, SongLine) else SongLine.model_validate(line)


def _ensure_chord(chord: SongChord | dict) -> SongChord:
    return chord if isinstance(chord, SongChord) else SongChord.model_validate(chord)


def lines_to_markdown(lines: Iterable[SongLine | dict]) -> str:
    rendered: List[str] = []
    for raw_line in lines:
        line = _ensure_line(raw_line)
        if line.type == "section":
            label = (line.label or "").strip()
            key_suffix = f" {{key={line.key.strip()}}}" if line.key else ""
            rendered.append(f"## {label}{key_suffix}".rstrip())
            continue
        if line.type == "chords":
            chords = " ".join(ch.chord.strip() for ch in sorted(line.chords, key=lambda c: c.position) if ch.chord)
            rendered.append(f":: {chords}".rstrip())
            continue
        rendered.append(_render_lyric_line(line))
    return "\n".join(rendered).strip() or ""


def _render_lyric_line(line: SongLine) -> str:
    text = line.lyrics or ""
    if not line.chords:
        return text
    sorted_chords = sorted(line.chords, key=lambda c: c.position)
    acc: List[str] = []
    cursor = 0
    for chord in sorted_chords:
        pos = max(0, min(len(text), chord.position))
        acc.append(text[cursor:pos])
        symbol = chord.chord.strip()
        if symbol:
            acc.append(f"[{symbol}]")
        cursor = pos
    acc.append(text[cursor:])
    return "".join(acc)


def markdown_to_lines(markdown: str) -> List[SongLine]:
    raw_lines = markdown.splitlines() if markdown else []
    lines: List[SongLine] = []
    for raw in raw_lines:
        stripped = raw.rstrip()
        if stripped.startswith("##"):
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
    chords = [SongChord(id=generate_public_id(), position=index, chord=token) for index, token in enumerate(tokens)]
    return SongLine(id=generate_public_id(), type="chords", chords=chords)


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
                position = len("".join(text_parts))
                chords.append(SongChord(id=generate_public_id(), position=position, chord=chord_text))
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
