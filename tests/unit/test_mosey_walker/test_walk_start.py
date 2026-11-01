"""Unit tests for the `MoseyWalker.walk` function with a directory to start in.

The tests of `walk`'s checks test `MoseyWalker.check_walk_can_start` too, which runs
exactly the same checks.
"""

import errno
import os
import stat
import sys
from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from typing import NamedTuple

from pytest import MonkeyPatch, fail, mark, param, raises

from mosey import Mosey
from tests.file_system_helpers import (
    Check,
    build_walker,
    make_broken_symlink,
    make_fifo,
    make_file,
    make_junction,
    make_socket,
    make_symlink_to_directory,
    make_symlink_to_file,
    make_tree,
    make_tree_with_ignore_files,
    relative_paths,
    symlinks_allowed,
    write_ignore_files,
)
from tests.git_oracle import git_list_files
from tests.markers import (
    each_check,
    needs_fifos,
    needs_git,
    needs_junctions,
    needs_posix_permissions,
    needs_symlinks,
    needs_unix_sockets,
)
from tests.random_trees import build, random_tree
from tests.timeouts import alarm

SEED = f"{sys.platform}-{sys.version_info.major}.{sys.version_info.minor}/start"
"""The seed that every random tree is made from, along with its index.

Like the seeds in `test_walk_random`, each operating system and version of Python has
its own, and it differs from theirs, so these trees aren't theirs.
"""

TREES = 100
"""How many random trees to start in every directory of."""


class StartCase(NamedTuple):
    """Ignore-files, the rest of a tree, a directory to start in, and what's yielded."""

    ignore_files: dict[str, list[str] | bytes]
    """Each ignore-file's lines or exact bytes, by directory.

    Each directory is "" for the root, or a "/"-separated path. Every ignore-file is
    named "ignore".
    """

    tree: list[str]
    """The rest of the tree, as `make_tree` takes it."""

    start: str
    """The directory to start in."""

    listed: list[str]
    """The "/"-separated paths of the files the walk yields, in walk order."""

    patterns: tuple[tuple[str, int], ...] = ()
    """Each pattern given in code, and its weight, in the order to add them."""


