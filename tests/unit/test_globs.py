"""Unit tests for the `globs` module."""

import re
import signal
import sys
from pathlib import Path
from types import FrameType
from typing import NamedTuple

from pytest import mark, param, skip

from mosey.globs import translate_glob
from tests.file_system_helpers import (
    format_pattern,
    list_files,
    skip_if_windows_cannot_create,
)
from tests.markers import needs_git


class GlobCase(NamedTuple):
    """A glob, and the names or paths it matches and doesn't."""

    glob: str
    """The glob to translate."""

    matches: list[str]
    """Names or "/"-separated paths that the glob matches."""

    misses: list[str]
    """Names or paths that the glob doesn't match, in the order Git lists them."""

    divergence: str | None = None
    """Why Git matches differently, if it does."""


ONE_BYTE = "Git's \"?\" matches one byte, and Mosey's matches one character"
"""Why Git matches some non-ASCII names differently."""


def matching(case: GlobCase) -> list[str]:
    """Return the paths in a case that its glob matches.

    Args:
        case: The case to check.

    Returns:
        The paths, from both `matches` and `misses`, that the glob matches, in order.
    """
    source = translate_glob(case.glob)

    if source is None:
        return []

    paths = [*case.matches, *case.misses]
    return [path for path in paths if re.fullmatch(source, path)]


LITERALS = [
    param(
        GlobCase(glob="a", matches=["a"], misses=["ab", "b", "ba"]),
        id="literal",
    ),
    param(
        GlobCase(glob="a.b", matches=["a.b"], misses=["axb"]),
        id="dot",
    ),
    # Text after a wildcard is literal too.
    param(
        GlobCase(glob="*.b", matches=["a.b"], misses=["axb"]),
        id="dot-after-star",
    ),
    # Characters that mean something in a regular expression mean nothing here.
    param(
        GlobCase(glob="^(a+){2}$", matches=["^(a+){2}$"], misses=["aa"]),
        id="regular-expression-characters",
    ),
    # macOS and Windows can't hold "A" and "a" side by side, so the tree only has "a".
    param(
        GlobCase(glob="A", matches=[], misses=["a"]),
        id="case",
    ),
    # "café" spells "é" as the single character U+00E9, and the name spells it as "e"
    # followed by U+0301, a combining accent. Names are never normalised, so the two
    # spellings don't match each other.
    param(
        GlobCase(glob="café", matches=[], misses=["cafe\u0301"]),
        id="composed-against-decomposed",
    ),
    # A "!" or "#" at the start of a glob is just a character, left by a line like "/!a"
    # or "!#a".
    param(
        GlobCase(glob="!a", matches=["!a"], misses=["a"]),
        id="exclamation-mark",
    ),
    param(
        GlobCase(glob="#a", matches=["#a"], misses=["a"]),
        id="hash",
    ),
    # A line like "a /" leaves a glob that ends with a space.
    param(
        GlobCase(glob="a ", matches=["a "], misses=["a"]),
        id="trailing-space",
    ),
]


@mark.parametrize("case", LITERALS)
def test_translate_glob__literals(case: GlobCase) -> None:
    """Characters other than wildcards and backslashes match only themselves."""
    assert matching(case) == case.matches


ESCAPES = [
    param(
        GlobCase(glob="\\a", matches=["a"], misses=["\\a"]),
        id="escaped-letter",
    ),
    # A backslash never starts a regular expression's escape, so "\d" is the letter "d"
    # and not any digit.
    param(
        GlobCase(glob="a\\d", matches=["ad"], misses=["a1"]),
        id="escaped-regular-expression",
    ),
    param(
        GlobCase(glob="a\\*b", matches=["a*b"], misses=["ab", "axb"]),
        id="escaped-star",
    ),
    param(
        GlobCase(glob="a\\?b", matches=["a?b"], misses=["axb"]),
        id="escaped-question-mark",
    ),
    param(
        GlobCase(glob="\\\\", matches=["\\"], misses=["\\\\", "a"]),
        id="escaped-backslash",
    ),
    # Backslashes escape each other in pairs, so the "*" isn't escaped.
    param(
        GlobCase(glob="a\\\\*", matches=["a\\", "a\\b"], misses=["a*", "ab"]),
        id="escaped-backslash-then-star",
    ),
    param(
        GlobCase(glob="\\[a]", matches=["[a]"], misses=["a"]),
        id="escaped-bracket",
    ),
    param(
        GlobCase(glob="a\\ ", matches=["a "], misses=["a"]),
        id="escaped-space",
    ),
    param(
        GlobCase(glob="a\\/b", matches=["a/b"], misses=["b"]),
        id="escaped-slash",
    ),
    param(
        GlobCase(glob="*\\**", matches=["*", "a*b", "a**"], misses=["ab", "b"]),
        id="escaped-star-between-stars",
    ),
]


