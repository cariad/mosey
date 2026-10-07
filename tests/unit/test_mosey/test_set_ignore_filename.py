"""Unit tests for the `Mosey.set_ignore_filename` function."""

from pathlib import Path

from pytest import mark, param, raises

from mosey import Mosey
from tests.file_system_helpers import make_tree


@mark.parametrize(
    "name",
    [
        param(".moseyignore", id="leading-dot"),
        param("a.b", id="dot-inside"),
        # Only exactly "." and ".." are refused, never a name that starts with them.
        param("..a", id="leading-dots"),
        param("...", id="three-dots"),
        param("a b", id="space"),
        param("café", id="non-ascii"),
    ],
)
def test_set_ignore_filename(name: str) -> None:
    """Any name that isn't a path is accepted as the ignore-file name."""
    Mosey().set_ignore_filename(name)


@mark.parametrize(
    "name",
    [
        param("", id="empty"),
        param(".", id="dot"),
        param("..", id="dot-dot"),
        param("a/b", id="slash"),
        param("/a", id="leading-slash"),
        param("a/", id="trailing-slash"),
        # A backslash is refused on every operating system, not only on Windows.
        param("a\\b", id="backslash"),
        param("\\", id="lone-backslash"),
        param("a\x00b", id="null"),
    ],
)
def test_set_ignore_filename__not_a_filename(name: str) -> None:
    """`ValueError` is raised when the ignore-file name isn't a plain name."""
    # Raised by `Mosey` itself, before anything is built or walked.
    with raises(ValueError) as raised:
        Mosey().set_ignore_filename(name)

    assert str(raised.value) == f"{name!r} isn't a filename"


def test_set_ignore_filename__replaces(tmp_path: Path) -> None:
    """Setting the ignore-file name again replaces the name set before."""
    make_tree(tmp_path, "x", "y")
    (tmp_path / "a").write_bytes(b"x\n")
    (tmp_path / "b").write_bytes(b"y\n")

    builder = Mosey()
    builder.set_ignore_filename("a")
    builder.set_ignore_filename("b")
    walker = builder.build()

    # Only "b" is read, so "x" is yielded and "y" isn't.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["a", "b", "x"]
