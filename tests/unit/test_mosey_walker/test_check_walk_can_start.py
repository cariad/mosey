"""Unit tests for the `MoseyWalker.check_walk_can_start` function.

What it raises is tested alongside `walk`, in `test_walk` and `test_walk_start`, because
it runs exactly the same checks.
"""

import os
from pathlib import Path

from pytest import MonkeyPatch, mark, raises

from tests.file_system_helpers import (
    build_walker,
    make_junction,
    make_symlink_to_directory,
    make_tree,
    write_ignore_files,
)
from tests.markers import needs_junctions, needs_posix_permissions, needs_symlinks


@needs_posix_permissions
def test_check_walk_can_start__lists_nothing_within_start(tmp_path: Path) -> None:
    """Nothing within the start is listed, so a walk that can start can still fail."""
    make_tree(tmp_path, "a/b/c/d.txt", "a/b/e.txt")
    walker = build_walker("ignore")

    # Write and search ("execute") but not read, so listing it would fail.
    (tmp_path / "a" / "b" / "c").chmod(0o300)

    try:
        walker.check_walk_can_start(tmp_path, start="a/b")

        # The walk starts too, but fails when it reaches the directory it can't list.
        steps = walker.walk(tmp_path, start="a/b")

        with raises(PermissionError) as raised:
            list(steps)
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "a" / "b" / "c").chmod(0o700)

    assert raised.value.filename == os.fspath(tmp_path / "a" / "b" / "c")


@mark.parametrize("start", [".", "a/b", "./a//b/", Path("a", "b")])
def test_check_walk_can_start__passes(
    tmp_path: Path,
    start: os.PathLike[str] | str,
) -> None:
    """Nothing is raised when a walk can start."""
    make_tree(tmp_path, "a/b/c.txt")

    build_walker("ignore").check_walk_can_start(tmp_path, start=start)


@needs_posix_permissions
def test_check_walk_can_start__reads_no_ignore_files(tmp_path: Path) -> None:
    """No ignore-file is read, so one that can't be read doesn't fail the check."""
    write_ignore_files(tmp_path, {"": ["*.log"]})
    make_tree(tmp_path, "a/b.txt")
    walker = build_walker("ignore")

    # Write but not read.
    (tmp_path / "ignore").chmod(0o200)

    try:
        walker.check_walk_can_start(tmp_path)
        walker.check_walk_can_start(tmp_path, start="a")

        with raises(PermissionError):
            list(walker.walk(tmp_path))
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        (tmp_path / "ignore").chmod(0o600)


def test_check_walk_can_start__relative_root(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """A relative root is found from the working directory."""
    make_tree(tmp_path, "root/a/b.txt")
    monkeypatch.chdir(tmp_path)

    build_walker().check_walk_can_start("root", start="a")


@needs_symlinks
def test_check_walk_can_start__root_is_symlink(tmp_path: Path) -> None:
    """A root that's a symlink to a directory can start, as it's walked."""
    make_symlink_to_directory(tmp_path / "root")
    make_tree(tmp_path / "root", "a/")
    walker = build_walker("ignore")

    walker.check_walk_can_start(tmp_path / "root")
    walker.check_walk_can_start(tmp_path / "root", start="a")


def test_check_walk_can_start__start_ignored(tmp_path: Path) -> None:
    """An ignored start passes the check, but the walk yields nothing."""
    write_ignore_files(tmp_path, {"": ["a/"]})
    make_tree(tmp_path, "a/b/c.txt")
    walker = build_walker("ignore")

    walker.check_walk_can_start(tmp_path, start="a/b")
    assert list(walker.walk(tmp_path, start="a/b")) == []


@needs_junctions
def test_check_walk_can_start__through_a_junction(tmp_path: Path) -> None:
    """A junction is a directory, so the check passes in or through one."""
    make_tree(tmp_path, "a/")
    make_junction(tmp_path / "a" / "b")
    make_tree(tmp_path / "a" / "b", "c/")
    walker = build_walker()

    walker.check_walk_can_start(
        tmp_path,
        start="a/b",
    )

    walker.check_walk_can_start(
        tmp_path,
        start="a/b/c",
    )