@mark.parametrize("case", ESCAPES)
def test_translate_glob__escapes(case: GlobCase) -> None:
    """A backslash makes the character after it literal."""
    assert matching(case) == case.matches


QUESTION_MARKS = [
    param(
        GlobCase(glob="a?b", matches=["axb"], misses=["a/b", "ab", "axxb"]),
        id="question-mark",
    ),
    # A "." at the start of a name isn't special.
    param(
        GlobCase(glob="?a", matches=[".a", "ba"], misses=["a"]),
        id="leading-dot",
    ),
    # A name can hold a carriage return, like the hidden "Icon\r" file that macOS
    # Finder makes.
    param(
        GlobCase(glob="Icon?", matches=["Icon\r"], misses=["Icon"]),
        id="carriage-return",
    ),
]


@mark.parametrize("case", QUESTION_MARKS)
def test_translate_glob__question_marks(case: GlobCase) -> None:
    """A "?" matches one character other than "/"."""
    assert matching(case) == case.matches


ASTERISKS = [
    param(
        GlobCase(glob="a*", matches=["a", "ab"], misses=["b", "ba"]),
        id="star-at-end",
    ),
    param(
        GlobCase(glob="*a", matches=["a", "aba", "ba"], misses=["ab"]),
        id="star-at-start",
    ),
    param(
        GlobCase(
            glob="a*b",
            matches=["ab", "axb", "axxb"],
            misses=["a/b", "abx", "ba", "xab"],
        ),
        id="star-in-middle",
    ),
    # A "." at the start of a name isn't special.
    param(
        GlobCase(glob="*", matches=[".a", "a"], misses=[]),
        id="star-alone",
    ),
    param(
        GlobCase(glob="a*/b", matches=["a/b", "ax/b"], misses=["a/x/b", "ax/c"]),
        id="star-before-slash",
    ),
    param(
        GlobCase(
            glob="a*b*c",
            matches=["abc", "abcbc", "abxc", "axbxc"],
            misses=["a/bc", "ab/c", "abcx", "acb"],
        ),
        id="several-stars",
    ),
    # The two "aa" can't share an "a", so "aaa" is too short.
    param(
        GlobCase(glob="*aa*aa", matches=["aaaa", "aaaaa"], misses=["aaa"]),
        id="overlapping-text",
    ),
    param(
        GlobCase(glob="*?*a", matches=["aa", "ba"], misses=["a"]),
        id="question-mark-between-stars",
    ),
    param(
        GlobCase(glob="a*?", matches=["ab", "abc"], misses=["a"]),
        id="question-mark-after-star",
    ),
    param(
        GlobCase(glob="a**b", matches=["ab", "axb"], misses=["a/b"]),
        id="two-stars",
    ),
]


@mark.parametrize("case", ASTERISKS)
def test_translate_glob__asterisks(case: GlobCase) -> None:
    """A "*" matches any run of characters other than "/", even none."""
    assert matching(case) == case.matches


NON_ASCII = [
    # "café" spells "é" as the single character U+00E9, which takes two bytes.
    param(
        GlobCase(
            glob="caf?",
            matches=["cafe", "café"],
            misses=["cafex"],
            divergence=ONE_BYTE,
        ),
        id="composed-question-mark",
    ),
    param(
        GlobCase(
            glob="caf??",
            matches=["cafex"],
            misses=["cafe", "café"],
            divergence=ONE_BYTE,
        ),
        id="composed-two-question-marks",
    ),
    # This spells "é" as "e" followed by U+0301, a combining accent, which is a
    # character of its own.
    param(
        GlobCase(glob="caf?", matches=["cafe"], misses=["cafe\u0301"]),
        id="decomposed-question-mark",
    ),
    param(
        GlobCase(
            glob="caf??",
            matches=["cafex", "cafe\u0301"],
            misses=["cafe"],
            divergence=ONE_BYTE,
        ),
        id="decomposed-two-question-marks",
    ),
]


