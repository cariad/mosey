"""Unit tests for the `exceptions` module."""

import errno

from pytest import raises

from mosey.exceptions import raise_file_not_found


def test_raise_file_not_found() -> None:
    """`FileNotFoundError` is raised."""
    with raises(FileNotFoundError) as raised:
        raise_file_not_found("foo")

    assert raised.value.errno == errno.ENOENT
    assert raised.value.filename == "foo"
    assert raised.value.__cause__ is None


def test_raise_file_not_found__cause() -> None:
    """`FileNotFoundError` is raised with the given cause."""
    cause = OSError()

    with raises(FileNotFoundError) as raised:
        raise_file_not_found("foo", cause)

    assert raised.value.__cause__ is cause
