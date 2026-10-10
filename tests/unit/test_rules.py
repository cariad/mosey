"""Unit tests for the `rules` module."""

from pathlib import Path
from typing import NamedTuple

from pytest import mark, param

from mosey.rules import (
    MAX_CHECKED_ENDINGS,
    Layer,
    Layers,
    Matcher,
    compile_ignore_filename_layers,
    compile_root_layers,
    compile_rules,
    is_ignored,
)
from tests.file_system_helpers import (
    make_tree,
    skip_if_windows_cannot_create,
    write_ignore_files,
)
from tests.git_oracle import git_list_files
from tests.markers import needs_git

# One more ending than a name is checked against before it's looked up.
MANY_ENDINGS = [f"*.{index}" for index in range(MAX_CHECKED_ENDINGS + 1)]


class RuleCase(NamedTuple):
    """Ignore-files, one entry beneath them, and whether the entry is ignored."""

    files: dict[str, list[str]]
    """Each ignore-file's lines, by directory: "" for the root, or a "/"-separated path.

    Only the root and the directories above the entry can have one.
    """

    entry: str
    """The entry's "/"-separated path from the root, ending with "/" for a directory."""

    ignored: bool
    """Whether the entry is ignored."""


def layers(case: RuleCase) -> Layers:
    """Return the layers that apply to a case's entry, deepest first.

    Args:
        case: The case to build the layers for.

    Returns:
        The layers from the ignore-files in the directory that holds the entry and every
        directory above it.
    """
    names = case.entry.removesuffix("/").split("/")
    found: list[Layer] = []

    for depth in reversed(range(len(names))):
        rules = compile_rules(case.files.get("/".join(names[:depth]), []))

        if rules is not None:
            found.append(("".join(f"{name}/" for name in names[:depth]), *rules))

    return tuple(found)


def judge(case: RuleCase) -> bool:
    """Return whether `is_ignored` ignores a case's entry.

    Args:
        case: The case to judge.

    Returns:
        `True` if the entry is ignored, otherwise `False`.
    """
    relative = case.entry.removesuffix("/")
    name = relative.rpartition("/")[2]
    return is_ignored(layers(case), name, relative, case.entry.endswith("/"))


@mark.parametrize(
    ("name", "other"),
    [
        param("ignore", "Ignore", id="plain"),
        # Each of these names would match the other one, or not match itself, if it
        # were read as a line of an ignore-file.
        param("a*b", "axb", id="star"),
        param("a?b", "axb", id="question-mark"),
        param("[a]", "a", id="brackets"),
        param("**", "a", id="double-star"),
        param("!a", "a", id="exclamation-mark"),
        param("#a", "a", id="hash"),
        param("a ", "a", id="trailing-space"),
    ],
)
def test_compile_ignore_filename_layers(name: str, other: str) -> None:
    """The layers ignore every file with exactly the name, and nothing else."""
    layers = compile_ignore_filename_layers(name)

    assert is_ignored(layers, name, name, False)
    assert is_ignored(layers, name, f"a/b/{name}", False)
    assert not is_ignored(layers, other, other, False)

    # A directory named like the ignore-file is walked like any other.
    assert not is_ignored(layers, name, name, True)