START_CASES = [
    param(
        StartCase(
            ignore_files={"": ["*.log"]},
            tree=["file.md", "other/sub/file.md", "sub/file.md", "sub/notes.log"],
            start="sub",
            listed=["sub/file.md"],
        ),
        id="root-ignore-file",
    ),
    param(
        StartCase(
            ignore_files={"": ["*.log"], "docs": ["drafts/"]},
            tree=[
                "docs/guides/drafts/next.md",
                "docs/guides/install.log",
                "docs/guides/install.md",
                "docs/index.md",
                "readme.md",
            ],
            start="docs/guides",
            listed=["docs/guides/install.md"],
        ),
        id="ignore-files-on-the-way-down",
    ),
    param(
        StartCase(
            ignore_files={"": ["/a/b/c.txt"]},
            tree=["a/b/c.txt", "a/b/d.txt", "c.txt"],
            start="a/b",
            listed=["a/b/d.txt"],
        ),
        id="anchored-path-from-the-root",
    ),
    param(
        StartCase(
            ignore_files={"": ["*.txt"], "a": ["!keep.txt"]},
            tree=["a/b/drop.txt", "a/b/keep.txt"],
            start="a/b",
            listed=["a/b/keep.txt"],
        ),
        id="re-included-on-the-way-down",
    ),
    param(
        StartCase(
            ignore_files={"a/b": ["*.md"]},
            tree=["a/b/c/d.md", "a/b/c/d.txt"],
            start="a/b/c",
            listed=["a/b/c/d.txt"],
        ),
        id="ignore-file-in-the-parent",
    ),
    param(
        StartCase(
            ignore_files={"a": ["*.md"]},
            tree=["a/b.md", "a/c.txt", "a/d/e.md", "a/d/f.txt"],
            start="a",
            listed=["a/c.txt", "a/d/f.txt"],
        ),
        id="ignore-file-in-start",
    ),
    param(
        StartCase(
            ignore_files={"": ["b/"]},
            tree=["a/b/c.txt", "a/d.txt"],
            start="a/b",
            listed=[],
        ),
        id="start-ignored",
    ),
    param(
        StartCase(
            ignore_files={"": ["a/"]},
            tree=["a/b/c.txt"],
            start="a/b",
            listed=[],
        ),
        id="above-start-ignored",
    ),
    param(
        StartCase(
            ignore_files={"": ["a/", "!a/b/"]},
            tree=["a/b/c.txt"],
            start="a/b",
            listed=[],
        ),
        id="above-start-ignored-start-re-included",
    ),
    param(
        StartCase(
            ignore_files={"": ["a/*", "!a/b/"]},
            tree=["a/b/c.txt", "a/d.txt"],
            start="a/b",
            listed=["a/b/c.txt"],
        ),
        id="start-re-included",
    ),
    param(
        StartCase(
            ignore_files={},
            tree=["a/b/c.txt", "a/b/d/e.txt", "a/b.txt", "a/b-c/d.txt", "b.txt"],
            start="a/b",
            listed=["a/b/c.txt", "a/b/d/e.txt"],
        ),
        id="nothing-ignored",
    ),
    param(
        StartCase(
            ignore_files={},
            tree=["a/b/", "a/c.txt"],
            start="a/b",
            listed=[],
        ),
        id="empty-start",
    ),
    param(
        StartCase(
            ignore_files={"": ["*"]},
            tree=["a/b/c.md", "a/b/c.txt"],
            start="a/b",
            listed=["a/b/c.txt"],
            patterns=(("!a/", 1), ("!a/b/", 1), ("!*.txt", 1)),
        ),
        id="heavy-pattern-overrules",
    ),
    param(
        StartCase(
            ignore_files={"": ["!b/"]},
            tree=["a/b/c.txt"],
            start="a/b",
            listed=["a/b/c.txt"],
            patterns=(("b/", 0),),
        ),
        id="light-pattern-overruled",
    ),
    param(
        StartCase(
            ignore_files={},
            tree=["a/b/c.txt"],
            start="a/b",
            listed=[],
            patterns=(("b/", 0),),
        ),
        id="start-ignored-by-pattern",
    ),
    param(
        StartCase(
            ignore_files={"": ["ignore"], "a/b": ["c.txt"]},
            tree=["a/b/c.txt", "a/b/d.txt"],
            start="a/b",
            listed=["a/b/d.txt"],
        ),
        id="ignore-files-left-out",
    ),
]


@mark.parametrize("case", START_CASES)
def test_walk__start(tmp_path: Path, case: StartCase) -> None:
    """The walk yields what a walk of the root yields within the directory."""
    make_tree_with_ignore_files(tmp_path, case.ignore_files, case.tree)
    walker = build_walker("ignore", case.patterns)

    steps = walker.walk(tmp_path, start=case.start)
    walked = [step.relative_as_posix for step in steps]
    assert walked == case.listed

    everything = relative_paths(tmp_path, "ignore", case.patterns)
    assert walked == [path for path in everything if path.startswith(f"{case.start}/")]


@mark.skipif(sys.platform == "win32", reason="Windows names can't hold a backslash")
def test_walk__start__backslash_in_a_name(tmp_path: Path) -> None:
    """On Linux and macOS, a backslash is part of a name, as it is in the root."""
    make_tree(tmp_path, "a\\b/c.txt", "a/b/d.txt")

    steps = Mosey().build().walk(tmp_path, start="a\\b")
    assert [step.relative_as_posix for step in steps] == ["a\\b/c.txt"]


@mark.skipif(sys.platform != "win32", reason="Only Windows separates with backslashes")
def test_walk__start__backslashes(tmp_path: Path) -> None:
    """On Windows, a start can use backslashes, but each step still uses slashes."""
    make_tree(tmp_path, "a/b/c.txt")

    steps = Mosey().build().walk(tmp_path, start="a\\b")
    assert [step.relative_as_posix for step in steps] == ["a/b/c.txt"]


