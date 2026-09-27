"""Unit tests for the `patterns` module."""

import sys
from pathlib import Path
from typing import NamedTuple

from pytest import mark, param, skip

from mosey.patterns import Pattern, parse_pattern
from tests.file_system_helpers import make_tree, windows_can_create
from tests.git_oracle import git_list_files
from tests.markers import needs_git


class PatternCase(NamedTuple):
    """A line, the pattern it parses to, and the files Git lists because of it."""

    line: str
    """The line to parse."""

    expect: Pattern | None
    """The pattern that the line parses to, or `None` if nothing is left to match."""

    tree: list[str]
    """Files and directories to create, as `make_tree` takes them."""

    listed: list[str]
    """The files Git lists, in order, when the root's ignore-file holds the line."""

    before: str | None = None
    """A line to put before `line`, so that a negation has something to re-include."""


def format_pattern(pattern: Pattern) -> str:
    """Return an ignore-file line that means the same as a pattern.

    Every space in the glob is escaped, so none can be trimmed from the end of the line.
    A pattern that wrongly kept a trailing space then matches differently, rather than
    being trimmed back into the right one.

    Args:
        pattern: The pattern to write as a line.

    Returns:
        The line.
    """
    glob, negated, directory_only, anchored = pattern
    characters = iter(glob)
    escaped = ""

    for character in characters:
        if character == "\\":
            # Keep an escape as it is, along with the character it escapes.
            escaped += character + next(characters, "")
        elif character == " ":
            escaped += "\\ "
        else:
            escaped += character

    prefix = ("!" if negated else "") + ("/" if anchored else "")
    return prefix + escaped + ("/" if directory_only else "")


def list_files(root: Path, tree: list[str], lines: list[str]) -> list[str]:
    """Create a tree with an ignore-file, and return the files Git lists beneath it.

    Args:
        root: Path to the directory to create the tree in.
        tree: Files and directories to create, as `make_tree` takes them.
        lines: Lines to write to the ignore-file, named "ignore", in the root.

    Returns:
        The files Git lists, in order.
    """
    root.mkdir()
    make_tree(root, *tree)
    (root / "ignore").write_bytes("".join(f"{line}\n" for line in lines).encode())
    return git_list_files(root, "ignore")


TRAILING_SPACES = [
    param(
        PatternCase(
            line="a ",
            expect=("a", False, False, False),
            tree=["a", "b", "sub/a"],
            listed=["b", "ignore"],
        ),
        id="one-space",
    ),
    param(
        PatternCase(
            line="a  ",
            expect=("a", False, False, False),
            tree=["a", "b", "sub/a"],
            listed=["b", "ignore"],
        ),
        id="several-spaces",
    ),
    param(
        PatternCase(
            line="a\\ ",
            expect=("a\\ ", False, False, False),
            tree=["a", "a ", "sub/a "],
            listed=["a", "ignore"],
        ),
        id="escaped-space",
    ),
    # Windows can't create "a ", so this checks the same line there without it.
    param(
        PatternCase(
            line="a\\ ",
            expect=("a\\ ", False, False, False),
            tree=["a"],
            listed=["a", "ignore"],
        ),
        id="escaped-space-without-a-space-name",
    ),
    param(
        PatternCase(
            line="a\\  ",
            expect=("a\\ ", False, False, False),
            tree=["a ", "a  ", "sub/a "],
            listed=["a  ", "ignore"],
        ),
        id="escaped-then-unescaped-space",
    ),
    # Backslashes escape each other in pairs, so two leave the space unescaped, and the
    # glob matches the name "a\".
    param(
        PatternCase(
            line="a\\\\ ",
            expect=("a\\\\", False, False, False),
            tree=["a\\", "a\\ ", "sub/a\\"],
            listed=["a\\ ", "ignore"],
        ),
        id="two-backslashes",
    ),
    param(
        PatternCase(
            line="a\\\\\\ ",
            expect=("a\\\\\\ ", False, False, False),
            tree=["a\\", "a\\ ", "sub/a\\ "],
            listed=["a\\", "ignore"],
        ),
        id="three-backslashes",
    ),
    # Only the backslashes right before the spaces count.
    param(
        PatternCase(
            line="\\#a ",
            expect=("\\#a", False, False, False),
            tree=["#a", "b", "sub/#a"],
            listed=["b", "ignore"],
        ),
        id="backslash-earlier-in-the-line",
    ),
    param(
        PatternCase(
            line="\\ ",
            expect=("\\ ", False, False, False),
            tree=[" ", "a", "sub/ "],
            listed=["a", "ignore"],
        ),
        id="only-an-escaped-space",
    ),
    param(
        PatternCase(
            line="a\t",
            expect=("a\t", False, False, False),
            tree=["a", "a\t", "sub/a\t"],
            listed=["a", "ignore"],
        ),
        id="tab",
    ),
    param(
        PatternCase(
            line=" a",
            expect=(" a", False, False, False),
            tree=[" a", "a", "sub/ a"],
            listed=["a", "ignore"],
        ),
        id="leading-space",
    ),
]


