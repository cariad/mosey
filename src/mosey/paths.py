"""Functions for working with paths.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import os
import sys
from pathlib import Path
from typing import Final

from .candidate import Candidate
from .exceptions import raise_file_not_found

FS_ENCODING: Final[str] = sys.getfilesystemencoding()
"""The encoding that converts filenames between strings and bytes."""

FS_ERRORS: Final[str] = sys.getfilesystemencodeerrors()
"""The error handler that converts filenames between strings and bytes."""


def sort_key(candidate: Candidate) -> bytes:
    """Return the key that sorts a candidate into walk order.

    The walk order is documented at https://cariad.github.io/mosey/walk-order/.

    Args:
        candidate: The candidate to sort.

    Returns:
        The candidate's sort key.
    """
    # The key is the filename as bytes, with "/" appended if the candidate is a
    # directory. A walk sorts one directory at a time, and that trailing "/" is what
    # makes the paths it yields come out in ascending byte order overall.
    #
    # The key is bytes rather than a string because the documented order is byte order,
    # and strings compare by code point instead. The two agree for valid UTF-8, but not
    # necessarily for names that aren't valid Unicode or under a file system encoding
    # other than UTF-8.
    #
    # NOTE: This is called once per object, so it's on the hot path and intentionally
    # NOTE: doesn't validate.
    #
    # NOTE: The name is encoded "manually" via `str.encode` rather than `os.fsencode`
    # NOTE: because it's about twice as fast in Python 3.11 to 3.14 on arm64 macOS.
    #
    # NOTE: The candidate is a single argument, rather than separate name and directory
    # NOTE: flags, so that the function can be passed directly to `list.sort` without
    # NOTE: needing a lambda in the middle.
    key = candidate[0].encode(FS_ENCODING, FS_ERRORS)
    return key + b"/" if candidate[1] else key


def split_start(start: os.PathLike[str] | str) -> tuple[str, ...]:
    """Split the path to a walk's starting directory into its names.

    Like the walk's root, the path is tidied up by `pathlib`, so "a//b/" and "./a/b" are
    both "a/b", and so is "a" and "b" separated by a backslash on Windows.

    Args:
        start: Path to the starting directory, relative to the walk's root, or "." for
            the root itself.

    Returns:
        The names of the directories to walk through to reach the starting directory,
        outermost first.

        For example, `("a", "b")` for "a/b".

        Returns an empty tuple for "." — the root itself.

    Raises:
        FileNotFoundError: When `start` is empty.
        ValueError: When `start` is absolute, has a drive, holds "..", or contains a
            null character.
    """
    # As with the root, `Path` would turn an empty string into ".", which feels a bit
    # unexpected, so an explicit "." is asked for instead.
    text = os.fspath(start)

    if not text:
        raise_file_not_found("")

    # The operating system refuses a null character in the root, and no name it lists
    # can hold one, so it's refused here too, rather than reported as missing.
    if "\x00" in text:
        raise ValueError(f"{text!r} contains a null character")

    path = Path(start)

    # The directory to start in is beneath the root, so nothing can take it elsewhere.
    if path.anchor or ".." in path.parts:
        raise ValueError(f"{text!r} isn't a path beneath the root")

    return path.parts