@each_check
@mark.parametrize(
    "make",
    [
        param(make_fifo, marks=needs_fifos),
        make_file,
        param(make_socket, marks=needs_unix_sockets),
        param(make_symlink_to_file, marks=needs_symlinks),
        param(make_symlink_to_directory, marks=needs_symlinks),
    ],
)
def test_walk__start__beneath_a_non_directory(
    tmp_path: Path,
    make: Callable[[Path], None],
    check: Check,
) -> None:
    """`FileNotFoundError` is raised when the start is beneath anything but a directory.

    That's a file, a symlink, or something that's never a candidate, like a FIFO.
    """
    make_tree(tmp_path, "a/")
    make(tmp_path / "a" / "b")

    # A symlink to a directory has something beneath it, but a walk never goes there.
    if (tmp_path / "a" / "b").is_dir():
        make_tree(tmp_path / "a" / "b", "c/")

    # Opening a FIFO waits for a writer, which here would be never. The walk should
    # never open one, but if it does, the alarm fails the test rather than hangs it.
    guard = (
        alarm(1, "Waited for the FIFO to be opened for writing")
        if make is make_fifo
        else nullcontext()
    )

    with guard, raises(FileNotFoundError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start="a/b/c",
        )

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == os.fspath(tmp_path / "a" / "b" / "c")


@each_check
def test_walk__start__checked_before_root(
    tmp_path: Path,
    check: Check,
) -> None:
    """The start's shape is checked before the root is."""
    with raises(ValueError, match="isn't a path beneath the root"):
        check(
            Mosey().build(),
            tmp_path / "missing",
            start="/a",
        )


def test_walk__start__checked_eagerly(tmp_path: Path) -> None:
    """The start is checked when `walk` is called, before any step is requested."""
    make_tree(tmp_path, "a.txt")

    # No `next` or `list`: the call alone has to raise.
    with raises(FileNotFoundError):
        Mosey().build().walk(tmp_path, start="a")


def test_walk__start__default(tmp_path: Path) -> None:
    """Starting in "." walks the root, as leaving `start` out does."""
    write_ignore_files(tmp_path, {"": ["b.txt"]})
    make_tree(tmp_path, "a.txt", "b.txt", "c/d.txt")
    walker = build_walker("ignore")

    expect = ["a.txt", "c/d.txt"]
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == expect
    assert [s.relative_as_posix for s in walker.walk(tmp_path, start=".")] == expect


@each_check
@mark.skipif(sys.platform == "win32", reason="Windows has no /dev/null")
def test_walk__start__device(check: Check) -> None:
    """A device is never a candidate, but it exists, so it isn't a directory.

    Only the root user can create a device, so this uses the one every Linux and macOS
    system has: "/dev/null", a character device.
    """
    assert stat.S_ISCHR(os.lstat("/dev/null").st_mode)

    walker = Mosey().build()

    with raises(NotADirectoryError) as not_a_directory:
        check(
            walker,
            "/dev",
            start="null",
        )

    assert not_a_directory.value.errno == errno.ENOTDIR
    assert not_a_directory.value.filename == "/dev/null"

    with raises(FileNotFoundError) as not_found:
        check(
            walker,
            "/dev",
            start="null/a",
        )

    assert not_found.value.errno == errno.ENOENT
    assert not_found.value.filename == "/dev/null/a"


@each_check
@mark.parametrize("start", ["a/b", "a/b/c"])
def test_walk__start__does_not_exist(
    tmp_path: Path,
    start: str,
    check: Check,
) -> None:
    """`FileNotFoundError` is raised when the start doesn't exist."""
    make_tree(tmp_path, "a/")

    with raises(FileNotFoundError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start=start,
        )

    assert raised.value.errno == errno.ENOENT


@each_check
@mark.skipif(sys.platform != "win32", reason="Only Windows has drives")
def test_walk__start__drive(
    tmp_path: Path,
    check: Check,
) -> None:
    """`ValueError` is raised when the start has a drive."""
    root = tmp_path / "root"
    make_tree(root, "sub/file.txt")

    with raises(ValueError, match="isn't a path beneath the root"):
        check(
            Mosey().build(),
            root,
            start=(root / "sub").as_posix(),
        )

    with raises(ValueError, match="isn't a path beneath the root"):
        check(
            Mosey().build(),
            root,
            start=Path(tmp_path.drive, "sub"),
        )


@each_check
@mark.skipif(sys.platform != "win32", reason="Only Windows has drives")
def test_walk__start__drive_in_a_name(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    check: Check,
) -> None:
    """A name partway down that looks like a drive is looked for beneath the root."""
    root = tmp_path / "root"
    make_tree(root, "a/", "sub/file.txt")

    # From the drive's root, "C:" alone is the drive's working directory, so
    # "a/C:/Users/me/root/sub" would reach the real directory if the drive were
    # honoured.
    monkeypatch.chdir(tmp_path.anchor)
    start = "a/" + (root / "sub").as_posix()

    with raises(OSError):
        check(
            Mosey().build(),
            root,
            start=start,
        )


