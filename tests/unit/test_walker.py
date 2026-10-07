"""Unit tests for the `Walker` protocol."""

from pytest import raises

from mosey import Walker


def test_walker__cannot_be_created() -> None:
    """`TypeError` is raised when a `Walker` is created directly."""
    with raises(TypeError):
        Walker()  # pyright: ignore[reportAbstractUsage]
