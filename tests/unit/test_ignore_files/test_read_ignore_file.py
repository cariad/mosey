"""Unit tests for the `read_ignore_file` function."""

import errno
import os
import sys
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from pytest import mark, param, raises

from mosey.ignore_files import read_ignore_file
from tests.file_system_helpers import (
    make_broken_symlink,
    make_directory,
    make_fifo,
    make_file,
    make_nothing,
    make_symlink_to_directory,
    make_symlink_to_file,
    symlink_target,
)
from tests.markers import needs_fifos, needs_posix_permissions, needs_symlinks
from tests.timeouts import alarm


@mark.parametrize(
    "data",
    [
        param(
            b"",
            id="empty",
        ),
        # Every byte value, so we'd notice if anything were translated on the way in.
        param(
            bytes(range(256)),
            id="every-byte",
        ),
    ],
)
def test_read_ignore_file(tmp_path: Path, data: bytes) -> None:
    """A regular file's contents are returned exactly, even when there are none."""
    path = tmp_path / "ignore"
    path.write_bytes(data)

    assert read_ignore_file(os.fspath(path)) == data


@mark.parametrize(
    "make",
    [
        param(
            make_directory,
            id="directory",
        ),
        param(
            make_file,
            id="file",
        ),
    ],
)
def test_read_ignore_file__closes(tmp_path: Path, make: Callable[[Path], None]) -> None:
    """The file is closed afterwards, even when reading it fails."""
    path = tmp_path / "ignore"
    make(path)

    probe = tmp_path / "probe"
    make_file(probe)

    # New file descriptors take the lowest free number, so if the read leaves its file
    # open, opening the probe afterwards gets a different number than before.
    before = os.open(probe, os.O_RDONLY)
    os.close(before)

    # Linux and macOS open a directory, then fail to read it, so that row checks that
    # the file is closed after a failed read too.
    with suppress(OSError):
        read_ignore_file(os.fspath(path))

    after = os.open(probe, os.O_RDONLY)
    os.close(after)

    assert after == before


@mark.parametrize(
    "make",
    [
        param(
            make_directory,
            id="directory",
        ),
        param(
            make_symlink_to_directory,
            marks=needs_symlinks,
            id="symlink-to-directory",
        ),
    ],
)
def test_read_ignore_file__directory(
    tmp_path: Path,
    make: Callable[[Path], None],
) -> None:
    """An error is raised for a directory, or a symlink to one."""
    file = tmp_path / "ignore"
    make(file)
    path = os.fspath(file)

    # Linux and macOS open a directory but can't read it. Windows can't open it at all.
    with raises(OSError) as raised:
        read_ignore_file(path)

    assert raised.value.filename == path


@mark.parametrize(
    "make",
    [
        param(
            make_nothing,
            id="missing",
        ),
        param(
            make_broken_symlink,
            marks=needs_symlinks,
            id="broken-symlink",
        ),
    ],
)
def test_read_ignore_file__does_not_exist(
    tmp_path: Path,
    make: Callable[[Path], None],
) -> None:
    """`FileNotFoundError` is raised for a missing file, or a broken symlink."""
    file = tmp_path / "ignore"
    make(file)
    path = os.fspath(file)

    with raises(FileNotFoundError) as raised:
        read_ignore_file(path)

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == path


@needs_fifos
def test_read_ignore_file__fifo(tmp_path: Path) -> None:
    """A FIFO reads as empty, without waiting for a writer to open it."""
    path = tmp_path / "ignore"
    make_fifo(path)

    # Opening a FIFO normally waits until something opens it to write, which here would
    # be never. So we set an alarm: if the read waits for a second, the alarm interrupts
    # it, and the test fails rather than hangs.
    with alarm(1, "Waited for the FIFO to be opened for writing"):
        assert read_ignore_file(os.fspath(path)) == b""


@mark.skipif(
    sys.platform != "win32",
    reason="Only Windows refuses to read a part of a file that's locked",
)
def test_read_ignore_file__locked(tmp_path: Path) -> None:
    """An error while reading the file names it, like an error while opening it."""
    file = tmp_path / "ignore"
    file.write_bytes(b"a\n")
    path = os.fspath(file)

    # `msvcrt` only exists on Windows. This assertion convinces Pyright that we can use
    # it.
    assert sys.platform == "win32"
    import msvcrt

    # Lock the file's contents through a descriptor of our own. Windows still lets
    # `read_ignore_file` open the file, but then refuses to let it read them.
    fd = os.open(path, os.O_RDWR)

    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 2)

        with raises(PermissionError) as raised:
            read_ignore_file(path)

        # Microsoft asks for locks to be released before closing.
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 2)
    finally:
        os.close(fd)

    assert raised.value.errno == errno.EACCES
    assert raised.value.filename == path


@needs_posix_permissions
def test_read_ignore_file__read_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny reading the file."""
    file = tmp_path / "ignore"
    file.write_bytes(b"a\n")
    path = os.fspath(file)

    # Write but not read.
    file.chmod(0o200)

    try:
        with raises(PermissionError) as raised:
            read_ignore_file(path)

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == path
    finally:
        # Leave the file readable, as we found it.
        file.chmod(0o600)


@needs_symlinks
def test_read_ignore_file__symlink(tmp_path: Path) -> None:
    """A symlink is followed, and its target's contents are returned."""
    path = tmp_path / "ignore"
    make_symlink_to_file(path)
    symlink_target(path).write_bytes(b"a\n")

    assert read_ignore_file(os.fspath(path)) == b"a\n"
