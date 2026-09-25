"""Unit tests for the `Mosey.walk` function."""

import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path

from pytest import MonkeyPatch, mark, param, raises

from mosey import Mosey
from tests.file_system_helpers import (
    make_broken_symlink,
    make_directory,
    make_fifo,
    make_file,
    make_nothing,
    make_symlink_to_directory,
    make_symlink_to_file,
    make_tree,
    relative_paths,
)
from tests.markers import (
    needs_fifos,
    needs_posix_permissions,
    needs_symlinks,
    needs_utf8,
)


@mark.parametrize(
    "make",
    [
        param(make_broken_symlink, marks=needs_symlinks),
        make_nothing,
    ],
)
def test_root_does_not_exist(tmp_path: Path, make: Callable[[Path], None]) -> None:
    """`FileNotFoundError` is raised when the root doesn't exist."""
    root = tmp_path / "nope"
    make(root)

    with raises(FileNotFoundError):
        Mosey().walk(root)


def test_root_is_empty() -> None:
    """`FileNotFoundError` is raised when the root is an empty string."""
    with raises(FileNotFoundError) as raised:
        Mosey().walk("")

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == ""


def test_root_is_beneath_a_file(tmp_path: Path) -> None:
    """`FileNotFoundError` is raised when one of the root's parents is a file."""
    parent = tmp_path / "parent"
    make_file(parent)
    root = parent / "root"

    with raises(FileNotFoundError) as raised:
        Mosey().walk(root)

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == os.fspath(root)


@mark.skipif(
    sys.platform == "win32",
    reason="Windows raises `FileNotFoundError` itself, so there's no cause to keep",
)
def test_root_is_beneath_a_file__cause(tmp_path: Path) -> None:
    """Linux and macOS keep the original `NotADirectoryError` as the cause."""
    parent = tmp_path / "parent"
    make_file(parent)

    with raises(FileNotFoundError) as raised:
        Mosey().walk(parent / "root")

    assert isinstance(raised.value.__cause__, NotADirectoryError)


@mark.parametrize(
    "make",
    [
        param(make_fifo, marks=needs_fifos),
        make_file,
        param(make_symlink_to_file, marks=needs_symlinks),
    ],
)
def test_root_is_not_a_directory(tmp_path: Path, make: Callable[[Path], None]) -> None:
    """`NotADirectoryError` is raised when the root isn't a directory."""
    root = tmp_path / "root"
    make(root)

    with raises(NotADirectoryError) as raised:
        Mosey().walk(root)

    assert raised.value.errno == errno.ENOTDIR
    assert raised.value.filename == os.fspath(root)


def test_root_is_not_a_directory__trailing_separator(tmp_path: Path) -> None:
    """`NotADirectoryError` is raised when a file root has a trailing separator."""
    root = tmp_path / "root"
    make_file(root)

    # A trailing separator asks the operating system to treat the file as a directory,
    # and POSIX reports that as "not a directory" -- the same error as a root beneath
    # a file, which `walk` normalises to `FileNotFoundError`. Passing a string proves
    # that `walk` strips the separator before it can be confused by that.
    with raises(NotADirectoryError) as raised:
        Mosey().walk(os.fspath(root) + os.sep)

    assert raised.value.errno == errno.ENOTDIR
    assert raised.value.filename == os.fspath(root)


@needs_symlinks
@mark.skipif(
    sys.platform == "win32",
    reason="Windows reports symlink loops differently",
)
def test_root_is_a_symlink_loop__posix(tmp_path: Path) -> None:
    """Linux and macOS raise `OSError` with `ELOOP` for a root in a symlink loop."""
    root = tmp_path / "root"
    root.symlink_to(root)

    with raises(OSError) as raised:
        Mosey().walk(root)

    # `errno.ELOOP` proves we caught the correct `OSError`.
    assert raised.value.errno == errno.ELOOP


