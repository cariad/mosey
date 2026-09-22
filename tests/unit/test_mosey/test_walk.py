"""Unit tests for the `Mosey.walk` function."""

import errno
import os
import sys
from collections.abc import Callable
from pathlib import Path

from pytest import mark, param, raises

from mosey import Mosey
from tests.file_system_helpers import (
    can_make_symlinks,
    make_broken_symlink,
    make_directory,
    make_fifo,
    make_file,
    make_nothing,
    make_symlink_to_directory,
    make_symlink_to_file,
)

needs_posix_permissions = mark.skipif(
    # The Windows check must come first because `os.geteuid` doesn't exist there.
    sys.platform == "win32" or os.geteuid() == 0,
    reason="`chmod` can't deny access on Windows or to the root user",
)
"""Skips a test that relies on `chmod` to deny access.

Such a test can't be set up:

- On Windows, where `chmod` can only toggle the read-only flag
- As the root user, who bypasses permission checks.
"""

needs_symlinks = mark.skipif(
    # GitHub Actions' Windows runners *should* be able to create symlinks, so let's fail
    # rather than skip if that configuration changes.
    not can_make_symlinks() and not os.environ.get("CI"),
    reason="Windows needs admin rights or Developer Mode to create symlinks",
)
"""Skips a test that relies on creating symlinks, unless running in CI."""


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
        param(
            make_fifo,
            marks=mark.skipif(
                not hasattr(os, "mkfifo"),
                reason="FIFOs can't be created on this platform",
            ),
        ),
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


@mark.parametrize(
    "make",
    [
        make_directory,
        param(make_symlink_to_directory, marks=needs_symlinks),
    ],
)
def test_walk_is_not_implemented(tmp_path: Path, make: Callable[[Path], None]) -> None:
    """`NotImplementedError` is raised when the root passes validation."""
    # TODO: Replace this with real tests when the walk is implemented.
    root = tmp_path / "root"
    make(root)

    with raises(NotImplementedError):
        Mosey().walk(root)