PRECEDENCE = [
    param(
        RuleCase(files={"": ["a", "!a"]}, entry="a", ignored=False),
        id="last-line-wins",
    ),
    param(
        RuleCase(files={"": ["!a", "a"]}, entry="a", ignored=True),
        id="last-line-wins-ignoring",
    ),
    param(
        RuleCase(files={"": ["*.log", "!keep.log"]}, entry="keep.log", ignored=False),
        id="ending-then-re-include",
    ),
    param(
        RuleCase(files={"": ["a", "!a", "a"]}, entry="a", ignored=True),
        id="repeated-line",
    ),
    param(
        RuleCase(files={"": ["*.log", "!*.log"]}, entry="a.log", ignored=False),
        id="last-ending-wins",
    ),
    # A plain name and a wildcard both match, and the later line decides, whichever
    # kind it is and whichever is negated.
    param(
        RuleCase(files={"": ["a", "!a*"]}, entry="a", ignored=False),
        id="plain-name-then-negated-wildcard",
    ),
    param(
        RuleCase(files={"": ["!a", "a*"]}, entry="a", ignored=True),
        id="negated-plain-name-then-wildcard",
    ),
    param(
        RuleCase(files={"": ["a*", "!a"]}, entry="a", ignored=False),
        id="wildcard-then-negated-plain-name",
    ),
    param(
        RuleCase(files={"": ["!a*", "a"]}, entry="a", ignored=True),
        id="negated-wildcard-then-plain-name",
    ),
    # The same for a plain path. In the first, the wildcard matches the name rather
    # than the path.
    param(
        RuleCase(files={"": ["/a", "!a*"]}, entry="a", ignored=False),
        id="plain-path-then-negated-wildcard",
    ),
    param(
        RuleCase(files={"": ["!/a", "/a*"]}, entry="a", ignored=True),
        id="negated-plain-path-then-wildcard",
    ),
    param(
        RuleCase(files={"": ["/a*", "!/a"]}, entry="a", ignored=False),
        id="wildcard-then-negated-plain-path",
    ),
    param(
        RuleCase(files={"": ["!/a*", "/a"]}, entry="a", ignored=True),
        id="negated-wildcard-then-plain-path",
    ),
    # A plain name and a plain path both match, and the later line decides.
    param(
        RuleCase(files={"": ["a", "!/a"]}, entry="a", ignored=False),
        id="plain-name-then-negated-plain-path",
    ),
    param(
        RuleCase(files={"": ["/a", "!a"]}, entry="a", ignored=False),
        id="plain-path-then-negated-plain-name",
    ),
    # An ending and a wildcard match, and the later one decides. The last line, another
    # ending, doesn't match, and changes nothing.
    param(
        RuleCase(
            files={"": ["*.log", "!keep*", "*.tmp"]},
            entry="keep.log",
            ignored=False,
        ),
        id="ending-then-negated-wildcard",
    ),
    # The same, but a "?" keeps "*.lo?" and "*.tm?" from being endings, so all three
    # lines are in one regular expression.
    param(
        RuleCase(
            files={"": ["*.lo?", "!keep*", "*.tm?"]},
            entry="keep.log",
            ignored=False,
        ),
        id="wildcard-then-negated-wildcard-no-endings",
    ),
    # A plain name and an ending both match, and the later line decides, whichever is
    # negated. (`ending-then-re-include` is the fourth way round.)
    param(
        RuleCase(files={"": ["a.log", "!*.log"]}, entry="a.log", ignored=False),
        id="plain-name-then-negated-ending",
    ),
    param(
        RuleCase(files={"": ["!a.log", "*.log"]}, entry="a.log", ignored=True),
        id="negated-plain-name-then-ending",
    ),
    param(
        RuleCase(files={"": ["!*.log", "a.log"]}, entry="a.log", ignored=True),
        id="negated-ending-then-plain-name",
    ),
    # An ending and a wildcard both match, and the later line decides, whichever is
    # negated. (`ending-then-negated-wildcard` is the fourth way round.)
    param(
        RuleCase(files={"": ["a*", "!*.log"]}, entry="a.log", ignored=False),
        id="wildcard-then-negated-ending",
    ),
    param(
        RuleCase(files={"": ["!a*", "*.log"]}, entry="a.log", ignored=True),
        id="negated-wildcard-then-ending",
    ),
    param(
        RuleCase(files={"": ["!*.log", "a*"]}, entry="a.log", ignored=True),
        id="negated-ending-then-wildcard",
    ),
    # Two endings match, and the later one decides, whichever is longer.
    param(
        RuleCase(files={"": ["*.gz", "!*.tar.gz"]}, entry="a.tar.gz", ignored=False),
        id="ending-then-negated-longer-ending",
    ),
    param(
        RuleCase(files={"": ["!*.tar.gz", "*.gz"]}, entry="a.tar.gz", ignored=True),
        id="negated-longer-ending-then-ending",
    ),
]


@mark.parametrize("case", PRECEDENCE)
def test_is_ignored__precedence(case: RuleCase) -> None:
    """Within one ignore-file, the last line that matches decides."""
    assert judge(case) == case.ignored


