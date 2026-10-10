"""Unit tests for the `Mosey.build` function."""

from pathlib import Path

from mosey import Mosey
from tests.file_system_helpers import make_tree


def test_build__later_changes(tmp_path: Path) -> None:
    """Changing a `Mosey` doesn't change the walkers it has already built."""
    make_tree(tmp_path, "x", "y")
    (tmp_path / "a").write_bytes(b"x\n")
    (tmp_path / "b").write_bytes(b"y\n")

    builder = Mosey()
    builder.set_ignore_filename("a")
    walker = builder.build()
    builder.set_ignore_filename("b", ignore=False)

    # The walker still reads and leaves out "a", so "y" is yielded and "x" isn't.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["b", "y"]


def test_build__later_patterns(tmp_path: Path) -> None:
    """Adding a pattern to a `Mosey` doesn't change the walkers it has already built."""
    make_tree(tmp_path, "x", "y", "z")

    builder = Mosey()
    builder.add_pattern("x")
    walker = builder.build()
    builder.add_pattern("y")
    builder.add_pattern("z", weight=1)

    # The walker still has only "x", so "y" and "z" are yielded.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["y", "z"]


def test_build__several_builds(tmp_path: Path) -> None:
    """Building leaves the patterns in the `Mosey`, so every later build has them."""
    make_tree(tmp_path, "a.log", "b.tmp", "c")

    builder = Mosey()
    builder.add_pattern("*.log")
    builder.build()
    builder.add_pattern("*.tmp", weight=1)
    walker = builder.build()

    # "*.log" was added before the first build, and the second build still has it.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["c"]
