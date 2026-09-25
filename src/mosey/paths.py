"""Functions for working with paths.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import sys
from typing import Final

from .candidate import Candidate

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
