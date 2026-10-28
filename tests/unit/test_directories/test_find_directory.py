"""Unit tests for the `find_directory` function."""

import os
from pathlib import Path

from mosey.directories import find_directory, list_candidates
from tests.file_system_helpers import make_tree


def test_find_directory__no_such_directory(tmp_path: Path) -> None:
    """`None` is returned when nothing is spelled that way or is the directory."""
    make_tree(tmp_path, "a/", "b/", "c.txt", "d/")
    candidates = [c for c in list_candidates(os.fspath(tmp_path)) if c[0] != "b"]
    identity = os.lstat(tmp_path / "b")

    assert find_directory(os.fspath(tmp_path), candidates, "x", identity) is None


def test_find_directory__not_a_candidate(tmp_path: Path) -> None:
    """`None` is returned when no candidate is the directory."""
    make_tree(tmp_path, "a/", "b/", "c.txt", "d/")
    candidates = [c for c in list_candidates(os.fspath(tmp_path)) if c[0] != "b"]
    identity = os.lstat(tmp_path / "b")

    assert find_directory(os.fspath(tmp_path), candidates, "b", identity) is None


def test_find_directory__same_identity(tmp_path: Path) -> None:
    """A directory spelled differently is found by its identity."""
    make_tree(tmp_path, "a/", "b/", "c.txt")
    candidates = list_candidates(os.fspath(tmp_path))
    identity = os.lstat(tmp_path / "b")

    # "B" stands in for a spelling that the file system finds "b" by.
    assert find_directory(os.fspath(tmp_path), candidates, "B", identity) == "b"


def test_find_directory__same_name(tmp_path: Path) -> None:
    """A directory spelled the same is found by name."""
    make_tree(tmp_path, "a/", "b/", "c.txt")
    candidates = list_candidates(os.fspath(tmp_path))
    identity = os.lstat(tmp_path / "b")

    assert find_directory(os.fspath(tmp_path), candidates, "b", identity) == "b"