@mark.parametrize("case", TRAILING_SPACES)
def test_parse_pattern__trailing_spaces(case: PatternCase) -> None:
    """Trailing spaces are removed, unless a backslash escapes one."""
    assert parse_pattern(case.line) == case.expect


NEGATION = [
    param(
        PatternCase(
            line="!a",
            expect=("a", True, False, False),
            tree=["a", "ab", "sub/a"],
            listed=["a", "ignore", "sub/a"],
            before="a*",
        ),
        id="negated",
    ),
    param(
        PatternCase(
            line="!!a",
            expect=("!a", True, False, False),
            tree=["!a", "a", "sub/!a"],
            listed=["!a", "ignore", "sub/!a"],
            before="*a",
        ),
        id="negated-twice",
    ),
    param(
        PatternCase(
            line=" !a",
            expect=(" !a", False, False, False),
            tree=[" !a", "a", "sub/ !a"],
            listed=["a", "ignore"],
        ),
        id="space-before-exclamation-mark",
    ),
    param(
        PatternCase(
            line="! a",
            expect=(" a", True, False, False),
            tree=[" a", "a", "sub/ a"],
            listed=[" a", "ignore", "sub/ a"],
            before="*a",
        ),
        id="space-after-exclamation-mark",
    ),
    # Only a "#" at the very start of a line makes a comment.
    param(
        PatternCase(
            line="!#a",
            expect=("#a", True, False, False),
            tree=["#a", "a", "sub/#a"],
            listed=["#a", "ignore", "sub/#a"],
            before="*a",
        ),
        id="negated-hash",
    ),
]


@mark.parametrize("case", NEGATION)
def test_parse_pattern__negation(case: PatternCase) -> None:
    """A "!" at the very start negates the pattern."""
    assert parse_pattern(case.line) == case.expect


ESCAPES = [
    param(
        PatternCase(
            line="\\!a",
            expect=("\\!a", False, False, False),
            tree=["!a", "a", "sub/!a"],
            listed=["a", "ignore"],
        ),
        id="escaped-exclamation-mark",
    ),
    param(
        PatternCase(
            line="\\#a",
            expect=("\\#a", False, False, False),
            tree=["#a", "a", "sub/#a"],
            listed=["a", "ignore"],
        ),
        id="escaped-hash",
    ),
]


@mark.parametrize("case", ESCAPES)
def test_parse_pattern__escapes(case: PatternCase) -> None:
    """Escaped characters keep their backslash."""
    assert parse_pattern(case.line) == case.expect