NESTED = [
    param(
        RuleCase(
            files={"": ["*.log"], "sub": ["!x.log"]},
            entry="sub/x.log",
            ignored=False,
        ),
        id="deeper-file-re-includes",
    ),
    param(
        RuleCase(
            files={"": ["*.log", "!x.log"], "sub": ["x.log"]},
            entry="sub/x.log",
            ignored=True,
        ),
        id="deeper-file-ignores",
    ),
    # The deeper file has no line that matches, so the root's decides.
    param(
        RuleCase(
            files={"": ["*.log"], "sub": ["*.txt"]},
            entry="sub/x.log",
            ignored=True,
        ),
        id="falls-through-to-root",
    ),
    param(
        RuleCase(
            files={"": ["!x"], "a": ["x"], "a/b": ["y"]},
            entry="a/b/x",
            ignored=True,
        ),
        id="falls-through-to-middle",
    ),
    # Each file's anchored lines match the path from that file's own directory.
    param(
        RuleCase(
            files={"": ["/sub/x"], "sub": ["/y"]},
            entry="sub/x",
            ignored=True,
        ),
        id="falls-through-anchored",
    ),
    # A line ending with "/" never matches a file, even to re-include it.
    param(
        RuleCase(files={"": ["x"], "sub": ["!x/"]}, entry="sub/x", ignored=True),
        id="falls-through-past-directory-only",
    ),
    param(
        RuleCase(
            files={"": ["build/"], "sub": ["!build/"]},
            entry="sub/build/",
            ignored=False,
        ),
        id="deeper-file-re-includes-directory",
    ),
]


@mark.parametrize("case", NESTED)
def test_is_ignored__nested(case: RuleCase) -> None:
    """The deepest ignore-file with a line that matches decides."""
    assert judge(case) == case.ignored


NEGATION = [
    param(
        RuleCase(files={"": ["!a"]}, entry="a", ignored=False),
        id="negation-alone",
    ),
    param(
        RuleCase(files={"": ["*", "!d/"]}, entry="d/", ignored=False),
        id="negated-directory-after-star",
    ),
]


@mark.parametrize("case", NEGATION)
def test_is_ignored__negation(case: RuleCase) -> None:
    """A line starting with "!" keeps what it matches."""
    assert judge(case) == case.ignored


DIRECTORY_ONLY = [
    param(
        RuleCase(files={"": ["a/"]}, entry="a/", ignored=True),
        id="directory-only-directory",
    ),
    param(
        RuleCase(files={"": ["a/"]}, entry="a", ignored=False),
        id="directory-only-file",
    ),
    param(
        RuleCase(files={"": ["*.log/"]}, entry="a.log/", ignored=True),
        id="directory-only-ending-directory",
    ),
    param(
        RuleCase(files={"": ["*.log/"]}, entry="a.log", ignored=False),
        id="directory-only-ending-file",
    ),
    # A line without a "/" at the end matches directories too.
    param(
        RuleCase(files={"": ["a"]}, entry="a/", ignored=True),
        id="name-directory",
    ),
    param(
        RuleCase(files={"": ["a", "!a/"]}, entry="a", ignored=True),
        id="negated-directory-only-file",
    ),
    param(
        RuleCase(files={"": ["a", "!a/"]}, entry="a/", ignored=False),
        id="negated-directory-only-directory",
    ),
    param(
        RuleCase(files={"": ["a/", "!a"]}, entry="a/", ignored=False),
        id="plain-line-after-directory-only",
    ),
    param(
        RuleCase(files={"": ["*/", "!a"]}, entry="a/", ignored=False),
        id="plain-line-after-directory-only-wildcard",
    ),
]


@mark.parametrize("case", DIRECTORY_ONLY)
def test_is_ignored__directory_only(case: RuleCase) -> None:
    """A line ending with "/" only matches directories."""
    assert judge(case) == case.ignored


