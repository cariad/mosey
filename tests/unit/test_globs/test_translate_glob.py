"""Unit tests for the `translate_glob` function."""

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


ONE_BYTE = 'Git\'s "?" and "[...]" match one byte, and Mosey\'s match one character'
"""Why Git matches some non-ASCII names differently."""


def matching(case: GlobCase) -> list[str]:
    """Return the paths in a case that its glob matches.

    Args:
        case: The case to check.

    Returns:
        The paths, from both `matches` and `misses`, that the glob matches, in order.
    """
    source = translate_glob(case.glob)

    # Only a malformed glob gives `None`, and `test_translate_glob__malformed` checks
    # those without calling this. So a row that matches nothing can't pass just because
    # its glob wasn't translated.
    assert source is not None

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


BRACKETS = [
    param(
        GlobCase(glob="[ab]", matches=["a", "b"], misses=["[ab]", "ab", "c"]),
        id="set",
    ),
    param(
        GlobCase(glob="[ab][cd]", matches=["ac", "bd"], misses=["a", "ab", "cd"]),
        id="several-sets",
    ),
    param(
        GlobCase(glob="*[ab]*", matches=["a", "xby"], misses=["xcy"]),
        id="set-between-stars",
    ),
    param(
        GlobCase(glob="[!ab]", matches=["c"], misses=["a", "b"]),
        id="negated-with-exclamation-mark",
    ),
    param(
        GlobCase(glob="[^ab]", matches=["c"], misses=["a", "b"]),
        id="negated-with-caret",
    ),
    # Only a "!" or "^" straight after the "[" negates.
    param(
        GlobCase(glob="[a!]", matches=["!", "a"], misses=["b"]),
        id="exclamation-mark-later",
    ),
    param(
        GlobCase(glob="[!^]", matches=["!", "a"], misses=["^"]),
        id="caret-after-exclamation-mark",
    ),
    param(
        GlobCase(glob="[\\!a]", matches=["!", "a"], misses=["b"]),
        id="escaped-exclamation-mark",
    ),
    # A "]" first in the set is a member, not the end.
    param(
        GlobCase(glob="[]a]", matches=["]", "a"], misses=["b"]),
        id="close-first",
    ),
    param(
        GlobCase(glob="[!]a]", matches=["b"], misses=["]", "a"]),
        id="negated-close-first",
    ),
    param(
        GlobCase(glob="[\\]]", matches=["]"], misses=["a"]),
        id="escaped-close",
    ),
    # A backslash never starts a regular expression's escape, so "\d" is the letter "d"
    # and not any digit.
    param(
        GlobCase(glob="[\\d]", matches=["d"], misses=["1", "\\"]),
        id="escaped-letter-in-set",
    ),
    param(
        GlobCase(glob="[*?]", matches=["*", "?"], misses=["a"]),
        id="wildcards-in-set",
    ),
    # A "[" that doesn't start a class is a member.
    param(
        GlobCase(glob="[[]", matches=["["], misses=["a"]),
        id="open-bracket-in-set",
    ),
    param(
        GlobCase(glob="[[:a]", matches=["[", "a"], misses=["b"]),
        id="open-bracket-and-colon",
    ),
    # A class needs a second ":" before its "]", so this is the set "[" and ":".
    param(
        GlobCase(glob="[[:]", matches=["["], misses=["]", "a"]),
        id="class-needs-two-colons",
    ),
    # And it needs a ":" straight after the "[", so this is the set "[", "a" and ":".
    param(
        GlobCase(glob="[[a:]", matches=["[", "a"], misses=["b"]),
        id="class-needs-colon-first",
    ),
    # "[:" starts a class only if the next "]" comes straight after another ":". Here
    # it's escaped, so this is the set "[", ":", "a", "]" and "b", followed by a "]".
    param(
        GlobCase(
            glob="[[:a\\]b:]]",
            matches=["[]", "]]", "a]", "b]"],
            misses=["a", "c]"],
        ),
        id="class-ends-at-escaped-close",
    ),
    param(
        GlobCase(glob="[\\[:digit:]]", matches=["[]", "d]"], misses=["1]", "d"]),
        id="escaped-open-bracket",
    ),
    # Only "[:" starts a class, so this is the set "[", "=" and "a", then a "]".
    param(
        GlobCase(glob="[[=a=]]", matches=["=]", "[]", "a]"], misses=["=", "a"]),
        id="equals-signs",
    ),
    # A bracket expression never matches "/", whatever it holds.
    param(
        GlobCase(glob="a[/]b", matches=[], misses=["a/b", "a[/]b"]),
        id="slash-in-set",
    ),
    param(
        GlobCase(
            glob="a[.-0]b",
            matches=["a.b", "a0b"],
            misses=["a-b", "a/b", "a1b"],
        ),
        id="range-across-slash",
    ),
    param(
        GlobCase(glob="a[!x]b", matches=["ayb"], misses=["a/b", "axb"]),
        id="negated-set-and-slash",
    ),
    param(
        GlobCase(glob="a[[:punct:]]b", matches=["a!b", "a.b"], misses=["a/b", "axb"]),
        id="class-and-slash",
    ),
    param(
        GlobCase(glob="a[[:graph:]]b", matches=["a.b"], misses=["a b", "a/b"]),
        id="graph-and-slash",
    ),
    param(
        GlobCase(glob="a[[:print:]]b", matches=["a b", "a.b"], misses=["a/b"]),
        id="print-and-slash",
    ),
    param(
        GlobCase(glob="a[![:alpha:]]b", matches=["a1b"], misses=["a/b", "axb"]),
        id="negated-class-and-slash",
    ),
]


