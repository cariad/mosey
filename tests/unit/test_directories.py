"""Unit tests for the `directories` module."""

import errno
import os
from pathlib import Path

from pytest import mark, param, raises

from mosey.candidate import Candidate
from mosey.directories import list_candidates
from tests.file_system_helpers import (
    make_broken_symlink,
    make_fifo,
    make_file,
    make_junction,
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
    """A broken symlink is a candidate file, because Git lists it like any symlink."""
    make_broken_symlink(tmp_path / "link")

    assert list_candidates(os.fspath(tmp_path)) == [("link", False)]


def test_list_candidates__does_not_exist(tmp_path: Path) -> None:
    """`FileNotFoundError` is raised when the directory doesn't exist."""
    directory = os.fspath(tmp_path / "nope")

    with raises(FileNotFoundError) as raised:
        list_candidates(directory)

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == directory


@mark.parametrize(
    ("path", "expect"),
    [
        param(
            ".git/",
            (".git", True),
            id="directory",
        ),
        # Worktrees and submodules have a ".git" file rather than a directory.
        param(
            ".git",
            (".git", False),
            id="file",
        ),
        # Git skips this too when `core.ignorecase` is set.
        param(
            ".GIT/",
            (".GIT", True),
            id="uppercase",
        ),
    ],
)
def test_list_candidates__dot_git(
    tmp_path: Path,
    path: str,
    expect: Candidate,
) -> None:
    """`.git` is a candidate like any other name, even though Git skips it."""
    make_tree(tmp_path, path)

    assert list_candidates(os.fspath(tmp_path)) == [expect]


def test_list_candidates__empty(tmp_path: Path) -> None:
    """An empty directory has no candidates."""
    assert list_candidates(os.fspath(tmp_path)) == []


@needs_fifos
def test_list_candidates__fifo(tmp_path: Path) -> None:
    """A FIFO isn't a candidate, because Git skips it."""
    make_fifo(tmp_path / "fifo")
    make_file(tmp_path / "file")

    assert list_candidates(os.fspath(tmp_path)) == [("file", False)]


def test_list_candidates__git_order(tmp_path: Path) -> None:
    """A directory's candidates are sorted into the order that Git lists them."""
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

    # Uppercase sorts before lowercase, so "Z" comes before "b".
    #
    # Then "-" (0x2d), "." (0x2e), "/" (0x2f), "_" (0x5f) and "a" (0x61) decide the ties
    # on "b", with the directory "b" sorting as "b/".
    assert list_candidates(os.fspath(tmp_path)) == [
        (".a", False),
        ("Z", False),
        ("b-c", False),
        ("b.txt", False),
        ("b", True),
        ("b_c", False),
        ("ba", False),
    ]


@needs_junctions
def test_list_candidates__junction(tmp_path: Path) -> None:
    """A junction is a candidate directory, because Git walks into it."""
    make_junction(tmp_path / "link")

    # The junction's target, "link.target", is a real directory -- and both are
    # considered directories, so they sort as "link/" and "link.target/".
    assert list_candidates(os.fspath(tmp_path)) == [
        ("link.target", True),
        ("link", True),
    ]


def test_list_candidates__not_a_directory(tmp_path: Path) -> None:
    """`NotADirectoryError` is raised when the directory is a file."""
    file = tmp_path / "file"
    make_file(file)
    directory = os.fspath(file)

    with raises(NotADirectoryError) as raised:
        list_candidates(directory)

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
            list_candidates(directory)

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == directory
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)


@needs_posix_permissions
def test_list_candidates__search_is_denied(tmp_path: Path) -> None:
    """Candidates keep their types when permissions deny searching the directory."""
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

        # So each type must come from the listing itself. If `list_candidates` called
        # `lstat` instead, every call would fail and every candidate would be skipped.
        #
        # This relies on the file system recording each object's type in the listing,
        # which every file system in our CI matrix does.
        assert list_candidates(directory) == [
            ("file", False),
            ("subdirectory", True),
        ]
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)


@needs_symlinks
def test_list_candidates__symlink_to_directory(tmp_path: Path) -> None:
    """A symlink to a directory is a candidate file, not a directory."""
    make_symlink_to_directory(tmp_path / "link")

    # The symlink's target, "link.target", is a real directory.
    assert list_candidates(os.fspath(tmp_path)) == [
        ("link", False),
        ("link.target", True),
    ]


@needs_symlinks
def test_list_candidates__symlink_to_file(tmp_path: Path) -> None:
    """A symlink to a file is a candidate file."""
    make_symlink_to_file(tmp_path / "link")

    # The symlink's target, "link.target", is a real file.
    assert list_candidates(os.fspath(tmp_path)) == [
        ("link", False),
        ("link.target", False),
    ]
