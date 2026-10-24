"""Unit tests for the `list_candidates` function."""

import errno
import os
from collections.abc import Callable
from pathlib import Path

from pytest import mark, param, raises

from mosey.candidate import Candidate
from mosey.directories import list_candidates
from tests.file_system_helpers import (
    make_broken_symlink,
    make_fifo,
    make_file,
    make_junction,
    make_symlink_loop,
    make_symlink_to_directory,
    make_symlink_to_file,
    make_tree,
)
from tests.markers import (
    needs_fifos,
    needs_junctions,
    needs_posix_permissions,
    needs_symlinks,
)


@needs_symlinks
def test_list_candidates__broken_symlink(tmp_path: Path) -> None:
    """A broken symlink is a candidate file, like any symlink."""
    make_broken_symlink(tmp_path / "link")

    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            "link",
            False,  # Is a directory
            True,  # Is a symlink
        ),
    ]

    assert candidates == expect


def test_list_candidates__does_not_exist(tmp_path: Path) -> None:
    """`FileNotFoundError` is raised when the directory doesn't exist."""
    directory = os.fspath(tmp_path / "nope")

    with raises(FileNotFoundError) as raised:
        list_candidates(
            directory,
        )

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == directory


@mark.parametrize(
    ("path", "expect"),
    [
        param(
            ".git/",
            (
                ".git",
                True,  # Is a directory
                False,  # Is a symlink
            ),
            id="directory",
        ),
        param(
            ".git",
            (
                ".git",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            id="file",
        ),
    ],
)
def test_list_candidates__dot_git(
    tmp_path: Path,
    path: str,
    expect: Candidate,
) -> None:
    """`.git` is a candidate like any other name."""
    make_tree(tmp_path, path)

    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    assert candidates == [
        expect,
    ]


def test_list_candidates__empty(tmp_path: Path) -> None:
    """An empty directory has no candidates."""
    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    assert candidates == []


@needs_fifos
def test_list_candidates__fifo(tmp_path: Path) -> None:
    """A FIFO isn't a candidate."""
    make_fifo(tmp_path / "fifo")
    make_file(tmp_path / "file")

    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            "file",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect


@needs_symlinks
@mark.parametrize(
    ("make", "expect"),
    [
        param(
            make_broken_symlink,
            [],
            id="broken-symlink",
        ),
        param(
            make_symlink_loop,
            [],
            id="symlink-loop",
        ),
        param(
            make_symlink_to_directory,
            [
                (
                    "link.target",
                    True,  # Is a directory
                    False,  # Is a symlink
                )
            ],
            id="symlink-to-directory",
        ),
        param(
            make_symlink_to_file,
            [
                (
                    "link.target",
                    False,  # Is a directory
                    False,  # Is a symlink
                )
            ],
            id="symlink-to-file",
        ),
    ],
)
def test_list_candidates__ignore_symlinks(
    tmp_path: Path,
    make: Callable[[Path], None],
    expect: list[Candidate],
) -> None:
    """When symlinks are ignored, a symlink isn't a candidate, but its target is."""
    make(tmp_path / "link")

    candidates = list_candidates(
        os.fspath(tmp_path),
        ignore_symlinks=True,
    )

    assert candidates == expect


@needs_junctions
def test_list_candidates__ignore_symlinks_junction(tmp_path: Path) -> None:
    """When symlinks are ignored, a junction is still a candidate directory."""
    make_junction(tmp_path / "link")

    candidates = list_candidates(
        os.fspath(tmp_path),
        ignore_symlinks=True,
    )

    expect = [
        (
            "link.target",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "link",
            True,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect


def test_list_candidates__order(tmp_path: Path) -> None:
    """A directory's candidates are sorted into walk order."""
    # Created in neither the expected order nor its reverse.
    make_tree(
        tmp_path,
        "b.txt",
        "Z",
        "ba",
        "b/",
        ".a",
        "b_c",
        "b-c",
    )

    # Uppercase before lowercase, then the byte after "b" decides the ties, with the
    # directory "b" sorting as "b/".
    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            ".a",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "Z",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b-c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b.txt",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b_c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "ba",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect


@needs_junctions
def test_list_candidates__junction(tmp_path: Path) -> None:
    """A junction is a candidate directory."""
    make_junction(tmp_path / "link")

    # The junction's target, "link.target", is a real directory -- and both are
    # considered directories, so they sort as "link/" and "link.target/".
    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            "link.target",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "link",
            True,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect


def test_list_candidates__not_a_directory(tmp_path: Path) -> None:
    """`NotADirectoryError` is raised when the directory is a file."""
    file = tmp_path / "file"
    make_file(file)
    directory = os.fspath(file)

    with raises(NotADirectoryError) as raised:
        list_candidates(
            directory,
        )

    assert raised.value.errno == errno.ENOTDIR
    assert raised.value.filename == directory


@needs_posix_permissions
def test_list_candidates__read_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny reading the directory."""
    path = tmp_path / "directory"
    path.mkdir()
    directory = os.fspath(path)

    # Write and search ("execute") but not read, so the directory can't be listed.
    path.chmod(0o300)

    try:
        with raises(PermissionError) as raised:
            list_candidates(
                directory,
            )

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == directory
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)


@needs_posix_permissions
def test_list_candidates__search_is_denied(tmp_path: Path) -> None:
    """Each candidate's type comes from the listing, not from looking it up."""
    path = tmp_path / "directory"
    make_tree(path, "file", "subdirectory/")
    directory = os.fspath(path)

    # Read and write but not search ("execute"), so the directory's names can be
    # listed but nothing inside it can be looked up.
    path.chmod(0o600)

    try:
        # Prove the setup worked: `lstat` can't look up anything inside the directory.
        with raises(PermissionError):
            os.lstat(path / "file")

        # So each type must come from the listing itself. If `list_candidates` looked up
        # each candidate separately instead, every lookup would fail here -- and every
        # walk would be several times slower.
        candidates = list_candidates(
            directory,
        )

        expect = [
            (
                "file",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            (
                "subdirectory",
                True,  # Is a directory
                False,  # Is a symlink
            ),
        ]

        assert candidates == expect

    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)


@needs_symlinks
def test_list_candidates__symlink_to_directory(tmp_path: Path) -> None:
    """A symlink to a directory is a candidate file, not a directory."""
    make_symlink_to_directory(tmp_path / "link")

    # The symlink's target, "link.target", is a real directory.
    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            "link",
            False,  # Is a directory
            True,  # Is a symlink
        ),
        (
            "link.target",
            True,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect


@needs_symlinks
def test_list_candidates__symlink_to_file(tmp_path: Path) -> None:
    """A symlink to a file is a candidate file."""
    make_symlink_to_file(tmp_path / "link")

    # The symlink's target, "link.target", is a real file.
    candidates = list_candidates(
        os.fspath(tmp_path),
    )

    expect = [
        (
            "link",
            False,  # Is a directory
            True,  # Is a symlink
        ),
        (
            "link.target",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert candidates == expect
