"""Unit tests for the `Step` protocol."""

from pytest import raises

from mosey import Step


def test_step__cannot_be_created() -> None:
    """`TypeError` is raised when a `Step` is created directly."""
    with raises(TypeError):
        Step()  # pyright: ignore[reportAbstractUsage]
