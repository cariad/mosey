"""Unit tests for the `MoseyStep` class."""

from pathlib import Path

from pytest import fixture

from mosey.mosey_step import MoseyStep


@fixture
def step() -> MoseyStep:
    """Return a `MoseyStep` with known values for testing."""
    return MoseyStep(
        "foo.txt",
        "documents/foo.txt",
        Path("stuff"),
    )


def test_name(step: MoseyStep) -> None:
    """The name is assigned during initialisation."""
    assert step.name == "foo.txt"


def test_path(step: MoseyStep) -> None:
    """The path is constructed from the root and relative path."""
    assert step.path == Path("stuff") / "documents" / "foo.txt"


def test_path__cached(step: MoseyStep) -> None:
    """The path is cached."""
    assert step.path is step.path


def test_path__lazy(step: MoseyStep) -> None:
    """The path isn't constructed during initialisation."""
    # I don't love that the test leans on hidden implementation, but it's an open-eyed
    # compromise over complexity.
    assert step._path is None  # pyright: ignore[reportPrivateUsage]


def test_repr(step: MoseyStep) -> None:
    """The canonical string representation is meaningful."""
    assert repr(step) == "<Step 'documents/foo.txt'>"


def test_relative_as_posix(step: MoseyStep) -> None:
    """The relative path is assigned during initialisation."""
    assert step.relative_as_posix == "documents/foo.txt"


def test_root(step: MoseyStep) -> None:
    """The root is assigned during initialisation."""
    assert step.root == Path("stuff")