DIRECTORY_ONLY = [
    param(
        PatternCase(
            line="a/",
            expect=("a", False, True, False),
            tree=["a/f", "sub/a", "x/y/a/g"],
            listed=["ignore", "sub/a"],
        ),
        id="directory-only",
    ),
    param(
        PatternCase(
            line="a//",
            expect=("a/", False, True, True),
            tree=["a/f", "b"],
            listed=["a/f", "b", "ignore"],
        ),
        id="two-trailing-slashes",
    ),
    param(
        PatternCase(
            line="a/ ",
            expect=("a", False, True, False),
            tree=["a/f", "sub/a", "x/a/g"],
            listed=["ignore", "sub/a"],
        ),
        id="trailing-slash-then-space",
    ),
    # The space isn't at the end of the line, so it's kept.
    param(
        PatternCase(
            line="a /",
            expect=("a ", False, True, False),
            tree=["a /f", "a/f", "sub/a /g"],
            listed=["a/f", "ignore"],
        ),
        id="space-then-trailing-slash",
    ),
    # The glob "a\" is left with a backslash that escapes nothing, so it never matches.
    param(
        PatternCase(
            line="a\\/",
            expect=("a\\", False, True, False),
            tree=["a/f", "b"],
            listed=["a/f", "b", "ignore"],
        ),
        id="escaped-trailing-slash",
    ),
    # The negation only re-includes directories, so the file "a" stays ignored.
    param(
        PatternCase(
            line="!a/",
            expect=("a", True, True, False),
            tree=["a", "sub/a/f"],
            listed=["ignore", "sub/a/f"],
            before="a",
        ),
        id="negated-directory-only",
    ),
    param(
        PatternCase(
            line="/a/",
            expect=("a", False, True, True),
            tree=["a/f", "sub/a/f", "x/a"],
            listed=["ignore", "sub/a/f", "x/a"],
        ),
        id="anchored-directory-only",
    ),
]


@mark.parametrize("case", DIRECTORY_ONLY)
def test_parse_pattern__directory_only(case: PatternCase) -> None:
    """A "/" at the very end means the pattern only matches directories."""
    assert parse_pattern(case.line) == case.expect


ANCHORING = [
    param(
        PatternCase(
            line="/a",
            expect=("a", False, False, True),
            tree=["a", "sub/a"],
            listed=["ignore", "sub/a"],
        ),
        id="leading-slash",
    ),
    param(
        PatternCase(
            line="a",
            expect=("a", False, False, False),
            tree=["a", "sub/a"],
            listed=["ignore"],
        ),
        id="no-slash",
    ),
    param(
        PatternCase(
            line="a/b",
            expect=("a/b", False, False, True),
            tree=["a/b", "sub/a/b"],
            listed=["ignore", "sub/a/b"],
        ),
        id="middle-slash",
    ),
    param(
        PatternCase(
            line="//a",
            expect=("/a", False, False, True),
            tree=["a", "sub/a"],
            listed=["a", "ignore", "sub/a"],
        ),
        id="two-leading-slashes",
    ),
    param(
        PatternCase(
            line="a\\/b",
            expect=("a\\/b", False, False, True),
            tree=["a/b", "sub/a/b"],
            listed=["ignore", "sub/a/b"],
        ),
        id="escaped-slash",
    ),
    # The line doesn't start with a "/", so there's none to remove, and the glob can
    # never match.
    param(
        PatternCase(
            line="\\/a",
            expect=("\\/a", False, False, True),
            tree=["a", "sub/a"],
            listed=["a", "ignore", "sub/a"],
        ),
        id="escaped-leading-slash",
    ),
    param(
        PatternCase(
            line="[/a]b",
            expect=("[/a]b", False, False, True),
            tree=["ab", "sub/ab"],
            listed=["ignore", "sub/ab"],
        ),
        id="slash-in-brackets",
    ),
    param(
        PatternCase(
            line="!/a",
            expect=("a", True, False, True),
            tree=["a", "sub/a"],
            listed=["a", "ignore"],
            before="a",
        ),
        id="negated-leading-slash",
    ),
    param(
        PatternCase(
            line="/!a",
            expect=("!a", False, False, True),
            tree=["!a", "sub/!a"],
            listed=["ignore", "sub/!a"],
        ),
        id="exclamation-mark-after-slash",
    ),
    # The "/" anchors this pattern too. Its leading "**/" is what matches any depth.
    param(
        PatternCase(
            line="**/a",
            expect=("**/a", False, False, True),
            tree=["a", "sub/a"],
            listed=["ignore"],
        ),
        id="leading-double-asterisk",
    ),
]


