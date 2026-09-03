"""Server-side PDF parsing utilities used by the import endpoint."""

from __future__ import annotations

import io
import re
import uuid
from typing import Iterable, List, Optional

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTAnno, LTChar, LTTextContainer, LTTextLine
from pdfminer.pdfparser import PDFSyntaxError

from ...shared.music import detect_key, normalize_chord_text


class PDFImportError(Exception):
    """Raised when a PDF cannot be processed into song data."""


DECORATIVE_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")
SECTION_HEADER_STRIP_RE = re.compile(r"[0-9\s\.,:;!?()\-–—•/\\]+")
BPM_RE = re.compile(r"(\d{2,3})\s*BPM", re.IGNORECASE)
TIME_SIG_RE = re.compile(r"(\d{1,2}\s*/\s*\d{1,2})")


def _uid() -> str:
    return uuid.uuid4().hex


def empty_line() -> dict:
    return {"id": _uid(), "type": "line", "lyrics": "", "chords": []}


def section_line(label: str, key: Optional[str]) -> dict:
    return {"id": _uid(), "type": "section", "label": label, "key": key, "chords": []}


def instrumental_line() -> dict:
    return {"id": _uid(), "type": "chords", "chords": []}


def _iter_text_lines(layout) -> Iterable[LTTextLine]:
    if isinstance(layout, LTTextContainer):
        for text_line in layout:
            if isinstance(text_line, LTTextLine):
                yield text_line
    if hasattr(layout, "_objs"):
        for element in layout._objs:  # type: ignore[attr-defined]
            yield from _iter_text_lines(element)


def _append_char(line_text: str, prev_end_x: Optional[float], char_obj: LTChar) -> tuple[str, float]:
    char = char_obj.get_text()
    if not char:
        return line_text, prev_end_x or 0.0
    x0 = getattr(char_obj, "x0", None)
    width = getattr(char_obj, "width", None)
    if prev_end_x is not None and x0 is not None and width is not None and char.strip():
        gap = x0 - prev_end_x
        avg_width = abs(width) if width else 3.0
        threshold = max(avg_width * 0.5, 1.2)
        if gap > threshold and not line_text.endswith(" "):
            line_text += " "
    line_text += char
    end_x = (x0 or 0.0) + (width or 0.0)
    return line_text, end_x


def extract_pdf_lines(data: bytes) -> list[str]:
    if not data:
        raise PDFImportError("Пустой файл PDF")
    lines: list[str] = []
    laparams = LAParams(line_overlap=0.5, line_margin=0.2, char_margin=2.0, word_margin=0.1, boxes_flow=None)
    try:
        with io.BytesIO(data) as buffer:
            for page_layout in extract_pages(buffer, laparams=laparams):
                for text_line in _iter_text_lines(page_layout):
                    current = ""
                    prev_end_x: Optional[float] = None
                    for obj in text_line:
                        if isinstance(obj, LTChar):
                            current, prev_end_x = _append_char(current, prev_end_x, obj)
                        elif isinstance(obj, LTAnno):
                            txt = obj.get_text()
                            if txt not in {"\n", "\r"}:
                                current += txt
                    cleaned = current.replace("\u00a0", " ").rstrip()
                    if cleaned:
                        lines.append(cleaned)
    except PDFSyntaxError as exc:
        raise PDFImportError("Файл повреждён или не является PDF") from exc
    except Exception as exc:  # pragma: no cover - generic safeguard
        raise PDFImportError("Не удалось разобрать PDF") from exc
    if not lines:
        raise PDFImportError("Не удалось извлечь текст из PDF")
    return lines


def _is_decorative_divider(raw: str) -> bool:
    return DECORATIVE_RE.search(raw) is None


def _is_section_header(raw: str) -> bool:
    core = SECTION_HEADER_STRIP_RE.sub("", raw)
    if not core:
        return False
    if re.search(r"[a-zа-яё]", core):
        return False
    return bool(re.search(r"[A-ZА-ЯЁ]", core))


