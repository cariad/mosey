"""Unit tests for the `check_pattern` function."""

import random

from pytest import mark, param, raises

from mosey.ignore_files import split_ignore_file
from mosey.paths import FS_ENCODING
from mosey.patterns import check_pattern
from mosey.rules import compile_rules
from tests.random_trees import Draft, random_line


def accepted_lines(count: int) -> list[str]:
    """Return random lines for an ignore-file that `check_pattern` accepts.

    The same lines are returned on every run, on every operating system.

    Args:
        count: How many different lines to return.

    Returns:
        The lines.
    """
    rng = random.Random("check_pattern")
    patterns: dict[str, None] = {}

    while len(patterns) < count:
        draft = Draft(rng)
        draft.add_entries()

        # Some lines name directories beneath the ignore-file's that hold another, so
        # every directory gets one.
        draft.lines = {directory: [] for directory in draft.directories}

        for _ in range(50):
            line = random_line(draft, rng.choice(draft.directories))

            try:
                check_pattern(line)
            except ValueError:
                continue

            patterns[line] = None

    return list(patterns)[:count]


def assert_same_as_ignore_file(pattern: str) -> None:
    """Check that an ignore-file reads a line holding the pattern exactly as it is.

    Args:
        pattern: The pattern, which `check_pattern` accepts.
    """
    # Reading an ignore-file removes a byte order mark from the start of the file, but
    # not from any other line, so the pattern goes on the second line. Any bytes at its
    # start that spell a byte order mark are then kept, as they are in code.
    for ending in ("\n", "\r\n"):
        text = f"a{ending}{pattern}{ending}"
        data = text.encode(FS_ENCODING, "surrogateescape")
        assert split_ignore_file(data) == ["a", pattern]

    # A pattern with nothing left to match, or a broken glob, compiles to nothing.
    assert compile_rules([pattern]) is not None


ACCEPTED = [
    param("*.pdf", id="extension"),
    param("docs/todo.txt", id="path"),
    param("/todo.txt", id="anchored"),
    param("notes/", id="directory"),
    param("!build/", id="negated-directory"),
    param("*", id="asterisk"),
    param("**", id="double-asterisk"),
    param("/**", id="anchored-double-asterisk"),
    param("**/", id="double-asterisk-directory"),
    param("[[:alpha:]]", id="class"),
    # Only a "#" at the very start makes a comment.
    param("\\#a", id="escaped-hash"),
    param("!#a", id="negated-hash"),
    param(" #a", id="space-before-hash"),
    param("!!a", id="negated-exclamation-mark"),
    param("/!a", id="exclamation-mark-after-slash"),
    param("\\!a", id="escaped-exclamation-mark"),
    # Trailing spaces are removed, as an ignore-file removes them, unless one is
    # escaped. Other trailing whitespace is kept.
    param("a.log ", id="trailing-space"),
    param("a\\ ", id="escaped-space"),
    param("\\ ", id="only-an-escaped-space"),
    param("a\t", id="trailing-tab"),
    # Only a carriage return at the very end is refused. One before a trailing space
    # stays, because an ignore-file removes the space but keeps the carriage return.
    param("a\rb", id="carriage-return-inside"),
    param("a\r ", id="carriage-return-before-space"),
    param("Icon[\r]", id="carriage-return-in-brackets"),
    # A backslash escapes the characters that mean something in a glob. Backslashes
    # escape each other in pairs, so the letter after a pair isn't escaped.
    param("a\\\\b", id="escaped-backslash"),
    param("\\\\a", id="escaped-backslash-before-letter"),
    param("docs\\*.md", id="escaped-asterisk"),
    param("\\[abc].txt", id="escaped-bracket"),
    param("[a\\]]", id="escaped-closing-bracket"),
    param("[a\\-z]", id="escaped-hyphen"),
    param("[\\^a]", id="escaped-caret"),
    # A bracket never matches "/", and a range written backwards only matches its first
    # character, but neither is broken.
    param("a[/]b", id="slash-in-brackets"),
    param("[z-a]", id="backwards-range"),
    param("café", id="non-ascii"),
    param("cafe\u0301", id="decomposed"),
    # A byte that isn't UTF-8, which an ignore-file can hold too.
    param("caf\udce9", id="undecodable-byte"),
    # Only a segment that's exactly "." or ".." is refused.
    param("...", id="three-dots"),
    param(".a", id="leading-dot"),
]