@mark.parametrize("case", ANCHORING)
def test_parse_pattern__anchoring(case: PatternCase) -> None:
    """Any other "/" anchors the pattern, and one at the very start is removed."""
    assert parse_pattern(case.line) == case.expect


NOTHING_LEFT = [
    param(
        PatternCase(
            line=" ",
            expect=None,
            tree=[" ", "a"],
            listed=[" ", "a", "ignore"],
        ),
        id="only-a-space",
    ),
    param(
        PatternCase(
            line="   ",
            expect=None,
            tree=["   ", "a"],
            listed=["   ", "a", "ignore"],
        ),
        id="only-spaces",
    ),
    param(
        PatternCase(
            line="!",
            expect=None,
            tree=["!", "a", "b"],
            listed=["!", "b", "ignore"],
            before="a",
        ),
        id="only-an-exclamation-mark",
    ),
    param(
        PatternCase(
            line="/",
            expect=None,
            tree=["a/f", "b"],
            listed=["a/f", "b", "ignore"],
        ),
        id="only-a-slash",
    ),
    param(
        PatternCase(
            line="!/",
            expect=None,
            tree=["!/f", "a/f", "b"],
            listed=["!/f", "b", "ignore"],
            before="a",
        ),
        id="exclamation-mark-and-slash",
    ),
    param(
        PatternCase(
            line="//",
            expect=None,
            tree=["a/f", "b"],
            listed=["a/f", "b", "ignore"],
        ),
        id="only-slashes",
    ),
]


@mark.parametrize("case", NOTHING_LEFT)
def test_parse_pattern__nothing_left(case: PatternCase) -> None:
    """`None` is returned when nothing is left of the line to match."""
    assert parse_pattern(case.line) == case.expect


NEVER_MATCHES = [
    param(
        PatternCase(
            line="./a",
            expect=("./a", False, False, True),
            tree=["a", "sub/a"],
            listed=["a", "ignore", "sub/a"],
        ),
        id="dot",
    ),
    param(
        PatternCase(
            line="../a",
            expect=("../a", False, False, True),
            tree=["a", "sub/a"],
            listed=["a", "ignore", "sub/a"],
        ),
        id="dot-dot",
    ),
    param(
        PatternCase(
            line="a//b",
            expect=("a//b", False, False, True),
            tree=["a/b"],
            listed=["a/b", "ignore"],
        ),
        id="double-slash",
    ),
    # The last backslash escapes nothing, so the glob never matches.
    param(
        PatternCase(
            line="a \\",
            expect=("a \\", False, False, False),
            tree=["a", "a ", "a \\"],
            listed=["a", "a ", "a \\", "ignore"],
        ),
        id="lone-backslash",
    ),
]


@mark.parametrize("case", NEVER_MATCHES)
def test_parse_pattern__never_matches(case: PatternCase) -> None:
    """Nothing is tidied up, even when that means the pattern can never match."""
    assert parse_pattern(case.line) == case.expect


@needs_git
@mark.parametrize(
    "case",
    [
        *TRAILING_SPACES,
        *NEGATION,
        *ESCAPES,
        *DIRECTORY_ONLY,
        *ANCHORING,
        *NOTHING_LEFT,
        *NEVER_MATCHES,
    ],
)
def test_parse_pattern__git(tmp_path: Path, case: PatternCase) -> None:
    """Git lists the expected files, for the line and for its expected pattern."""
    # Windows refuses some names, and quietly changes others ("a " becomes "a"), so a
    # row that needs one is only checked on Linux and macOS.
    if sys.platform == "win32":
        for path in case.tree:
            if not windows_can_create(path):
                skip(f"Windows can't create {path!r}")

    before = [] if case.before is None else [case.before]
    lines = [*before, case.line]
    assert list_files(tmp_path / "line", case.tree, lines) == case.listed

    # Git can't check a pattern directly, so we also write the expected pattern back as
    # a line, and check that Git lists the same files for it. This way, Git checks the
    # patterns in these tables and not only their listings.
    lines = before if case.expect is None else [*before, format_pattern(case.expect)]
    assert list_files(tmp_path / "pattern", case.tree, lines) == case.listed