@mark.parametrize("case", BRACKETS)
def test_translate_glob__brackets(case: GlobCase) -> None:
    """A bracket expression matches one character from a set, and never "/"."""
    assert matching(case) == case.matches


RANGES = [
    param(
        GlobCase(glob="[b-d]", matches=["b", "c", "d"], misses=["a", "e"]),
        id="range",
    ),
    param(
        GlobCase(glob="[\\b-\\d]", matches=["b", "c", "d"], misses=["a", "e"]),
        id="escaped-ends",
    ),
    param(
        GlobCase(glob="[A-\\]]", matches=["B", "[", "]"], misses=["-", "^"]),
        id="range-to-escaped-close",
    ),
    param(
        GlobCase(glob="[a\\-c]", matches=["-", "a", "c"], misses=["b"]),
        id="escaped-dash",
    ),
    param(
        GlobCase(glob="[a-c[:digit:]]", matches=["1", "b"], misses=["d"]),
        id="range-then-class",
    ),
    # A "-" first or last in the set is a member.
    param(
        GlobCase(glob="[-a]", matches=["-", "a"], misses=["b"]),
        id="dash-first",
    ),
    param(
        GlobCase(glob="[!-a]", matches=["b"], misses=["-", "a"]),
        id="negated-dash-first",
    ),
    param(
        GlobCase(glob="[-[:digit:]]", matches=["-", "1"], misses=["a"]),
        id="dash-before-class",
    ),
    param(
        GlobCase(glob="[a-]", matches=["-", "a"], misses=["b"]),
        id="dash-last",
    ),
    # So is a "-" straight after a range or a class.
    param(
        GlobCase(glob="[a-c-e]", matches=["-", "a", "b", "c", "e"], misses=["d"]),
        id="dash-after-range",
    ),
    param(
        GlobCase(glob="[[:digit:]-z]", matches=["-", "1", "z"], misses=["y"]),
        id="dash-after-class",
    ),
    # Like any other member, such a "-" can start a range.
    param(
        GlobCase(
            glob="a[--0]b",
            matches=["a-b", "a.b", "a0b"],
            misses=["a,b", "a/b", "a1b"],
        ),
        id="range-from-dash",
    ),
    param(
        GlobCase(
            glob="[a-c--e]",
            matches=["-", "0", "A", "_", "b", "e"],
            misses=[",", "f"],
        ),
        id="range-from-dash-after-range",
    ),
    # A range whose ends are the wrong way round matches only its first character.
    param(
        GlobCase(glob="[y-a]", matches=["y"], misses=["a", "b", "z"]),
        id="backwards",
    ),
    param(
        GlobCase(glob="[y-ab]", matches=["b", "y"], misses=["a", "z"]),
        id="backwards-then-member",
    ),
    param(
        GlobCase(glob="[a-\\]]", matches=["a"], misses=["]", "b"]),
        id="backwards-to-escaped-close",
    ),
    # The character after a "-" always ends the range, even a "[". So this is "a" (from
    # a backwards range), ":", "d", "i", "g" and "t", then a "]".
    param(
        GlobCase(
            glob="[a-[:digit:]]",
            matches=["a]", "d]"],
            misses=["1]", "_]", "a"],
        ),
        id="range-to-open-bracket",
    ),
    # A "]" first in the set can start a range too.
    param(
        GlobCase(
            glob="[]-a]",
            matches=["]", "^", "_", "`", "a"],
            misses=["[", "b"],
        ),
        id="range-from-close",
    ),
]