def _is_chord_like_token(token: str) -> bool:
    s = token.strip()
    if not s:
        return False
    if re.search(r"\s", s):
        return False
    if s in {"?", "-", "—", "–"}:
        return True
    normalized = normalize_chord_text(s)
    return bool(re.fullmatch(r"[A-G][#b]?[A-Za-z0-9+°/]*", normalized))


def _try_parse_chords_only_line(raw: str) -> Optional[list[str]]:
    if "|" not in raw:
        return None
    segments = [segment.strip() for segment in raw.split("|")]
    segments = [s for s in segments if s]
    if not segments:
        return None
    tokens: list[str] = []
    for seg in segments:
        match = re.match(r"^(.+?)\s*[x×]\s*(\d+)$", seg, re.IGNORECASE)
        chord_part = seg
        repeat = 1
        if match:
            chord_part = match.group(1).strip()
            repeat = int(match.group(2)) or 1
        if not _is_chord_like_token(chord_part):
            return None
        normalized = chord_part if chord_part in {"?", "-", "—", "–"} else normalize_chord_text(chord_part)
        for _ in range(repeat):
            tokens.append(normalized)
    return tokens or None


def _extract_header_meta(lines: List[str]) -> tuple[Optional[str], Optional[int], Optional[str], int]:
    idx = 0
    while idx < len(lines) and lines[idx] == "":
        idx += 1
    title = lines[idx] if idx < len(lines) else None
    if title is not None:
        idx += 1
    bpm: Optional[int] = None
    time_signature: Optional[str] = None
    while idx < len(lines):
        line = lines[idx]
        if line == "":
            idx += 1
            continue
        bpm_match = BPM_RE.search(line)
        time_match = TIME_SIG_RE.search(line)
        if bpm_match or time_match:
            if bpm_match:
                bpm = int(bpm_match.group(1))
            if time_match:
                time_signature = time_match.group(1).replace(" ", "")
            idx += 1
            continue
        break
    return title, bpm, time_signature, idx


def _tokenize(lines: Iterable[str]) -> list[dict]:
    items: list[dict] = []
    for raw in lines:
        if raw == "" or _is_decorative_divider(raw):
            continue
        if _is_section_header(raw):
            items.append({"type": "section", "label": raw})
            continue
        chords = _try_parse_chords_only_line(raw)
        if chords:
            items.append({"type": "chords", "chords": chords})
            continue
        items.append({"type": "text", "text": raw})
    return items


def parse_song_document(raw_lines: Optional[Iterable[str]]) -> dict:
    source = list(raw_lines or [])
    lines = [line.strip() for line in source]
    title, bpm, time_signature, rest_index = _extract_header_meta(lines)
    items = _tokenize(lines[rest_index:])

    result_lines: list[dict] = []
    current_key: Optional[str] = None
    primary_key: Optional[str] = None

    i = 0
    while i < len(items):
        item = items[i]
        if item["type"] == "section":
            j = i + 1
            bucket: list[str] = []
            while j < len(items) and items[j]["type"] != "section":
                if items[j]["type"] == "chords":
                    bucket.extend(items[j]["chords"])
                j += 1
            detected = detect_key(bucket) if bucket else None
            if detected and primary_key is None:
                primary_key = detected
            if detected and detected != current_key:
                result_lines.append(section_line(item["label"], detected))
                current_key = detected
            else:
                result_lines.append(section_line(item["label"], None))
        elif item["type"] == "chords":
            line = instrumental_line()
            line["chords"] = [
                {"id": _uid(), "position": position, "chord": chord}
                for position, chord in enumerate(item["chords"])
            ]
            result_lines.append(line)
        else:
            line = empty_line()
            line["lyrics"] = item["text"]
            result_lines.append(line)
        i += 1

    return {
        "title": title,
        "bpm": bpm,
        "time_signature": time_signature,
        "primary_key": primary_key,
        "lines": result_lines,
    }


def import_pdf_document(data: bytes) -> dict:
    raw_lines = extract_pdf_lines(data)
    return parse_song_document(raw_lines)
