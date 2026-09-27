"""Unit tests for the Git comparison helpers."""

from pathlib import Path

from pytest import MonkeyPatch, mark, param, raises

from tests.file_system_helpers import make_tree
from tests.git_oracle import git_list_files
from tests.markers import needs_git, needs_posix_permissions


@needs_git
@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"*.txt\n",
            ["ignore"],
            id="matches",
        ),
        # `git init` turns on case-insensitive matching when the file system ignores
        # case, like macOS's does by default, so this checks that it's turned off.
        param(
            b"*.TXT\n",
            ["a.txt", "ignore"],
            id="case-sensitive",
        ),
    ],
)
def test_git_list_files(tmp_path: Path, data: bytes, expect: list[str]) -> None:
    """Git leaves out the files that the ignore-file ignores, matching case exactly."""
    make_tree(tmp_path, "a.txt")
    (tmp_path / "ignore").write_bytes(data)

    assert git_list_files(tmp_path, "ignore") == expect


@needs_git
def test_git_list_files__decomposed(tmp_path: Path) -> None:
    """A name comes back exactly as the file system reports it."""
    # "e" then the combining accent U+0301. `git init` turns on composing them into the
    # single character U+00E9 on macOS, so this checks that it's turned off.
    name = "cafe\u0301"
    make_tree(tmp_path, name)

    assert git_list_files(tmp_path, "ignore") == [name]


@needs_git
def test_git_list_files__environment(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Git's environment variables are left out, so they change nothing."""
    # `GIT_TRACE` makes Git print what it's doing to stderr, which would count as an
    # error if it got through.
    monkeypatch.setenv("GIT_TRACE", "1")
    make_tree(tmp_path, "a.txt")

    assert git_list_files(tmp_path, "ignore") == ["a.txt"]


@mark.parametrize(
    "path",
    [
        param(
            ".git",
            id="file",
        ),
        param(
            "sub/.GIT/",
            id="nested-directory-in-another-casing",
        ),
    ],
)
def test_git_list_files__git(tmp_path: Path, path: str) -> None:
    """`ValueError` is raised when anything is named ".git", in any casing."""
    make_tree(tmp_path, path)

    with raises(ValueError):
        git_list_files(tmp_path, "ignore")


@needs_git
@needs_posix_permissions
def test_git_list_files__read_is_denied(tmp_path: Path) -> None:
    """An error is raised when Git can't read the ignore-file."""
    file = tmp_path / "ignore"
    file.write_bytes(b"*\n")

    # Write but not read. Git warns, then carries on as if the file weren't there, and
    # still exits with 0.
    file.chmod(0o200)

    try:
        # Git's warning names the file, whatever language it's in. Any other failure
        # wouldn't.
        with raises(RuntimeError, match="ignore"):
            git_list_files(tmp_path, "ignore")
    finally:
        # Leave the file readable, as we found it.
        file.chmod(0o600)
