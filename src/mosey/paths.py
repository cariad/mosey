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
    """Returns the key that sorts a candidate into Git's walk order.

    Git lists files in the order of their full paths, compared byte by byte from the
    left. We sort one directory at a time, so each directory's entries need to sort in
    the same order as the paths beneath them would in Git.

    Sorting by name alone doesn't do that. Take this directory:

    ```
    root/
    ├── b/
    │   └── x
    └── b.txt
    ```

    Git doesn't list directories, only the full paths of the files inside them, so it
    sees two paths:

    ```
    b/x
    b.txt
    ```

    Both start with "b", so the second character decides the order. "." is byte 0x2e and
    "/" is byte 0x2f, so Git lists "b.txt" first:

    ```
    b.txt
    b/x
     ^
    ```

    We don't see paths, though. We walk one directory at a time, and the root directory
    has two entries: the directory "b" and the file "b.txt". Sorted by name, "b" comes
    first because it's shorter:

    ```
    b
    b.txt
    ```

    That's the opposite of Git. We'd walk into "b" and yield "b/x" before "b.txt".

    Appending "/" to the directory's name makes our entries look like Git's paths, so
    the second character decides again and "b.txt" comes first:

    ```
    b.txt
    b/
     ^
    ```

    The key is an array of bytes rather than a string because Git sees the raw bytes of
    a filename, and Python's string comparison doesn't always agree with them.

    Performance considerations:

    - This is called once per object, so it's on the hot path and intentionally doesn't
      validate.
    - The name is encoded "manually" via `str.encode` rather than `os.fsencode` because
      it's about twice as fast in Python 3.11 to 3.14 on arm64 macOS.
    - The candidate is a single argument, rather than separate name and directory flags,
      so the function can be passed directly to `list.sort` without needing a lambda in
      the middle.

    Args:
        candidate: Candidate.

    Returns:
        Sort key as an array of bytes.
    """
    key = candidate[0].encode(FS_ENCODING, FS_ERRORS)
    return key + b"/" if candidate[1] else key