@each_check
def test_walk__start__empty(
    tmp_path: Path,
    check: Check,
) -> None:
    """`FileNotFoundError` is raised when the start is empty, as for the root."""
    with raises(FileNotFoundError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start="",
        )

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == ""


@needs_git
@mark.parametrize("case", START_CASES)
def test_walk__start__git(tmp_path: Path, case: StartCase) -> None:
    """Git lists the same files within the directory."""
    make_tree_with_ignore_files(tmp_path, case.ignore_files, case.tree)
    listed = git_list_files(tmp_path, "ignore", case.patterns)

    assert [path for path in listed if path.startswith(f"{case.start}/")] == case.listed


@needs_symlinks
def test_walk__start__ignore_symlinks(tmp_path: Path) -> None:
    """A walker that ignores symlinks yields none within the start either."""
    make_tree(tmp_path, "a/b/c.txt")
    make_symlink_to_file(tmp_path / "a" / "b" / "d")
    walker = build_walker("ignore", ignore_symlinks=True)

    walked = [step.relative_as_posix for step in walker.walk(tmp_path, start="a/b")]
    assert walked == ["a/b/c.txt", "a/b/d.target"]


def test_walk__start__lazy(tmp_path: Path) -> None:
    """Nothing is read until the first step is requested."""
    make_tree(tmp_path, "a/b/c.txt")
    steps = build_walker("ignore").walk(tmp_path, start="a/b")

    # The root's ignore-file is written after `walk`, so it only applies if the walk
    # reads it lazily.
    write_ignore_files(tmp_path, {"": ["c.txt"]})

    assert list(steps) == []


@each_check
def test_walk__start__missing(
    tmp_path: Path,
    check: Check,
) -> None:
    """`FileNotFoundError` names the first missing directory."""
    make_tree(tmp_path, "a/")

    with raises(FileNotFoundError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start="a/b/c",
        )

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == os.fspath(tmp_path / "a" / "b")


@each_check
def test_walk__start__missing_beneath_ignored(
    tmp_path: Path,
    check: Check,
) -> None:
    """A start that doesn't exist raises, even when a directory above it is ignored."""
    write_ignore_files(tmp_path, {"": ["a/"]})
    make_tree(tmp_path, "a/")

    with raises(FileNotFoundError):
        check(
            build_walker("ignore"),
            tmp_path,
            start="a/b",
        )


@each_check
@mark.parametrize(
    "make",
    [
        param(make_fifo, marks=needs_fifos),
        make_file,
        param(make_socket, marks=needs_unix_sockets),
        param(make_symlink_to_file, marks=needs_symlinks),
        param(make_symlink_to_directory, marks=needs_symlinks),
        param(make_broken_symlink, marks=needs_symlinks),
    ],
)
def test_walk__start__not_a_directory(
    tmp_path: Path,
    make: Callable[[Path], None],
    check: Check,
) -> None:
    """`NotADirectoryError` is raised when the start is anything but a directory.

    That's a file, a symlink, or something that's never a candidate, like a FIFO.
    """
    make_tree(tmp_path, "a/")
    make(tmp_path / "a" / "b")

    # Opening a FIFO waits for a writer, which here would be never. The walk should
    # never open one, but if it does, the alarm fails the test rather than hangs it.
    guard = (
        alarm(1, "Waited for the FIFO to be opened for writing")
        if make is make_fifo
        else nullcontext()
    )

    with guard, raises(NotADirectoryError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start="a/b",
        )

    assert raised.value.errno == errno.ENOTDIR
    assert raised.value.filename == os.fspath(tmp_path / "a" / "b")


@each_check
@mark.parametrize("start", ["/", "/a", "..", "a/..", "a/../a", Path("/a")])
def test_walk__start__not_beneath_the_root(
    tmp_path: Path,
    start: os.PathLike[str] | str,
    check: Check,
) -> None:
    """`ValueError` is raised when the start isn't a path beneath the root."""
    make_tree(tmp_path, "a/b/")

    with raises(ValueError, match="isn't a path beneath the root"):
        check(
            Mosey().build(),
            tmp_path,
            start=start,
        )


