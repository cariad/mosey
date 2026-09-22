"""Functions for working with paths.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import sys
from typing import Final

FS_ENCODING: Final[str] = sys.getfilesystemencoding()
"""The encoding that converts filenames between strings and bytes."""

FS_ERRORS: Final[str] = sys.getfilesystemencodeerrors()
"""The error handler that converts filenames between strings and bytes."""


def sort_key(filename: str, is_dir: bool) -> bytes:
    """Returns a filename as an array of bytes that sort into Git's walk order.

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

    A name that isn't valid in the filesystem encoding reaches Python with its bad bytes
    escaped as surrogate code points, which compare higher than most real characters
    even when the bytes themselves compare lower. Encoding the name puts the raw bytes
    back.

    This is called once per object, so it's on the hot path and intentionally doesn't
    validate `filename`.

    It's also why the name is encoded by hand rather than with `os.fsencode`, which
    does exactly this but also accepts path-like objects and looks up the encoding and
    error handler on every call. On Python 3.11 to 3.14 on arm64 macOS, `str.encode`
    with the cached `FS_ENCODING` and `FS_ERRORS` is about twice as fast.

    That saving is smaller than the cost of an extra Python call per entry, so the
    walker shouldn't adapt this to `sorted` with a lambda. Instead, inline the body
    into a key function shaped for whatever the walker carries per entry.

    Args:
        filename: The entry's filename. Just the name, not the path.
        is_dir: Whether the entry is a directory, and so has paths beneath it. Pass
            `False` for a symlink to a directory unless the walk will descend it;
            Git stores symlinks as files, so it sorts them by name alone.

    Returns:
        Sort key as an array of bytes.
    """
    key = filename.encode(FS_ENCODING, FS_ERRORS)
    return key + b"/" if is_dir else key
