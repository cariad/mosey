"""Pytest configuration for Mosey's tests."""

import sys

from pytest import UsageError


def pytest_configure() -> None:
    """Stop before any test runs if the file system encoding isn't UTF-8.

    Raises:
        UsageError: When the file system encoding isn't UTF-8.
    """
    encoding = sys.getfilesystemencoding()

    if encoding == "utf-8":
        return

    raise UsageError(
        f"Mosey's tests need a UTF-8 file system encoding, not {encoding!r}. Run them "
        "with PYTHONUTF8=1."
    )