@each_check
def test_walk__start__null_character(
    tmp_path: Path,
    check: Check,
) -> None:
    """`ValueError` is raised when the start holds a null character, as for the root."""
    make_tree(tmp_path, "a/")

    with raises(ValueError):
        check(
            Mosey().build(),
            tmp_path,
            start="a/\x00",
        )


@each_check
@needs_posix_permissions
def test_walk__start__parent_listing_is_denied(
    tmp_path: Path,
    check: Check,
) -> None:
    """`PermissionError` is raised when permissions deny listing a start's parent."""
    make_tree(tmp_path, "a/b/c.txt")
    walker = build_walker("ignore")

    # Write and search ("execute") but not read, so the start could be reached, but its
    # parent can't be listed to find it.
    (tmp_path / "a").chmod(0o300)

    try:
        with raises(PermissionError) as raised:
            check(
                walker,
                tmp_path,
                start="a/b",
            )

    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "a").chmod(0o700)

    assert raised.value.filename == os.fspath(tmp_path / "a")


@each_check
@needs_posix_permissions
def test_walk__start__preflight_is_denied(
    tmp_path: Path,
    check: Check,
) -> None:
    """`PermissionError` is raised when permissions deny listing the start."""
    make_tree(tmp_path, "a/b/c.txt")

    # Write and search ("execute") but not read, so the start can be `stat`-ed but not
    # listed.
    (tmp_path / "a" / "b").chmod(0o300)

    try:
        with raises(PermissionError) as raised:
            check(
                Mosey().build(),
                tmp_path,
                start="a/b",
            )

    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "a" / "b").chmod(0o700)

    assert raised.value.filename == os.fspath(tmp_path / "a" / "b")


def test_walk__start__random_trees(tmp_path: Path) -> None:
    """Starting in each directory yields what a walk of the root yields within it."""
    symlinks = symlinks_allowed()

    for index in range(TREES):
        case = random_tree(
            SEED,
            index,
            symlinks=symlinks,
            ignore_directories=True,
            patterns=index % 2 == 1,
        )

        root = tmp_path / str(index)
        build(root, case)

        made = (
            f"random_tree({SEED!r}, {index}, symlinks={symlinks}, "
            f"ignore_directories=True, patterns={index % 2 == 1})"
        )

        walker = build_walker(case.ignore_filename, case.patterns)
        everything = [step.relative_as_posix for step in walker.walk(root)]

        for directory, names, _ in os.walk(root):
            for name in names:
                path = Path(directory, name)

                # A walk never walks into a symlink, so it can't start in one.
                if path.is_symlink():
                    continue

                start = path.relative_to(root)
                prefix = f"{start.as_posix()}/"

                walked = [s.relative_as_posix for s in walker.walk(root, start=start)]
                expect = [p for p in everything if p.startswith(prefix)]

                if walked != expect:
                    fail(
                        f"{made} starting in {start!r} walks differently:\n{case!r}\n"
                        f"Expected: {expect!r}\nWalked: {walked!r}",
                        pytrace=False,
                    )


def test_walk__start__relative_root(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """A relative root and a start walk the directory beneath the working directory."""
    make_tree(tmp_path, "root/a/b.txt", "root/c.txt")
    monkeypatch.chdir(tmp_path)

    steps = list(Mosey().build().walk("root", start="a"))

    assert [step.relative_as_posix for step in steps] == ["a/b.txt"]
    assert [step.path for step in steps] == [Path("root/a/b.txt")]


@needs_posix_permissions
def test_walk__start__siblings_not_listed(tmp_path: Path) -> None:
    """Nothing beside the start, or the directories above it, is listed."""
    make_tree(tmp_path, "a/b/c.txt", "a/d/e.txt", "f/g.txt")
    walker = build_walker("ignore")

    # Write and search ("execute") but not read, so listing either one would fail.
    (tmp_path / "a" / "d").chmod(0o300)
    (tmp_path / "f").chmod(0o300)

    try:
        steps = list(walker.walk(tmp_path, start="a/b"))
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "a" / "d").chmod(0o700)
        (tmp_path / "f").chmod(0o700)

    assert [step.relative_as_posix for step in steps] == ["a/b/c.txt"]