@mark.parametrize("pattern", ACCEPTED)
def test_check_pattern(pattern: str) -> None:
    """`None` is returned for a pattern that an ignore-file would read the same way."""
    assert check_pattern(pattern) is None


BACKSLASHES = [
    param("build\\out", "o", id="windows-path"),
    param("\\a", "a", id="start"),
    param("a\\B", "B", id="upper-case"),
    param("a\\1", "1", id="digit"),
    param("a\\é", "é", id="non-ascii-letter"),
    param("!\\a", "a", id="negated"),
    param("[\\a]", "a", id="in-brackets"),
    # Backslashes escape each other in pairs, so the third one escapes the "a".
    param("\\\\\\a", "a", id="after-a-pair"),
    param("a\\b\\c", "b", id="first-of-two"),
    param("build\\.cache", ".", id="windows-path-dot"),
    param("src\\__pycache__", "_", id="windows-path-underscore"),
    param("*\\.log", ".", id="dot"),
    param("[\\.]", ".", id="dot-in-brackets"),
    param("node_modules\\@types", "@", id="windows-path-at-sign"),
    param("C:\\$Recycle.Bin", "$", id="windows-path-dollar"),
    param("docs\\~$report.docx", "~", id="windows-path-tilde"),
    param("a\\/b", "/", id="slash"),
    param("a\\/", "/", id="trailing-slash"),
]


@mark.parametrize(("pattern", "escaped"), BACKSLASHES)
def test_check_pattern__backslash(pattern: str, escaped: str) -> None:
    """`ValueError` is raised when a backslash comes before what it doesn't escape."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == (
        f"{pattern!r} has a backslash before {escaped!r}, which escapes nothing"
    )


BROKEN = [
    param("[abc.txt", id="unclosed-bracket"),
    param("[]", id="empty-bracket"),
    param("[[:letter:]]", id="unknown-class"),
    param("[[:alpha:]", id="unclosed-class"),
    param("notes\\", id="trailing-backslash"),
    param("\\", id="only-a-backslash"),
    param("![a", id="negated"),
]


@mark.parametrize("pattern", BROKEN)
def test_check_pattern__broken(pattern: str) -> None:
    """`ValueError` is raised when the pattern's glob is broken."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} is broken, so never matches"


BYTE_ORDER_MARKS = [
    param("\ufeffa", id="start"),
    param("\ufeff", id="only-a-byte-order-mark"),
    param("\ufeff!a", id="before-exclamation-mark"),
]


@mark.parametrize("pattern", BYTE_ORDER_MARKS)
def test_check_pattern__byte_order_mark(pattern: str) -> None:
    """`ValueError` is raised when the pattern starts with a byte order mark."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} starts with a byte order mark"


CARRIAGE_RETURNS = [
    param("a\r", id="end"),
    param("\r", id="only-a-carriage-return"),
    # Finder's hidden "Icon" file ends with a carriage return, and "Icon[\r]" matches
    # it instead.
    param("Icon\r", id="finder-icon"),
    param("a \r", id="after-space"),
    param("a/\r", id="after-slash"),
    # An ignore-file only removes one, so it would read this as "a\r".
    param("a\r\r", id="two"),
]


@mark.parametrize("pattern", CARRIAGE_RETURNS)
def test_check_pattern__carriage_return(pattern: str) -> None:
    """`ValueError` is raised when the pattern ends with a carriage return."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} ends with a carriage return"


COMMENTS = [
    param("#notes", id="hash"),
    param("#", id="only-a-hash"),
    param("# a", id="hash-then-space"),
    param("#!a", id="hash-then-exclamation-mark"),
]


