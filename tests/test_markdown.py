"""The Markdown song format, and what it can express.

The interesting case is a chord placed past the end of its lyrics — one
syllable held under a run of changes. Chords live inside the text
(`[Am7]слово`), so a chord's column is an index into it, and there is nowhere
to put one that falls past the end. Those get an explicit column instead.
"""

from __future__ import annotations

import pytest

from app.markdown_utils import lines_to_markdown, markdown_to_lines
from app.schemas import SongChord, SongLine


def line(lyrics: str, *chords: tuple[int, str], voicings: dict[str, str] | None = None) -> SongLine:
    voicings = voicings or {}
    return SongLine(
        id="line",
        type="line",
        lyrics=lyrics,
        chords=[
            SongChord(id=f"c{i}", position=position, chord=symbol, voicing=voicings.get(symbol))
            for i, (position, symbol) in enumerate(chords)
        ],
    )


def roundtrip(source: SongLine) -> SongLine:
    return markdown_to_lines(lines_to_markdown([source]))[0]


def positions(parsed: SongLine) -> list[tuple[int, str]]:
    return sorted((c.position, c.chord) for c in parsed.chords)


def test_chords_inside_the_text_are_written_inline():
    assert lines_to_markdown([line("Длинная строка", (0, "C"), (8, "G"))]) == "[C]Длинная [G]строка"


def test_a_chord_at_the_very_end_needs_no_column():
    assert lines_to_markdown([line("Текст", (5, "G"))]) == "Текст[G]"


def test_a_chord_past_the_end_keeps_its_column():
    """The reported bug: three chords over the single letter "А".

    Every position beyond the text used to collapse to len(text), so the
    chords ended up stacked on one column and drawn on top of each other.
    """

    source = line("А", (0, "Am7"), (2, "Dmaj7"), (4, "F#m"))

    assert lines_to_markdown([source]) == "[Am7]А[Dmaj7@2][F#m@4]"
    assert positions(roundtrip(source)) == [(0, "Am7"), (2, "Dmaj7"), (4, "F#m")]


def test_distinct_columns_stay_distinct():
    """The failure was silent: nothing errored, the chords just merged."""

    parsed = roundtrip(line("А", (2, "C"), (5, "D"), (9, "E")))

    columns = [c.position for c in parsed.chords]
    assert len(set(columns)) == len(columns)


def test_a_chord_past_an_empty_line():
    source = line("", (0, "C"), (4, "G"))

    assert positions(roundtrip(source)) == [(0, "C"), (4, "G")]
    assert roundtrip(source).lyrics == ""


def test_voicing_survives_an_explicit_column():
    source = line("А", (6, "Am7"), voicings={"Am7": "a1b2c3"})
    parsed = roundtrip(source)

    assert lines_to_markdown([source]) == "А[Am7:a1b2c3@6]"
    assert parsed.chords[0].position == 6
    assert parsed.chords[0].voicing == "a1b2c3"


@pytest.mark.parametrize(
    "markdown",
    [
        "[C]Длинная [G]строка",
        "Текст без аккордов",
        "[Am7]А",
        "## Куплет {key=Em}",
        ":: Am7 D x2",
    ],
)
def test_existing_songs_render_back_byte_for_byte(markdown):
    """Nothing already stored may change shape.

    A song is re-rendered on every write, and a format change that rewrites
    untouched lines would turn one edit into a diff against every line —
    which the three-way merge would then have to reconcile.
    """

    assert lines_to_markdown(markdown_to_lines(markdown)) == markdown


def test_an_at_sign_without_digits_is_not_a_column():
    parsed = markdown_to_lines("[C@]Текст")[0]

    assert parsed.chords[0].chord == "C@"
    assert parsed.chords[0].position == 0
