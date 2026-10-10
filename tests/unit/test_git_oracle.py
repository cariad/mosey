"""Unit tests for the Git comparison helpers."""

from pathlib import Path

from pytest import MonkeyPatch, mark, param, raises

from tests.file_system_helpers import (
    make_tree,
    skip_if_windows_cannot_create,
    skip_if_windows_git_warns,
)
from tests.git_oracle import git_list_files, has_git
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

    # The ignore-file is listed unless a line ignores it, so these check its lines too.
    assert git_list_files(tmp_path, "ignore", ignore_ignore_files=False) == expect


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
@mark.parametrize(
    ("ignore_ignore_files", "expect"),
    [
        param(
            True,
            ["a", "dir/ignore/c", "sub/b"],
            id="left-out",
        ),
        param(
            False,
            ["a", "dir/ignore/c", "ignore", "sub/b", "sub/ignore"],
            id="listed",
        ),
    ],
)
def test_git_list_files__ignore_files(
    tmp_path: Path,
    ignore_ignore_files: bool,
    expect: list[str],
) -> None:
    """Git leaves out the ignore-files if asked, but not a directory named like them."""
    make_tree(tmp_path, "a", "ignore", "dir/ignore/c", "sub/b", "sub/ignore")
    skip_if_windows_git_warns(tmp_path, "ignore")

    assert git_list_files(tmp_path, "ignore", (), ignore_ignore_files) == expect


@needs_git
def test_git_list_files__no_ignore_filename(tmp_path: Path) -> None:
    """Without an ignore-file name, Git reads no ignore-file, not even its own."""
    make_tree(tmp_path, "a.txt")
    (tmp_path / ".gitignore").write_bytes(b"*.txt\n")
    (tmp_path / "ignore").write_bytes(b"*.txt\n")

    assert git_list_files(tmp_path, None) == [".gitignore", "a.txt", "ignore"]


@needs_git
@mark.parametrize(
    "weight",
    [
        param(1, id="exclude"),
        param(0, id="exclude-from"),
    ],
)
@mark.parametrize(
    ("pattern", "tree", "expect"),
    [
        param('a"b', ['a"b', "ab"], ["ab"], id="double-quote"),
        # Windows can't create a name holding '"', so this checks the quote there too.
        # Without the quote, "a[!]b" would never match, since nothing closes its "[".
        param('a[!"]b', ["ab", "axb"], ["ab"], id="double-quote-in-brackets"),
        param("a'b", ["a'b", "ab"], ["ab"], id="single-quote"),
        param("%PATH%", ["%PATH%", "PATH"], ["PATH"], id="percent"),
        param("a^b", ["a^b", "ab"], ["ab"], id="caret"),
        param("a&b", ["a&b", "ab"], ["ab"], id="ampersand"),
        param("a*", ["ab", "b"], ["b"], id="star"),
        param("a?c", ["abc", "ac"], ["ac"], id="question-mark"),
        # Without the backslash, nothing would close the "[", and it would never match.
        param("a\\[b", ["a[b", "ab"], ["ab"], id="escaped-bracket"),
        param(" a", [" a", "a"], ["a"], id="leading-space"),
        param("a\t", ["a\t", "a"], ["a"], id="trailing-tab"),
        param("a\\ ", ["a ", "a"], ["a"], id="escaped-trailing-space"),
        param("café", ["cafe", "café"], ["cafe"], id="non-ascii"),
    ],
)
def test_git_list_files__pattern(
    tmp_path: Path,
    pattern: str,
    tree: list[str],
    expect: list[str],
    weight: int,
) -> None:
    """Git is given each pattern exactly, as an argument or in a file of patterns."""
    # Patterns weighing 1 or more are passed to Git as arguments, so on Windows, these
    # check that Python's quoting of a command line reaches Git intact.
    skip_if_windows_cannot_create(tree)
    make_tree(tmp_path, *tree)

    assert git_list_files(tmp_path, None, [(pattern, weight)]) == expect


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


@needs_git
def test_has_git() -> None:
    """Git doesn't count when it's older than the version asked for."""
    assert not has_git((1000, 0))