@mark.parametrize("case", RANGES)
def test_translate_glob__ranges(case: GlobCase) -> None:
    """A "-" between two members of a bracket expression makes a range."""
    assert matching(case) == case.matches


ASCII = [chr(code) for code in range(1, 128) if chr(code) != "/"]
"""Every ASCII character that a name can hold."""

# The ASCII characters that the classes are made of. The punctuation leaves out "/",
# since no name can hold one.
DIGITS = "0123456789"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
PUNCTUATION = "!\"#$%&'()*+,-.:;<=>?@[\\]^_`{|}~"
CONTROL = "".join(chr(code) for code in [*range(32), 127])


def ascii_case(bracket: str, members: str) -> GlobCase:
    """Return a case for a bracket expression against every ASCII character.

    Each name is a character followed by its code, like "A065", so that no two names
    differ only in case. The glob is the bracket expression followed by "*", so it
    matches the names that start with a member. It also tries U+FF11, a full-width
    "1", since no class holds a character that isn't ASCII.

    Args:
        bracket: The bracket expression.
        members: The characters it matches.

    Returns:
        The case.
    """
    characters = [*ASCII, "\uff11"]
    names = [f"{character}{ord(character):03}" for character in characters]

    return GlobCase(
        glob=bracket + "*",
        matches=[name for name in names if name[0] in members],
        misses=[name for name in names if name[0] not in members],
    )


CLASSES = [
    param(ascii_case("[[:alnum:]]", DIGITS + UPPER + LOWER), id="alnum"),
    param(ascii_case("[[:alpha:]]", UPPER + LOWER), id="alpha"),
    param(ascii_case("[[:blank:]]", "\t "), id="blank"),
    param(ascii_case("[[:cntrl:]]", CONTROL), id="cntrl"),
    param(ascii_case("[[:digit:]]", DIGITS), id="digit"),
    param(ascii_case("[[:graph:]]", DIGITS + UPPER + LOWER + PUNCTUATION), id="graph"),
    param(ascii_case("[[:lower:]]", LOWER), id="lower"),
    param(
        ascii_case("[[:print:]]", " " + DIGITS + UPPER + LOWER + PUNCTUATION),
        id="print",
    ),
    param(ascii_case("[[:punct:]]", PUNCTUATION), id="punct"),
    # Not vertical tab or form feed.
    param(ascii_case("[[:space:]]", "\t\n\r "), id="space"),
    param(ascii_case("[[:upper:]]", UPPER), id="upper"),
    param(ascii_case("[[:xdigit:]]", DIGITS + "ABCDEF" + "abcdef"), id="xdigit"),
]