@each_check
@mark.parametrize(
    ("start", "missing"),
    [
        param("A/b", "A", id="first-name"),
        param("a/B", "a/B", id="last-name"),
        param("cafe\u0301", "cafe\u0301", id="decomposed"),
    ],
)
def test_walk__start__spelled_differently(
    tmp_path: Path,
    start: str,
    missing: str,
    check: Check,
) -> None:
    """`FileNotFoundError` is raised when a name isn't spelled as it's listed.

    That's so even on a file system that would find the directory by that spelling,
    like macOS's and Windows' by default.
    """
    make_tree(tmp_path, "a/b/c.txt", "caf\u00e9/d.txt")

    # macOS's file system keeps names as they're given, so "café" stays composed.
    with raises(FileNotFoundError) as raised:
        check(
            Mosey().build(),
            tmp_path,
            start=start,
        )

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == os.fspath(tmp_path.joinpath(*missing.split("/")))


@each_check
@needs_posix_permissions
def test_walk__start__stat_is_denied(
    tmp_path: Path,
    check: Check,
) -> None:
    """`PermissionError` is raised when permissions deny reaching the start."""
    make_tree(tmp_path, "a/b/c.txt")

    # Read and write but not search ("execute"), so nothing beneath "a" can be reached.
    (tmp_path / "a").chmod(0o600)

    try:
        with raises(PermissionError):
            check(
                Mosey().build(),
                tmp_path,
                start="a/b",
            )

    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "a").chmod(0o700)


@mark.parametrize("ignore_filename", ["ignore", None])
def test_walk__start__steps(tmp_path: Path, ignore_filename: str | None) -> None:
    """Each step is relative to the root, and its path is within the start."""
    make_tree(tmp_path, "a/b/c.txt", "a/b/d/e.txt")
    walker = build_walker(ignore_filename)

    steps = list(walker.walk(tmp_path, start="a/b"))

    assert [step.name for step in steps] == ["c.txt", "e.txt"]
    assert [step.relative_as_posix for step in steps] == ["a/b/c.txt", "a/b/d/e.txt"]
    assert [step.path for step in steps] == [
        tmp_path / "a" / "b" / "c.txt",
        tmp_path / "a" / "b" / "d" / "e.txt",
    ]
    assert [step.root for step in steps] == [tmp_path, tmp_path]


@each_check
@needs_symlinks
@mark.parametrize("ignore_symlinks", [False, True])
def test_walk__start__symlink_when_ignoring_symlinks(
    tmp_path: Path,
    ignore_symlinks: bool,
    check: Check,
) -> None:
    """A symlinked start raises the same whether or not the walker ignores symlinks."""
    make_tree(tmp_path, "a/")
    make_symlink_to_directory(tmp_path / "a" / "b")
    walker = build_walker(
        "ignore",
        ignore_symlinks=ignore_symlinks,
    )

    with raises(NotADirectoryError) as raised:
        check(
            walker,
            tmp_path,
            start="a/b",
        )

    assert raised.value.errno == errno.ENOTDIR
    assert raised.value.filename == os.fspath(tmp_path / "a" / "b")


@needs_junctions
def test_walk__start__through_a_junction(tmp_path: Path) -> None:
    """A junction is a directory, so the walk can start in or through one."""
    make_tree(tmp_path, "a/")
    make_junction(tmp_path / "a" / "b")
    make_tree(tmp_path / "a" / "b", "c/d.txt")
    walker = build_walker("ignore")

    expect = ["a/b/c/d.txt"]
    assert [s.relative_as_posix for s in walker.walk(tmp_path, start="a/b")] == expect
    assert [s.relative_as_posix for s in walker.walk(tmp_path, start="a/b/c")] == expect


@mark.parametrize(
    "start",
    ["a/b", "a/b/", "a//b", "./a/b", "a/./b", Path("a/b"), Path("a", "b")],
)
def test_walk__start__tidied(tmp_path: Path, start: os.PathLike[str] | str) -> None:
    """The start is tidied up like a `Path`, so each step begins with its tidy form."""
    make_tree(tmp_path, "a/b/c.txt", "a/d.txt")

    steps = Mosey().build().walk(tmp_path, start=start)
    assert [step.relative_as_posix for step in steps] == ["a/b/c.txt"]
