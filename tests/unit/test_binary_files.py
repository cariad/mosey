"""Unit tests for the `binary_files` module."""

import re
from pathlib import Path

from mosey import BINARY_FILE_PATTERNS
from mosey.patterns import check_pattern

ENDINGS = [p for p in BINARY_FILE_PATTERNS if p.startswith("*.")]
"""The patterns that match an extension, like "*.pdf"."""

NAMES = [p for p in BINARY_FILE_PATTERNS if not p.startswith("*.")]
"""The patterns that match a whole name, like ".DS_Store"."""

PAGE = Path(__file__).parents[2] / "docs" / "binary-files.md"
"""The docs page that lists every extension and whole name."""


def test_binary_file_patterns__check_pattern() -> None:
    """Every pattern means what an ignore-file's line would, and isn't broken."""
    for pattern in BINARY_FILE_PATTERNS:
        check_pattern(pattern)


def test_binary_file_patterns__docs() -> None:
    """The docs page lists exactly the same extensions, in order, and every name."""
    # The Windows runners don't read files as UTF-8 by default.
    page = PAGE.read_text(encoding="utf-8")
    formats = page.split("\n## Formats\n", 1)[1]

    # The second column of each row in the table.
    rows = re.findall(r"^\| [^|]+ \| (`.+?) +\|$", formats, flags=re.MULTILINE)
    listed = [extension for row in rows for extension in re.findall(r"`(.+?)`", row)]

    assert listed == [p.removeprefix("*.") for p in ENDINGS if p == p.lower()]

    for name in NAMES:
        assert f"`{name}`" in formats, name


def test_binary_file_patterns__no_duplicates() -> None:
    """No pattern appears twice."""
    assert len(set(BINARY_FILE_PATTERNS)) == len(BINARY_FILE_PATTERNS)


def test_binary_file_patterns__twins() -> None:
    """Each extension appears in lowercase then uppercase, before the whole names."""
    assert (*ENDINGS, *NAMES) == BINARY_FILE_PATTERNS
    assert ".DS_Store" in NAMES

    assert all(pattern == pattern.lower() for pattern in ENDINGS[::2])
    assert ENDINGS[1::2] == [pattern.upper() for pattern in ENDINGS[::2]]
