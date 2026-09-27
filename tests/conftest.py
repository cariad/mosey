"""Pytest configuration for Mosey's tests."""

import sys

from pytest import UsageError

from tests.git_oracle import git_version


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


def pytest_report_header() -> str:
    """Show which Git the comparisons with Git use, so every CI job's log records it.

    Returns:
        What `git --version` prints, or a note that Git isn't installed.
    """
    return git_version() or "git: not installed"