@needs_symlinks
@mark.skipif(
    sys.platform != "win32",
    reason="Linux and macOS report symlink loops differently",
)
def test_root_is_a_symlink_loop__windows(tmp_path: Path) -> None:
    """Windows raises `OSError` with `EINVAL` for a root in a symlink loop."""
    # `OSError.winerror` only exists on Windows, and this assertion convinces pyright
    # that we can read it.
    assert sys.platform == "win32"

    root = tmp_path / "root"
    root.symlink_to(root)

    with raises(OSError) as raised:
        Mosey().walk(root)

    # Windows has no error code of its own for symlink loops, so Python falls back to
    # `EINVAL`.
    assert raised.value.errno == errno.EINVAL

    # The Windows-specific code "1921" (`ERROR_CANT_RESOLVE_FILENAME`) proves we caught
    # the correct `OSError`.
    assert raised.value.winerror == 1921


@needs_posix_permissions
def test_root_stat_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny the stat of the root."""
    parent = tmp_path / "parent"
    root = parent / "root"
    root.mkdir(parents=True)

    # Read and write but not search ("execute"), so nothing beneath the parent can be
    # `stat`-ed.
    parent.chmod(0o600)

    try:
        # Prove that the stat is denied. `walk` stats before it does anything else, so
        # that must be where it fails too.
        with raises(PermissionError):
            os.stat(root)

        with raises(PermissionError):
            Mosey().walk(root)
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        parent.chmod(0o700)


@needs_posix_permissions
def test_root_preflight_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny the preflight of the root."""
    root = tmp_path / "root"
    root.mkdir()

    # Write and search ("execute") but not read, so the root can be `stat`-ed but not
    # listed.
    root.chmod(0o300)

    try:
        # Prove that the stat is allowed, so it must be the preflight that fails.
        os.stat(root)

        with raises(PermissionError):
            Mosey().walk(root)
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        root.chmod(0o700)


@needs_posix_permissions
def test_root_search_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny searching the root."""
    root = tmp_path / "root"
    root.mkdir()

    # Read but not search ("execute"), so the root can be `stat`-ed and listed but
    # nothing inside it can be reached.
    root.chmod(0o400)

    try:
        # Prove that the stat and the preflight are allowed, so it must be the search
        # check that fails.
        os.stat(root)

        with os.scandir(root):
            pass

        with raises(PermissionError):
            Mosey().walk(root)
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        root.chmod(0o700)


def test_walk__order(tmp_path: Path) -> None:
    """Files are yielded in walk order."""
    # Created in neither the expected order nor its reverse, so the test can't pass on
    # a file system that lists a directory's entries oldest first or newest first.
    make_tree(tmp_path, "b.txt", "Z", "ba", "b/x", ".a", "b_c", "b-c")

    # Uppercase before lowercase, then the byte after "b" decides the ties, with the
    # directory "b" sorting as "b/".
    assert relative_paths(tmp_path) == [".a", "Z", "b-c", "b.txt", "b/x", "b_c", "ba"]


@needs_utf8
def test_walk__ascending_paths(tmp_path: Path) -> None:
    """Files are yielded in ascending byte order of their relative paths."""
    # The example from the walk-order page, created in neither the expected order nor
    # its reverse.
    make_tree(
        tmp_path,
        "cafz",
        "b.txt",
        "Z",
        "ba/z",
        "b/x",
        ".a",
        "café",
        "b_c",
        "b-c",
        "a",
    )

    paths = relative_paths(tmp_path)

    assert paths == [
        ".a",
        "Z",
        "a",
        "b-c",
        "b.txt",
        "b/x",
        "b_c",
        "ba/z",
        "cafz",
        "café",
    ]

    # The rule itself, so a typo in the hand-written list above can't slip through.
    assert paths == sorted(paths, key=os.fsencode)


def test_walk__depth_first(tmp_path: Path) -> None:
    """Everything inside a directory is yielded before the directory's next sibling."""
    make_tree(tmp_path, "b", "a/z", "a/b/y", "a/b/c/x")
    assert relative_paths(tmp_path) == ["a/b/c/x", "a/b/y", "a/z", "b"]