ANCHORING = [
    param(
        RuleCase(files={"": ["/top"]}, entry="top", ignored=True),
        id="anchored",
    ),
    param(
        RuleCase(files={"": ["/top"]}, entry="sub/top", ignored=False),
        id="anchored-not-deeper",
    ),
    param(
        RuleCase(files={"sub": ["/top"]}, entry="sub/top", ignored=True),
        id="nested-anchored",
    ),
    param(
        RuleCase(files={"sub": ["/top"]}, entry="sub/x/top", ignored=False),
        id="nested-anchored-not-deeper",
    ),
    # The path is matched from the ignore-file's directory, not from the root.
    param(
        RuleCase(files={"sub": ["/sub/top"]}, entry="sub/top", ignored=False),
        id="nested-anchored-from-its-directory",
    ),
    # Only the directory's own "a/" is cut from the front of the path, leaving "a/a",
    # rather than every "a/" in the path, or every "a" and "/" at its front.
    param(
        RuleCase(files={"a": ["/a/a"]}, entry="a/a/a", ignored=True),
        id="nested-anchored-same-name",
    ),
    param(
        RuleCase(files={"a": ["/a/*"]}, entry="a/a/a", ignored=True),
        id="nested-anchored-wildcard-same-name",
    ),
    param(
        RuleCase(files={"": ["a/b"]}, entry="a/b", ignored=True),
        id="middle-slash",
    ),
    param(
        RuleCase(files={"": ["a/b"]}, entry="x/a/b", ignored=False),
        id="middle-slash-not-deeper",
    ),
    param(
        RuleCase(files={"sub": ["a/b"]}, entry="sub/a/b", ignored=True),
        id="nested-middle-slash",
    ),
    # A "/" anchors a line that starts with "*.", so it matches the path from the
    # ignore-file's directory, not any name with the same ending.
    param(
        RuleCase(files={"": ["/*.log"]}, entry="a.log", ignored=True),
        id="anchored-ending",
    ),
    param(
        RuleCase(files={"": ["/*.log"]}, entry="x/a.log", ignored=False),
        id="anchored-ending-not-deeper",
    ),
    param(
        RuleCase(files={"": ["*.d/x"]}, entry="a.d/x", ignored=True),
        id="middle-slash-wildcard",
    ),
    param(
        RuleCase(files={"": ["a", "!/a"]}, entry="x/a", ignored=True),
        id="negated-anchored-not-deeper",
    ),
    param(
        RuleCase(files={"": ["/a/"]}, entry="a/", ignored=True),
        id="anchored-directory-only",
    ),
    param(
        RuleCase(files={"": ["/a/"]}, entry="x/a/", ignored=False),
        id="anchored-directory-only-not-deeper",
    ),
    param(
        RuleCase(files={"": ["**/a"]}, entry="x/y/a", ignored=True),
        id="leading-double-star",
    ),
    param(
        RuleCase(files={"": ["**/a"]}, entry="a", ignored=True),
        id="leading-double-star-no-directory",
    ),
    param(
        RuleCase(files={"": ["*", "!**/keep"]}, entry="keep", ignored=False),
        id="negated-leading-double-star-no-directory",
    ),
    param(
        RuleCase(files={"sub": ["**/a"]}, entry="sub/a", ignored=True),
        id="nested-leading-double-star-no-directory",
    ),
    # A "**/" before a glob with no other "/" matches the same as the glob alone.
    param(
        RuleCase(files={"": ["**/*.log"]}, entry="x/y/a.log", ignored=True),
        id="leading-double-star-ending",
    ),
    param(
        RuleCase(files={"": ["**/x/a"]}, entry="y/x/a", ignored=True),
        id="leading-double-star-path",
    ),
    param(
        RuleCase(files={"sub": ["x/**/a"]}, entry="sub/x/y/a", ignored=True),
        id="nested-middle-double-star",
    ),
]


@mark.parametrize("case", ANCHORING)
def test_is_ignored__anchoring(case: RuleCase) -> None:
    """A line with any other "/" matches the path from its ignore-file's directory."""
    assert judge(case) == case.ignored


