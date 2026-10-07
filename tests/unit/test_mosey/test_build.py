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
    builder.set_ignore_filename("b")

    # The walker still reads "a", so "y" is yielded and "x" isn't.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["a", "b", "y"]
