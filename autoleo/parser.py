from __future__ import annotations

from pathlib import Path

from .models import WordEntry


SEPARATORS = (" — ", " – ", " - ", "\t")


def parse_entries(text: str) -> list[WordEntry]:
    entries: list[WordEntry] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        separator = next((item for item in SEPARATORS if item in line), None)
        if separator is None:
            raise ValueError(
                f"Line {line_number}: expected 'word — definition' format, got: {raw_line!r}"
            )

        word, definition = line.split(separator, 1)
        word = word.strip()
        definition = definition.strip()

        if not word or not definition:
            raise ValueError(
                f"Line {line_number}: both word and definition must be non-empty."
            )

        entries.append(WordEntry(word=word, definition=definition))

    if not entries:
        raise ValueError("No words found in the input.")

    return entries


def parse_file(path: Path) -> list[WordEntry]:
    return parse_entries(path.read_text(encoding="utf-8-sig"))

