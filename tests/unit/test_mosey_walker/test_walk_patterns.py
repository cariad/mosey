"""Unit tests for the `MoseyWalker.walk` function with patterns given in code."""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from pytest import mark, param, skip

from tests.file_system_helpers import (
    build_walker,
    make_broken_symlink,
    make_tree,
    make_tree_with_ignore_files,
    relative_paths,
)
from tests.git_oracle import KEPT_SPACES, git_list_files
from tests.markers import needs_git, needs_symlinks


class PatternCase(NamedTuple):
    """Ignore-files, the rest of a tree, patterns, and the files a walk of it yields."""

    ignore_files: dict[str, list[str] | bytes]
    """Each ignore-file's lines or exact bytes, by directory.

    Each directory is "" for the root, or a "/"-separated path. Every ignore-file is
    named "ignore". Lines are written as UTF-8, each followed by a newline.
    """

    tree: list[str]
    """The rest of the tree, as `make_tree` takes it."""

    patterns: list[tuple[str, int]]
    """Each pattern and its weight, in the order they're added."""

    listed: list[str]
    """The "/"-separated paths of the files the walk yields, in walk order."""

    name: str | None = "ignore"
    """The ignore-file name that the walk and Git are given, or `None` to read none."""

    ignore_ignore_files: bool = True
    """Whether the walk and Git leave out the ignore-files."""

    divergence: str | None = None
    """Why Git lists differently, if it does."""


WEIGHTS = [
    # Every ignore-file overrules a pattern weighing 0, so the root's "!a.log" and
    # "sub"'s "!b.log" both re-include what it ignores. The root's line reaches "sub"
    # too.
    param(
        PatternCase(
            ignore_files={"": ["!a.log"], "sub": ["!b.log"]},
            tree=["a.log", "b.log", "c.log", "sub/a.log", "sub/b.log", "sub/c.log"],
            patterns=[("*.log", 0)],
            listed=["a.log", "sub/a.log", "sub/b.log"],
        ),
        id="light-loses-to-ignore-files",
    ),
    param(
        PatternCase(
            ignore_files={"": ["!a.log"], "sub": ["!b.log"]},
            tree=[
                "a.log",
                "b.log",
                "c.log",
                "readme",
                "sub/a.log",
                "sub/b.log",
                "sub/c.log",
            ],
            patterns=[("*.log", 1)],
            listed=["readme"],
        ),
        id="heavy-beats-ignore-files",
    ),
    # A pattern weighing -1 ranks below one weighing 0, whichever was added first.
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", 0), ("!keep.log", -1)],
            listed=["readme"],
        ),
        id="negative-below-zero",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", 0), ("*.log", -1)],
            listed=["keep.log", "readme"],
        ),
        id="negative-below-zero-added-last",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", -2), ("!keep.log", -1)],
            listed=["keep.log", "readme"],
        ),
        id="minus-two-below-minus-one",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", -1), ("*.log", -2)],
            listed=["keep.log", "readme"],
        ),
        id="minus-two-below-minus-one-added-last",
    ),
    # Every ignore-file overrules a pattern weighing less than 0, too.
    param(
        PatternCase(
            ignore_files={"": ["!keep.log"]},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", -1)],
            listed=["keep.log", "readme"],
        ),
        id="negative-loses-to-ignore-files",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", 0), ("!keep.log", 0)],
            listed=["keep.log", "readme"],
        ),
        id="equal-weight-last-wins",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", 0), ("*.log", 0)],
            listed=["readme"],
        ),
        id="equal-weight-last-wins-reversed",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", -1), ("!keep.log", -1)],
            listed=["keep.log", "readme"],
        ),
        id="equal-negative-weight-last-wins",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", -1), ("*.log", -1)],
            listed=["readme"],
        ),
        id="equal-negative-weight-last-wins-reversed",
    ),
    # A pattern weighing 1 re-includes what both the root's ignore-file and a deeper
    # one ignore.
    param(
        PatternCase(
            ignore_files={"": ["*.log"], "sub": ["*.log"]},
            tree=["a.log", "keep.log", "sub/a.log", "sub/keep.log"],
            patterns=[("!keep.log", 1)],
            listed=["keep.log", "sub/keep.log"],
        ),
        id="heavy-re-includes-over-ignore-files",
    ),
    # The root's ignore-file re-includes every log, so only the heavy patterns can
    # ignore "a.log".
    param(
        PatternCase(
            ignore_files={"": ["!*.log"]},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", 1), ("!keep.log", 1)],
            listed=["keep.log", "readme"],
        ),
        id="equal-heavy-weight-last-wins",
    ),
    param(
        PatternCase(
            ignore_files={"": ["!*.log"]},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", 1), ("*.log", 1)],
            listed=["readme"],
        ),
        id="equal-heavy-weight-last-wins-reversed",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", 1), ("!keep.log", 2)],
            listed=["keep.log", "readme"],
        ),
        id="heavier-wins-added-last",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", 2), ("*.log", 1)],
            listed=["keep.log", "readme"],
        ),
        id="heavier-wins-added-first",
    ),
    # "*.tmp" is the heaviest, so it ignores "keep.tmp" even though "!keep.tmp" was
    # added after it. "!keep.log" outweighs "*.log". The root's ignore-file re-includes
    # everything, and every pattern here overrules it.
    param(
        PatternCase(
            ignore_files={"": ["!*.log", "!*.tmp"]},
            tree=["a.log", "a.tmp", "keep.log", "keep.tmp", "readme"],
            patterns=[
                ("*.tmp", 3),
                ("!keep.log", 2),
                ("*.log", 1),
                ("!keep.tmp", 1),
            ],
            listed=["keep.log", "readme"],
        ),
        id="several-heavy",
    ),
    # The root's ignore-file has no line that matches "keep.log", so the pattern
    # re-includes it there. "sub"'s ignore-file ignores every log, and overrules it.
    param(
        PatternCase(
            ignore_files={"": ["*.tmp"], "sub": ["*.log"]},
            tree=["a.log", "a.tmp", "keep.log", "sub/a.log", "sub/keep.log"],
            patterns=[("*.log", 0), ("!keep.log", 0)],
            listed=["keep.log"],
        ),
        id="light-re-include",
    ),
]


