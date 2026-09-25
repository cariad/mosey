"""The `Candidate` type, which describes a directory entry before a walk acts on it.

This is an internal type for the `mosey` package. It isn't explicitly exported by the
package, and its shape can change without notice.
"""

from typing import TypeAlias

# NOTE: `Candidate` is a plain tuple rather than a named tuple because one is built per
# NOTE: entry, and a tuple literal (built in C) is far cheaper than a named tuple (a
# NOTE: Python call): about 17 nanoseconds against 160 on Python 3.14 on arm64 macOS.
Candidate: TypeAlias = tuple[str, bool]
"""A directory entry that a walk hasn't acted on yet.

The elements are:

1. The filename: just the name, not the path.
2. Whether the candidate is a directory: `True` for a directory (including a Windows
   junction), `False` for a file or any symlink (even a symlink to a directory).
"""