@mark.parametrize("case", CLASSES)
def test_translate_glob__classes(case: GlobCase) -> None:
    """A class in a bracket expression matches its ASCII characters."""
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
    # "caf[é]" spells "é" as the single character U+00E9, which takes two bytes.
    param(
        GlobCase(
            glob="caf[é]",
            matches=["café"],
            misses=["cafe"],
            divergence=ONE_BYTE,
        ),
        id="composed-bracket",
    ),
    param(
        GlobCase(
            glob="caf[!x]",
            matches=["cafe", "café"],
            misses=["cafex", "cafx"],
            divergence=ONE_BYTE,
        ),
        id="composed-negated-bracket",
    ),
    # The name spells "é" as "e" followed by U+0301, a combining accent. Names are
    # never normalised, so the bracket expression matches the "e", and the accent is
    # left over.
    param(
        GlobCase(glob="caf[eé]", matches=["cafe"], misses=["cafe\u0301"]),
        id="decomposed-bracket",
    ),
    param(
        GlobCase(
            glob="caf[!x][!x]",
            matches=["cafe\u0301"],
            misses=["cafe", "cafex"],
            divergence=ONE_BYTE,
        ),
        id="decomposed-negated-brackets",
    ),
]


@mark.parametrize("case", NON_ASCII)
def test_translate_glob__non_ascii(case: GlobCase) -> None:
    """A "?" or a bracket matches one character, however many bytes it takes."""
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
    # A "]" first in the set is a member, so nothing closes these.
    param(
        GlobCase(glob="[]", matches=[], misses=["[]", "]"]),
        id="empty-set",
    ),
    param(
        GlobCase(glob="[!]", matches=[], misses=["!", "[!]"]),
        id="empty-negated-set",
    ),
    # A backslash at the very end has nothing to escape, so nothing closes these either.
    param(
        GlobCase(glob="[a\\", matches=[], misses=["a"]),
        id="trailing-backslash-in-set",
    ),
    param(
        GlobCase(glob="[a-\\", matches=[], misses=["a"]),
        id="trailing-backslash-in-range",
    ),
    # The class's "]" doesn't close the set.
    param(
        GlobCase(glob="[[:alpha:]", matches=[], misses=["[", "a"]),
        id="class-left-open",
    ),
    # An unknown class breaks the glob, even though a "]" closes the set.
    param(
        GlobCase(glob="[[:foo:]]", matches=[], misses=["[", "f", "f]"]),
        id="unknown-class",
    ),
    param(
        GlobCase(glob="[[:ALPHA:]]", matches=[], misses=["A", "A]"]),
        id="class-in-wrong-case",
    ),
    param(
        GlobCase(glob="[[::]]", matches=[], misses=["[]", "]"]),
        id="class-without-a-name",
    ),
    # A backslash in a class's name is part of the name.
    param(
        GlobCase(glob="[[:alpha\\:]]", matches=[], misses=["a"]),
        id="backslash-in-class-name",
    ),
    # An unknown class breaks the glob even beside a member that matches, or negated.
    param(
        GlobCase(glob="[a[:foo:]]", matches=[], misses=["a", "a]"]),
        id="unknown-class-beside-member",
    ),
    param(
        GlobCase(glob="[![:foo:]]", matches=[], misses=["a", "a]"]),
        id="negated-unknown-class",
    ),
]


@mark.parametrize("case", MALFORMED)
def test_translate_glob__malformed(case: GlobCase) -> None:
    """An unclosed "[", an unknown class or a trailing lone backslash gives `None`."""
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
    param(
        GlobCase(glob="*[ab]" * 7 + "*c", matches=[], misses=["a" * 58]),
        id="brackets",
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
        *BRACKETS,
        *RANGES,
        *CLASSES,
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