ANCHORING = [
    # Patterns are tied to the walked directory, so "/todo.txt" only matches the root's,
    # even in "tools", beside an ignore-file of its own.
    param(
        PatternCase(
            ignore_files={"tools": ["*.log"]},
            tree=["todo.txt", "tools/a.log", "tools/todo.txt"],
            patterns=[("/todo.txt", 0)],
            listed=["tools/todo.txt"],
        ),
        id="anchored-light",
    ),
    param(
        PatternCase(
            ignore_files={"tools": ["*.log"]},
            tree=["todo.txt", "tools/a.log", "tools/todo.txt"],
            patterns=[("/todo.txt", 1)],
            listed=["tools/todo.txt"],
        ),
        id="anchored-heavy",
    ),
    param(
        PatternCase(
            ignore_files={"docs": ["b.txt"]},
            tree=[
                "a.md",
                "docs/a.md",
                "docs/b.txt",
                "docs/c.txt",
                "docs/sub/a.md",
                "x/docs/a.md",
            ],
            patterns=[("docs/*.md", 0)],
            listed=["a.md", "docs/c.txt", "docs/sub/a.md", "x/docs/a.md"],
        ),
        id="anchored-middle-slash",
    ),
    # A wrong prefix for a pattern only shows when it reaches more than one level down,
    # beneath a directory with an ignore-file of its own.
    param(
        PatternCase(
            ignore_files={"a/b": ["y"]},
            tree=["a/b/x", "a/b/y", "a/b/z", "a/b/a/b/x", "c/a/b/x"],
            patterns=[("a/b/x", 1)],
            listed=["a/b/a/b/x", "a/b/z", "c/a/b/x"],
        ),
        id="anchored-deep",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "b/a.log", "b/c/a.log", "b/c/d"],
            patterns=[("*.log", 0)],
            listed=["b/c/d"],
        ),
        id="unanchored-light",
    ),
    param(
        PatternCase(
            ignore_files={"b/c": ["!a.log"]},
            tree=["a.log", "b/a.log", "b/c/a.log", "b/c/d/a.log", "b/c/d/e"],
            patterns=[("a.log", 1)],
            listed=["b/c/d/e"],
        ),
        id="unanchored-heavy",
    ),
]