UNANCHORED = [
    param(
        RuleCase(files={"": ["a"]}, entry="x/y/a", ignored=True),
        id="name-at-depth",
    ),
    param(
        RuleCase(files={"sub": ["a"]}, entry="sub/x/a", ignored=True),
        id="nested-name-at-depth",
    ),
    param(
        RuleCase(files={"": ["*.log"]}, entry="x/y.log", ignored=True),
        id="wildcard-at-depth",
    ),
    # A line like "*.log" matches every name that ends with what follows its "*".
    param(
        RuleCase(files={"": ["*.gz"]}, entry="a.tar.gz", ignored=True),
        id="ending-last-dot",
    ),
    param(
        RuleCase(files={"": ["*.tar.gz"]}, entry="a.tar.gz", ignored=True),
        id="ending-two-dots",
    ),
    param(
        RuleCase(files={"": ["*.tar.gz"]}, entry="a.gz", ignored=False),
        id="ending-two-dots-not-one",
    ),
    param(
        RuleCase(files={"": ["*.c.d"]}, entry="a.b.c.d", ignored=True),
        id="ending-several-dots",
    ),
    param(
        RuleCase(files={"": ["*.b.c"]}, entry="a.b.c.d", ignored=False),
        id="ending-several-dots-not-middle",
    ),
    param(
        RuleCase(files={"": ["*.log"]}, entry="a.log.txt", ignored=False),
        id="ending-not-in-middle",
    ),
    param(
        RuleCase(files={"": ["*."]}, entry="a.", ignored=True),
        id="ending-only-dot",
    ),
    param(
        RuleCase(files={"": ["*.log"]}, entry="log", ignored=False),
        id="ending-without-dot",
    ),
    # The "*" can match nothing.
    param(
        RuleCase(files={"": ["*.log"]}, entry=".log", ignored=True),
        id="ending-whole-name",
    ),
    # A "?" after the "*." means the line isn't an ending.
    param(
        RuleCase(files={"": ["*.lo?"]}, entry="a.log", ignored=True),
        id="ending-with-question-mark",
    ),
    # With more endings than a name is checked against first, it's only looked up.
    param(
        RuleCase(
            files={"": MANY_ENDINGS},
            entry=f"a.{MAX_CHECKED_ENDINGS}",
            ignored=True,
        ),
        id="many-endings",
    ),
    param(
        RuleCase(files={"": MANY_ENDINGS}, entry="a.log", ignored=False),
        id="many-endings-not",
    ),
    # A "?", a bracket or a backslash means the line isn't a plain name.
    param(
        RuleCase(files={"": ["a?"]}, entry="ab", ignored=True),
        id="question-mark",
    ),
    param(
        RuleCase(files={"": ["[ab]"]}, entry="a", ignored=True),
        id="brackets",
    ),
    param(
        RuleCase(files={"": ["\\#a"]}, entry="#a", ignored=True),
        id="escaped-hash",
    ),
    param(
        RuleCase(files={"": ["build/"]}, entry="sub/build/", ignored=True),
        id="directory-only-at-depth",
    ),
    param(
        RuleCase(files={"": ["a"]}, entry="ab", ignored=False),
        id="whole-name",
    ),
    param(
        RuleCase(files={"": ["*.log"]}, entry="x.logs", ignored=False),
        id="whole-name-wildcard",
    ),
    param(
        RuleCase(files={"": ["a?"]}, entry="abc", ignored=False),
        id="whole-name-question-mark",
    ),
    param(
        RuleCase(files={"": ["A"]}, entry="a", ignored=False),
        id="case",
    ),
    param(
        RuleCase(files={"": ["A*"]}, entry="a", ignored=False),
        id="case-wildcard",
    ),
    param(
        RuleCase(files={"": ["*.LOG"]}, entry="a.log", ignored=False),
        id="case-ending",
    ),
    # Only spaces are trimmed from the end of a line, so the tab is part of the name.
    param(
        RuleCase(files={"": ["a\t"]}, entry="a", ignored=False),
        id="trailing-tab",
    ),
    # The line matches the entry's own name, not a directory's name above it.
    param(
        RuleCase(files={"": ["x", "!x/"]}, entry="x/a", ignored=False),
        id="name-of-directory-above",
    ),
    param(
        RuleCase(files={"": ["x*", "!x*/"]}, entry="x/a", ignored=False),
        id="wildcard-name-of-directory-above",
    ),
]


@mark.parametrize("case", UNANCHORED)
def test_is_ignored__unanchored(case: RuleCase) -> None:
    """A line with no "/" before its end matches the whole name, at any depth."""
    assert judge(case) == case.ignored