@mark.parametrize("pattern", COMMENTS)
def test_check_pattern__comment(pattern: str) -> None:
    """`ValueError` is raised when the pattern starts with a "#"."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} would be a comment"


# Each row has two reasons, and the error gives whichever comes first in the order of
# the tests above. No pattern starts with both a "#" and a byte order mark, and a
# pattern with nothing left to match has no other reason, so those reasons never meet.
FIRST_REASON = [
    param(
        "\x00\n",
        "holds a line break",
        id="line-break-before-null",
    ),
    param(
        "#\x00",
        "holds a null character",
        id="null-before-comment",
    ),
    param(
        "\ufeff\x00",
        "holds a null character",
        id="null-before-byte-order-mark",
    ),
    param(
        "#a\r",
        "would be a comment",
        id="comment-before-carriage-return",
    ),
    param(
        "\ufeffa\r",
        "starts with a byte order mark",
        id="byte-order-mark-before-carriage-return",
    ),
    param(
        "\\a\r",
        "ends with a carriage return",
        id="carriage-return-before-backslash",
    ),
    param(
        "./\\a",
        "has a backslash before 'a', which escapes nothing",
        id="backslash-before-segment",
    ),
    param(
        "[\\a",
        "has a backslash before 'a', which escapes nothing",
        id="backslash-before-broken",
    ),
    param(
        "./[a",
        'has an empty, "." or ".." segment, so never matches',
        id="segment-before-broken",
    ),
]


@mark.parametrize(("pattern", "reason"), FIRST_REASON)
def test_check_pattern__first_reason(pattern: str, reason: str) -> None:
    """When a pattern is refused for more than one reason, only the first is given."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} {reason}"


LINE_BREAKS = [
    param("a\nb", id="inside"),
    param("\na", id="start"),
    param("a\n", id="end"),
    param("\n", id="only-a-line-break"),
    # A Windows line ending ends with a line break, not a carriage return.
    param("a\r\n", id="windows-line-ending"),
]


@mark.parametrize("pattern", LINE_BREAKS)
def test_check_pattern__line_break(pattern: str) -> None:
    """`ValueError` is raised when the pattern holds a line break."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} holds a line break"


NOTHING_LEFT = [
    param("", id="empty"),
    param("   ", id="only-spaces"),
    param("!", id="only-an-exclamation-mark"),
    param("/", id="only-a-slash"),
    param("!/", id="exclamation-mark-and-slash"),
    param("//", id="only-slashes"),
    # Trailing spaces are removed first, as an ignore-file removes them.
    param("! ", id="exclamation-mark-and-space"),
]


@mark.parametrize("pattern", NOTHING_LEFT)
def test_check_pattern__nothing_left(pattern: str) -> None:
    """`ValueError` is raised when nothing is left of the pattern to match."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} has nothing to match"


NULLS = [
    param("a\x00b", id="inside"),
    param("\x00a", id="start"),
    param("a\x00", id="end"),
    param("\x00", id="only-a-null"),
]


@mark.parametrize("pattern", NULLS)
def test_check_pattern__null(pattern: str) -> None:
    """`ValueError` is raised when the pattern holds a null character."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == f"{pattern!r} holds a null character"


@mark.parametrize("pattern", ACCEPTED)
def test_check_pattern__same_as_ignore_file(pattern: str) -> None:
    """An accepted pattern means exactly what it means in an ignore-file."""
    assert_same_as_ignore_file(pattern)


def test_check_pattern__same_as_ignore_file__random() -> None:
    """Every accepted random line means exactly what it means in an ignore-file."""
    for pattern in accepted_lines(3000):
        assert_same_as_ignore_file(pattern)


SEGMENTS = [
    param("./todo.txt", id="leading-dot"),
    param("a/./b", id="dot-inside"),
    param("a/.", id="trailing-dot"),
    param(".", id="only-a-dot"),
    param("./", id="dot-directory"),
    param("../a", id="leading-dot-dot"),
    param("a/../b", id="dot-dot-inside"),
    param("a/..", id="trailing-dot-dot"),
    param("..", id="only-two-dots"),
    param("docs//todo.txt", id="empty-inside"),
    # Only one "/" at the start is removed, which leaves the other.
    param("//a", id="empty-at-start"),
    # Only one "/" at the end means directories only, which leaves the other.
    param("a//", id="empty-at-end"),
    param("!./a", id="negated"),
]


@mark.parametrize("pattern", SEGMENTS)
def test_check_pattern__segment(pattern: str) -> None:
    """`ValueError` is raised when the pattern has an empty, "." or ".." segment."""
    with raises(ValueError) as raised:
        check_pattern(pattern)

    assert str(raised.value) == (
        f'{pattern!r} has an empty, "." or ".." segment, so never matches'
    )