@mark.parametrize(
    "make",
    [
        make_directory,
        param(make_symlink_to_directory, marks=needs_symlinks),
    ],
)
def test_walk__steps(tmp_path: Path, make: Callable[[Path], None]) -> None:
    """Each step describes a file beneath the root."""
    root = tmp_path / "root"
    make(root)
    make_tree(root, "a/b.txt")

    [step] = Mosey().walk(root)

    assert step.name == "b.txt"
    assert step.relative_as_posix == "a/b.txt"

    # When the root is a symlink, the walk follows it. Steps keep the path to the
    # symlink, though, rather than the path to its target.
    assert step.root == root
    assert step.path == root / "a" / "b.txt"


def test_walk__relative_root(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Steps beneath a relative root have relative paths, without a leading "./"."""
    make_tree(tmp_path, "a/b.txt")
    monkeypatch.chdir(tmp_path)

    [step] = Mosey().walk(".")

    assert step.relative_as_posix == "a/b.txt"
    assert step.root == Path(".")
    assert step.path == Path("a", "b.txt")


@mark.parametrize(
    "paths",
    [
        param((), id="empty"),
        param(("a/b/", "c/"), id="only-directories"),
    ],
)
def test_walk__no_files(tmp_path: Path, paths: tuple[str, ...]) -> None:
    """Nothing is yielded when there are no files, because directories aren't."""
    make_tree(tmp_path, *paths)

    assert relative_paths(tmp_path) == []


@needs_symlinks
def test_walk__symlink_to_file(tmp_path: Path) -> None:
    """A symlink to a file is yielded as a file."""
    make_symlink_to_file(tmp_path / "link")

    assert relative_paths(tmp_path) == ["link", "link.target"]


@needs_symlinks
def test_walk__symlink_to_directory(tmp_path: Path) -> None:
    """A symlink to a directory is yielded as a file, and never walked into."""
    make_symlink_to_directory(tmp_path / "link")
    make_tree(tmp_path, "link.target/x")

    # If the walk had followed the symlink, it would have yielded "link/x" as well. If
    # it had sorted the symlink as a directory, "link.target/x" would have come first.
    assert relative_paths(tmp_path) == ["link", "link.target/x"]


def test_walk__lazy_root(tmp_path: Path) -> None:
    """The root isn't listed until the first step is requested."""
    steps = Mosey().walk(tmp_path)
    make_file(tmp_path / "a")

    assert [step.relative_as_posix for step in steps] == ["a"]


def test_walk__lazy_directories(tmp_path: Path) -> None:
    """A directory isn't listed until the walk reaches it."""
    make_tree(tmp_path, "a/x", "b/")
    steps = Mosey().walk(tmp_path)

    assert next(steps).relative_as_posix == "a/x"

    # The walk has listed the root, so it knows "b" exists, but it hasn't listed "b"
    # itself yet.
    make_file(tmp_path / "b" / "y")

    assert [step.relative_as_posix for step in steps] == ["b/y"]


def test_walk__directory_vanishes(tmp_path: Path) -> None:
    """`FileNotFoundError` is raised when the walk reaches a directory that's gone."""
    make_tree(tmp_path, "a/x", "b/")
    steps = Mosey().walk(tmp_path)

    assert next(steps).relative_as_posix == "a/x"

    # The walk has listed the root, so it knows "b" exists, but it hasn't listed "b"
    # itself yet.
    (tmp_path / "b").rmdir()

    with raises(FileNotFoundError) as raised:
        next(steps)

    # Proves that it was "b" that couldn't be listed, not the root.
    assert raised.value.filename == os.fspath(tmp_path / "b")


@needs_posix_permissions
def test_walk__directory_listing_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when the walk reaches a directory it can't list."""
    make_tree(tmp_path, "a.txt", "b/")
    denied = tmp_path / "b"

    # Write and search ("execute") but not read, so "b" can't be listed.
    denied.chmod(0o300)

    try:
        steps = Mosey().walk(tmp_path)

        assert next(steps).relative_as_posix == "a.txt"

        with raises(PermissionError) as raised:
            next(steps)

        # Proves that it was "b" that couldn't be listed, not the root.
        assert raised.value.filename == os.fspath(denied)
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        denied.chmod(0o700)