DOUBLE_ASTERISKS = [
    param(
        RuleCase(files={"": ["a/**/"]}, entry="a/x/", ignored=True),
        id="directories-inside",
    ),
    param(
        RuleCase(files={"": ["a/**/"]}, entry="a/x", ignored=False),
        id="directories-inside-not-files",
    ),
    param(
        RuleCase(files={"": ["a/**/"]}, entry="a/", ignored=False),
        id="directories-inside-not-itself",
    ),
    # The second line keeps "a/x", so that Git looks inside it.
    param(
        RuleCase(files={"": ["a/**/", "!/a/x/"]}, entry="a/x/y/", ignored=True),
        id="directories-inside-deeper",
    ),
    param(
        RuleCase(files={"": ["**/a/"]}, entry="x/y/a/", ignored=True),
        id="directory-at-any-depth",
    ),
    param(
        RuleCase(files={"": ["**/a/"]}, entry="x/y/a", ignored=False),
        id="directory-at-any-depth-not-files",
    ),
    param(
        RuleCase(files={"": ["**/a/"]}, entry="a/", ignored=True),
        id="directory-at-any-depth-no-directory",
    ),
    param(
        RuleCase(files={"sub": ["**/a/"]}, entry="sub/a/", ignored=True),
        id="nested-directory-at-any-depth",
    ),
    param(
        RuleCase(files={"": ["/a/**", "!/a/**/"]}, entry="a/x/", ignored=False),
        id="re-include-directories-inside",
    ),
    param(
        RuleCase(files={"": ["/a/**", "!/a/**/"]}, entry="a/f", ignored=True),
        id="re-include-directories-inside-not-files",
    ),
]


@mark.parametrize("case", DOUBLE_ASTERISKS)
def test_is_ignored__double_asterisks(case: RuleCase) -> None:
    """A line with a "**" and a "/" at the end only matches directories."""
    assert judge(case) == case.ignored


# A walk's relative paths never start or end with "/", or hold an empty, "." or ".."
# name, so lines that need one never match.
NEVER_MATCHES = [
    param(
        RuleCase(files={"": ["//a"]}, entry="a", ignored=False),
        id="two-leading-slashes",
    ),
    param(
        RuleCase(files={"sub": ["//a"]}, entry="sub/a", ignored=False),
        id="nested-two-leading-slashes",
    ),
    param(
        RuleCase(files={"": ["a//"]}, entry="a/", ignored=False),
        id="two-trailing-slashes",
    ),
    param(
        RuleCase(files={"": ["./a"]}, entry="a", ignored=False),
        id="dot",
    ),
    param(
        RuleCase(files={"sub": ["../a"]}, entry="sub/a", ignored=False),
        id="dot-dot",
    ),
    param(
        RuleCase(files={"": ["a//b"]}, entry="a/b", ignored=False),
        id="double-slash",
    ),
]


@mark.parametrize("case", NEVER_MATCHES)
def test_is_ignored__never_matches(case: RuleCase) -> None:
    """Lines that only match paths a walk never makes never match."""
    assert judge(case) == case.ignored


MALFORMED = [
    param(
        RuleCase(files={"": ["[a"]}, entry="[a", ignored=False),
        id="malformed",
    ),
    param(
        RuleCase(files={"": ["a", "![a"]}, entry="a", ignored=True),
        id="malformed-negation",
    ),
    param(
        RuleCase(files={"": ["[a", "b"]}, entry="b", ignored=True),
        id="malformed-beside-another-line",
    ),
    param(
        RuleCase(files={"": ["!", "b"]}, entry="b", ignored=True),
        id="nothing-left-beside-another-line",
    ),
    param(
        RuleCase(files={"": ["a", "!"]}, entry="a", ignored=True),
        id="nothing-left",
    ),
    # The deeper file has no line left to match, so the root's decides.
    param(
        RuleCase(files={"": ["x"], "sub": ["![x", "!"]}, entry="sub/x", ignored=True),
        id="only-malformed-lines",
    ),
]


@mark.parametrize("case", MALFORMED)
def test_is_ignored__malformed(case: RuleCase) -> None:
    """A malformed line matches nothing, and leaves the other lines working."""
    assert judge(case) == case.ignored


# Every case whose only ignore-file is in the root, so its lines could be patterns given
# in code instead.
IN_ROOT = [
    case
    for case in [
        *PRECEDENCE,
        *NEGATION,
        *DIRECTORY_ONLY,
        *ANCHORING,
        *UNANCHORED,
        *DOUBLE_ASTERISKS,
        *NEVER_MATCHES,
        *MALFORMED,
    ]
    if isinstance(case.values[0], RuleCase) and set(case.values[0].files) == {""}
]