PRUNING = [
    param(
        PatternCase(
            ignore_files={"": ["!build/"]},
            tree=["build/a", "keep"],
            patterns=[("build/", 1)],
            listed=["keep"],
        ),
        id="heavy-ignores-directory",
    ),
    # "build" is walked after all, and the root's ignore-file still judges what's inside
    # it.
    param(
        PatternCase(
            ignore_files={"": ["build/", "*.o"]},
            tree=["build/a", "build/b.o", "keep"],
            patterns=[("!build/", 1)],
            listed=["build/a", "keep"],
        ),
        id="heavy-re-includes-directory",
    ),
    # "build" is never walked, so nothing can re-include "build/x".
    param(
        PatternCase(
            ignore_files={"": ["build/"]},
            tree=["build/x", "build/y", "keep"],
            patterns=[("!build/x", 1)],
            listed=["keep"],
        ),
        id="heavy-cannot-reach-inside",
    ),
    # "build" itself isn't ignored, only what's inside it, so "build/x" can be
    # re-included.
    param(
        PatternCase(
            ignore_files={"": ["build/*"]},
            tree=["build/x", "build/y", "keep"],
            patterns=[("!build/x", 1)],
            listed=["build/x", "keep"],
        ),
        id="heavy-re-includes-contents",
    ),
    param(
        PatternCase(
            ignore_files={"sub": ["!build/"]},
            tree=["build/a", "sub/build/a"],
            patterns=[("build/", 0)],
            listed=["sub/build/a"],
        ),
        id="light-undone-by-nested",
    ),
    # "logs" is ignored, so its own ignore-file is never read.
    param(
        PatternCase(
            ignore_files={"logs": ["!*.log"]},
            tree=["a.log", "keep", "logs/b.log", "logs/c"],
            patterns=[("*.log", 0), ("logs/", 1)],
            listed=["keep"],
        ),
        id="ignored-directory-not-read",
    ),
]


OWN_FILE = [
    # The ignore-files are hidden, and their lines still apply.
    param(
        PatternCase(
            ignore_files={"": ["/a"], "sub": ["b"]},
            tree=["a", "b", "sub/a", "sub/b"],
            patterns=[("ignore", 0)],
            listed=["b", "sub/a"],
            ignore_ignore_files=False,
        ),
        id="ignores-every-ignore-file",
    ),
    param(
        PatternCase(
            ignore_files={"": ["/a"], "sub": ["b"]},
            tree=["a", "b", "sub/a", "sub/b"],
            patterns=[("/ignore", 1)],
            listed=["b", "sub/a", "sub/ignore"],
            ignore_ignore_files=False,
        ),
        id="ignores-root-ignore-file",
    ),
    # Leaving out the ignore-files ranks below every pattern, whatever its weight, but
    # only a heavy pattern overrules the ignore-file in "sub", which ignores itself.
    param(
        PatternCase(
            ignore_files={"": ["a"], "sub": ["ignore"]},
            tree=["a", "b", "sub/c"],
            patterns=[("!ignore", -5)],
            listed=["b", "ignore", "sub/c"],
        ),
        id="negative-re-includes",
    ),
    param(
        PatternCase(
            ignore_files={"": ["a"], "sub": ["ignore"]},
            tree=["a", "b", "sub/c"],
            patterns=[("!ignore", 0)],
            listed=["b", "ignore", "sub/c"],
        ),
        id="light-re-includes",
    ),
    param(
        PatternCase(
            ignore_files={"": ["a"], "sub": ["ignore"]},
            tree=["a", "b", "sub/c"],
            patterns=[("!ignore", 1)],
            listed=["b", "ignore", "sub/c", "sub/ignore"],
        ),
        id="heavy-re-includes",
    ),
]


NO_IGNORE_FILENAME = [
    # The file named "ignore" is an ordinary file, so its line never applies.
    param(
        PatternCase(
            ignore_files={"": ["a"]},
            tree=["a", "b.log", "sub/c.log", "sub/d"],
            patterns=[("*.log", 0)],
            listed=["a", "ignore", "sub/d"],
            name=None,
        ),
        id="patterns-alone",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("!keep.log", 1), ("*.log", 0)],
            listed=["keep.log", "readme"],
            name=None,
        ),
        id="heavy-before-light",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "keep.log", "readme"],
            patterns=[("*.log", 1), ("!keep.log", 0)],
            listed=["readme"],
            name=None,
        ),
        id="heavy-before-light-reversed",
    ),
]


TRAILING_SPACES = [
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "b"],
            patterns=[("a.log ", 0)],
            listed=["b"],
        ),
        id="light",
    ),
    param(
        PatternCase(
            ignore_files={},
            tree=["a.log", "b"],
            patterns=[("a.log ", 1)],
            listed=["b"],
            divergence=KEPT_SPACES,
        ),
        id="heavy",
    ),
    # A backslash keeps the space after it.
    param(
        PatternCase(
            ignore_files={},
            tree=["a", "a "],
            patterns=[("a\\ ", 1)],
            listed=["a"],
        ),
        id="escaped",
    ),
]


def build(root: Path, case: PatternCase) -> None:
    """Build a case's ignore-files and tree.

    Args:
        root: Path to the directory to build them in.
        case: The case to build.
    """
    make_tree_with_ignore_files(
        root,
        case.ignore_files,
        case.tree,
    )


def walk(root: Path, case: PatternCase) -> list[str]:
    """Walk a case's tree, and return every step's relative path, in order.

    Args:
        root: Path to the directory to walk.
        case: The case to walk.

    Returns:
        The relative path of every step.
    """
    return relative_paths(root, case.name, case.patterns, case.ignore_ignore_files)


