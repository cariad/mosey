"""Unit tests for the `rules` module."""

from pathlib import Path
from typing import NamedTuple

from pytest import mark, param

from mosey.rules import Layer, Layers, compile_rules, is_ignored
from tests.file_system_helpers import (
    make_tree,
    skip_if_windows_cannot_create,
    write_ignore_files,
)
from tests.git_oracle import git_list_files
from tests.markers import needs_git


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
        id="wildcard-then-re-include",
    ),
    param(
        RuleCase(files={"": ["a", "!a", "a"]}, entry="a", ignored=True),
        id="repeated-line",
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
    param(
        RuleCase(files={"": ["build/"]}, entry="sub/build/", ignored=True),
        id="directory-only-at-depth",
    ),
    param(
        RuleCase(files={"": ["a"]}, entry="ab", ignored=False),
        id="whole-name",
    ),
    param(
        RuleCase(files={"": ["A"]}, entry="a", ignored=False),
        id="case",
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


NOTHING_LEFT = [
    param([], id="no-lines"),
    param(["!", "/", "!/", "//"], id="lines-with-nothing-left"),
    param(["[a", "[[:foo:]]", "a\\"], id="malformed-lines"),
]


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