@mark.parametrize("case", IN_ROOT)
def test_compile_root_layers(case: RuleCase) -> None:
    """Patterns judge an entry exactly as the same lines in the root's ignore-file."""
    found = compile_root_layers(case.files[""])

    # One layer, tied to the root, unless no line is left to match.
    assert [prefix for prefix, _, _ in found] == [
        prefix for prefix, _, _ in layers(case)
    ]

    relative = case.entry.removesuffix("/")
    name = relative.rpartition("/")[2]
    assert is_ignored(found, name, relative, case.entry.endswith("/")) == case.ignored


NOTHING_LEFT = [
    param([], id="no-lines"),
    param(["!", "/", "!/", "//"], id="lines-with-nothing-left"),
    param(["[a", "[[:foo:]]", "a\\"], id="malformed-lines"),
]


@mark.parametrize("lines", NOTHING_LEFT)
def test_compile_root_layers__nothing_left(lines: list[str]) -> None:
    """No layers are returned when no line is left to match."""
    assert compile_root_layers(lines) == ()


def test_compile_rules__ending() -> None:
    """A line like "*.log" is looked up by its ending, not by a regular expression."""
    matcher: Matcher = ({}, {".log": 3}, (".log",), None, (), {}, None, ())
    assert compile_rules(["*.log"]) == (matcher, matcher)


def test_compile_rules__leading_double_star() -> None:
    """A "**/" before a glob with no other "/" compiles as the glob alone."""
    assert compile_rules(["**/a", "**/*.log"]) == compile_rules(["a", "*.log"])


@mark.parametrize(
    ("count", "checked"),
    [
        param(MAX_CHECKED_ENDINGS, True, id="checked"),
        param(MAX_CHECKED_ENDINGS + 1, False, id="too-many-to-check"),
    ],
)
def test_compile_rules__many_endings(count: int, checked: bool) -> None:
    """A name is checked against the endings first only when there are few."""
    endings = [f".{index}" for index in range(count)]
    rules = compile_rules([f"*{ending}" for ending in endings])
    assert rules is not None

    for matcher in rules:
        assert list(matcher[1]) == endings
        assert matcher[2] == (tuple(endings) if checked else None)


@mark.parametrize("lines", NOTHING_LEFT)
def test_compile_rules__nothing_left(lines: list[str]) -> None:
    """`None` is returned when no line is left to match."""
    assert compile_rules(lines) is None


@needs_git
@mark.parametrize(
    "case",
    [
        *PRECEDENCE,
        *NESTED,
        *NEGATION,
        *DIRECTORY_ONLY,
        *ANCHORING,
        *UNANCHORED,
        *DOUBLE_ASTERISKS,
        *NEVER_MATCHES,
        *MALFORMED,
    ],
)
def test_is_ignored__git(tmp_path: Path, case: RuleCase) -> None:
    """Git lists the entry exactly when it isn't ignored."""
    relative = case.entry.removesuffix("/")
    names = relative.split("/")
    is_dir = case.entry.endswith("/")

    # Every directory below gets an ignore-file named "ignore". On macOS and Windows, an
    # entry or directory named "Ignore" would be that same file.
    assert all(name.lower() != "ignore" for name in names)

    skip_if_windows_cannot_create([case.entry])

    # The root and every directory above the entry.
    directories = ["/".join(names[:depth]) for depth in range(len(names))]
    assert set(case.files) <= set(directories)

    if is_dir:
        directories.append(relative)

    # Git only shows a directory through a file inside it. So each of these directories
    # gets an ignore-file whose last line keeps it. That line only matches the name
    # "ignore", which the entry and the directories above it don't have, so it changes
    # nothing else.
    files = {
        directory: [*case.files.get(directory, []), "!ignore"]
        for directory in directories
    }

    root = tmp_path / "tree"
    write_ignore_files(root, files)
    make_tree(root, case.entry)
    listed = git_list_files(root, "ignore")

    # Git leaves out everything inside an ignored directory. So if Git leaves out the
    # parent's ignore-file, a directory above the entry is ignored, and the entry's own
    # answer can't be seen.
    parent = "".join(f"{name}/" for name in names[:-1])
    assert f"{parent}ignore" in listed

    shown = f"{relative}/ignore" if is_dir else relative
    assert (shown not in listed) == case.ignored