@mark.parametrize("case", NON_ASCII)
def test_translate_glob__non_ascii(case: GlobCase) -> None:
    """A "?" matches one character, however many bytes it takes."""
    assert matching(case) == case.matches


# Nothing is tidied up, so these can never match a path relative to the ignore-file's
# directory. They're still translated like any other glob.
NEVER_MATCHES = [
    param(
        GlobCase(glob="/a", matches=[], misses=["a"]),
        id="leading-slash",
    ),
    param(
        GlobCase(glob="a//b", matches=[], misses=["a/b"]),
        id="double-slash",
    ),
    param(
        GlobCase(glob="./a", matches=[], misses=["a"]),
        id="dot-segment",
    ),
]


@mark.parametrize("case", NEVER_MATCHES)
def test_translate_glob__never_matches(case: GlobCase) -> None:
    """A glob that can never match a relative path is still translated."""
    assert translate_glob(case.glob) is not None
    assert matching(case) == case.matches


MALFORMED = [
    param(
        GlobCase(glob="a\\", matches=[], misses=["a", "a\\"]),
        id="trailing-backslash",
    ),
    param(
        GlobCase(glob="a\\\\\\", matches=[], misses=["a", "a\\", "a\\\\"]),
        id="escaped-then-trailing-backslash",
    ),
    param(
        GlobCase(glob="[a", matches=[], misses=["[a", "a"]),
        id="unterminated-bracket",
    ),
]


@mark.parametrize("case", MALFORMED)
def test_translate_glob__malformed(case: GlobCase) -> None:
    """A glob with an unescaped "[", or a lone backslash at the end, gives `None`."""
    assert translate_glob(case.glob) is None


# If each "*" were translated plainly, each of these would take 3-6 seconds to fail on
# Python 3.11 to 3.14 on arm64 macOS, because the regular expression engine would try
# every way to share the name between the "*".
TIMING = [
    param(
        GlobCase(glob="*a" * 7 + "*b", matches=[], misses=["a" * 60]),
        id="letters",
    ),
    param(
        GlobCase(glob="*a?" * 8 + "*b", matches=[], misses=["a" * 54]),
        id="question-marks-in-text",
    ),
    param(
        GlobCase(glob="*?" * 8 + "*b", matches=[], misses=["a" * 48]),
        id="question-marks",
    ),
    param(
        GlobCase(glob="*a" * 8, matches=[], misses=["a" * 49 + "b/a"]),
        id="slash-near-the-end",
    ),
    param(
        GlobCase(glob="*ab" * 12 + "*abc", matches=[], misses=["ab" * 30 + "abd"]),
        id="almost-matches",
    ),
]


@mark.skipif(
    sys.platform == "win32",
    reason="Windows has no alarm signal to interrupt a slow match",
)
@mark.parametrize("case", TIMING)
def test_translate_glob__timing(case: GlobCase) -> None:
    """Globs that could stall a walk match in under a second."""
    # `signal.setitimer` doesn't exist on Windows. This assertion convinces Pyright that
    # we won't call it when we're running on Windows.
    assert sys.platform != "win32"

    # If matching takes a second, the alarm interrupts it, and the test fails rather
    # than waits.
    def interrupt(signum: int, frame: FrameType | None) -> None:
        raise TimeoutError("Took over a second to match")

    previous = signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, 1)

    try:
        assert matching(case) == case.matches
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@needs_git
@mark.parametrize(
    "case",
    [
        *LITERALS,
        *ESCAPES,
        *QUESTION_MARKS,
        *ASTERISKS,
        *NON_ASCII,
        *NEVER_MATCHES,
        *MALFORMED,
        *TIMING,
    ],
)
def test_translate_glob__git(tmp_path: Path, case: GlobCase) -> None:
    """Git ignores the paths that the glob matches, and lists the rest."""
    paths = [*case.matches, *case.misses]

    skip_if_windows_cannot_create(paths)

    # A "/" at the start anchors the line, so Git matches the glob against each path
    # from the root, as the rows do.
    line = format_pattern((case.glob, False, False, True))

    # The ignore-file isn't one of the row's paths, so we leave it out, whether or not
    # the glob matches it.
    listed = [
        path
        for path in list_files(tmp_path / "tree", paths, [line])
        if path != "ignore"
    ]

    if case.divergence:
        # Git should still list something different, or the reason no longer holds.
        assert listed != case.misses
        skip(case.divergence)

    assert listed == case.misses
