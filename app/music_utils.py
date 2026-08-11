"""Music theory helpers shared across backend features."""

from __future__ import annotations

import re
from typing import Iterable, Optional


SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Keys that conventionally use flats (major tonic names + their relative minors).
FLAT_KEY_TONICS = {
    "F",
    "Bb",
    "Eb",
    "Ab",
    "Db",
    "Gb",
    "Cb",
    "D",
    "G",
    "C",
}

NOTE_TO_SEMITONE = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "Fb": 4,
    "F": 5,
    "E#": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
    "Cb": 11,
}

CYRILLIC_ROOT_LOOKALIKES = {
    "А": "A",
    "В": "B",
    "С": "C",
    "Е": "E",
    "Н": "H",
    "К": "K",
    "М": "M",
    "О": "O",
    "Р": "P",
    "Т": "T",
    "Х": "X",
    "а": "a",
    "в": "b",
    "с": "c",
    "е": "e",
    "н": "h",
    "к": "k",
    "м": "m",
    "о": "o",
    "р": "p",
    "т": "t",
    "х": "x",
}


def normalize_chord_text(chord: Optional[str]) -> str:
    raw = (chord or "").strip()
    if not raw:
        return ""
    first = CYRILLIC_ROOT_LOOKALIKES.get(raw[0])
    return f"{first}{raw[1:]}" if first else raw


def note_to_semitone(note: Optional[str]) -> Optional[int]:
    return NOTE_TO_SEMITONE.get(note) if note else None


def semitone_to_note(value: int, prefer_flat: bool) -> str:
    normalized = (value % 12 + 12) % 12
    names = FLAT_NAMES if prefer_flat else SHARP_NAMES
    return names[normalized]


def parse_key(key_label: Optional[str]) -> dict[str, object]:
    raw = (key_label or "").strip()
    match = re.match(r"^([A-Ga-g])([#b]?)(m)?$", raw)
    if not match:
        return {"tonic": raw or "C", "mode": "major", "prefer_flat": False, "valid": False}
    letter = match.group(1).upper()
    accidental = match.group(2) or ""
    mode = "minor" if match.group(3) else "major"
    tonic = f"{letter}{accidental}"
    prefer_flat = (
        accidental == "b"
        or tonic in FLAT_KEY_TONICS
        or (mode == "minor" and tonic in FLAT_KEY_TONICS)
    )
    return {"tonic": tonic, "mode": mode, "prefer_flat": prefer_flat, "valid": True}


def parse_chord(chord: Optional[str]) -> tuple[Optional[str], str]:
    raw = normalize_chord_text(chord)
    match = re.match(r"^([A-Ga-g])([#b]?)(.*)$", raw)
    if not match:
        return None, raw
    root = f"{match.group(1).upper()}{match.group(2) or ''}"
    suffix = match.group(3) or ""
    return root, suffix


def diatonic_chords(key_label: Optional[str]) -> list[str]:
    key = parse_key(key_label)
    if not key["valid"]:
        return []
    tonic_semitone = note_to_semitone(key["tonic"])
    if tonic_semitone is None:
        return []
    if key["mode"] == "minor":
        steps = [0, 2, 3, 5, 7, 8, 10]
        qualities = ["m", "dim", "", "m", "m", "", ""]
    else:
        steps = [0, 2, 4, 5, 7, 9, 11]
        qualities = ["", "m", "m", "", "", "m", "dim"]
    prefer_flat = key["prefer_flat"]
    return [
        f"{semitone_to_note(tonic_semitone + step, prefer_flat)}{qualities[i]}"
        for i, step in enumerate(steps)
    ]


def _chord_quality_info(chord: Optional[str]) -> Optional[dict[str, object]]:
    raw = normalize_chord_text(chord)
    if not raw:
        return None
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    root, suffix = parse_chord(raw)
    if root is None:
        return None
    semitone = note_to_semitone(root)
    if semitone is None:
        return None
    quality = "maj"
    if re.match(r"^dim", suffix, re.IGNORECASE):
        quality = "dim"
    elif re.match(r"^m(?!aj)", suffix, re.IGNORECASE):
        quality = "min"
    return {"semitone": semitone, "quality": quality}


def _diatonic_quality_info(key_label: Optional[str]) -> list[dict[str, object]]:
    return [info for chord in diatonic_chords(key_label) if (info := _chord_quality_info(chord))]


def detect_key(chord_strings: Iterable[str]) -> Optional[str]:
    observed = [info for chord in chord_strings if (info := _chord_quality_info(chord))]
    if not observed:
        return None

    best: Optional[tuple[float, str]] = None
    for semitone in range(12):
        for mode in ("major", "minor"):
            tonic_label = f"{semitone_to_note(semitone, False)}{'m' if mode == 'minor' else ''}"
            diatonic = _diatonic_quality_info(tonic_label)
            score = 0.0
            for obs in observed:
                if any(d["semitone"] == obs["semitone"] and d["quality"] == obs["quality"] for d in diatonic):
                    score += 1
            tonic_quality = "min" if mode == "minor" else "maj"
            if any(o["semitone"] == semitone and o["quality"] == tonic_quality for o in observed):
                score += 2
            first = observed[0]
            if first["semitone"] == semitone and first["quality"] == tonic_quality:
                score += 1
            if mode == "major":
                score += 0.1
            if best is None or score > best[0]:
                best = (score, tonic_label)
    return best[1] if best else None