@mark.parametrize("case", ANCHORING)
def test_walk__anchoring(tmp_path: Path, case: PatternCase) -> None:
    """A pattern with a "/" before its end matches paths from the walked directory."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed


@needs_git
@mark.parametrize(
    "case",
    [
        *WEIGHTS,
        *ANCHORING,
        *PRUNING,
        *OWN_FILE,
        *NO_IGNORE_FILENAME,
        *TRAILING_SPACES,
    ],
)
def test_walk__git(tmp_path: Path, case: PatternCase) -> None:
    """Git lists exactly the files that the walk yields."""
    build(tmp_path, case)
    listed = git_list_files(
        tmp_path, case.name, case.patterns, case.ignore_ignore_files
    )

    if case.divergence:
        # Git should still list something different, or the reason no longer holds.
        assert listed != case.listed
        skip(case.divergence)

    assert listed == case.listed


@needs_symlinks
def test_walk__ignored_directory_ignore_file_is_broken_symlink(tmp_path: Path) -> None:
    """A directory's ignore-file isn't read when a pattern ignores the directory."""
    # Reading "b/ignore" would raise `FileNotFoundError`.
    make_tree(tmp_path, "a", "b/c", "d")
    make_broken_symlink(tmp_path / "b" / "ignore")

    assert relative_paths(tmp_path, "ignore", [("b/", 0)]) == ["a", "d"]


@mark.parametrize("case", NO_IGNORE_FILENAME)
def test_walk__no_ignore_filename(tmp_path: Path, case: PatternCase) -> None:
    """Patterns apply when the walk reads no ignore-files, heaviest first."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed


@mark.parametrize("case", OWN_FILE)
def test_walk__own_file(tmp_path: Path, case: PatternCase) -> None:
    """A pattern can decide if an ignore-file is yielded, and its lines still apply."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed


@mark.parametrize(
    "list_paths",
    [
        param(relative_paths, id="walk"),
        param(git_list_files, marks=needs_git, id="git"),
    ],
)
def test_walk__patterns_example(
    tmp_path: Path,
    list_paths: Callable[[Path, str, Sequence[tuple[str, int]]], list[str]],
) -> None:
    """The default and overriding patterns page's example lists what it says."""
    # The example from the default and overriding patterns page, with its ignore-files
    # named as the page names them.
    make_tree(
        tmp_path,
        "backup.iso",
        "docs/guide.pdf",
        "docs/install.iso",
        "manual.pdf",
        "readme.md",
        "report.pdf",
    )

    (tmp_path / ".walkignore").write_bytes(b"!manual.pdf\n")
    (tmp_path / "docs" / ".walkignore").write_bytes(b"!*.iso\n")

    assert list_paths(tmp_path, ".walkignore", [("*.pdf", 0), ("*.iso", 1)]) == [
        "manual.pdf",
        "readme.md",
    ]


@mark.parametrize("case", PRUNING)
def test_walk__pruning(tmp_path: Path, case: PatternCase) -> None:
    """A directory that a pattern ignores is never walked."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed


@mark.parametrize("weight", [param(1, id="heavy"), param(0, id="light")])
def test_walk__root_never_judged(tmp_path: Path, weight: int) -> None:
    """The walked directory is never judged, even by a pattern that matches it."""
    root = tmp_path / "build"
    make_tree(root, "a", "build/b")

    assert relative_paths(root, patterns=[("build/", weight)]) == ["a"]


@mark.parametrize("case", TRAILING_SPACES)
def test_walk__trailing_spaces(tmp_path: Path, case: PatternCase) -> None:
    """Spaces at the end of a pattern are removed, as from a line of an ignore-file."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed


@mark.parametrize("weight", [param(1, id="heavy"), param(0, id="light")])
def test_walk__two_roots(tmp_path: Path, weight: int) -> None:
    """One walker ties its patterns to each directory it walks, in turn."""
    make_tree(tmp_path, "x", "sub/x", "sub/y")
    walker = build_walker(patterns=[("/x", weight)])

    # "/x" matches the root's "x" in the first walk, and "sub/x" in the second.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == [
        "sub/x",
        "sub/y",
    ]

    assert [step.relative_as_posix for step in walker.walk(tmp_path / "sub")] == ["y"]


@mark.parametrize("case", WEIGHTS)
def test_walk__weights(tmp_path: Path, case: PatternCase) -> None:
    """A pattern's weight says which patterns and ignore-files it overrules."""
    build(tmp_path, case)
    assert walk(tmp_path, case) == case.listed
