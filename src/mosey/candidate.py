"""The `Candidate` type, which describes a directory entry before a walk acts on it.

This is an internal type for the `mosey` package. It isn't explicitly exported by the
package, and its shape can change without notice.
"""

from typing import TypeAlias

# NOTE: `Candidate` is a plain tuple rather than a named tuple because one is built per
# NOTE: entry, and a tuple literal (built in C) is far cheaper than a named tuple (a
# NOTE: Python call): about 17 nanoseconds against 160 on Python 3.14 on arm64 macOS.
# NOTE:
# NOTE: The third element tells a symlink apart. On Python 3.11 to 3.14 on arm64 macOS,
# NOTE: carrying it through to each step, passed by position, made walks of 24,000
# NOTE: files in a virtual environment's site-packages, and of a generated tree of
# NOTE: 20,000 files and 1,000 symlinks, take 0.2-1.2% longer, or 0.4-1.7% with an
# NOTE: ignore-file name, which also looks for a symlinked ignore-file. Passing it by
# NOTE: name, as `MoseyStep` takes it, made walks another 2.3% longer on 3.11 and
# NOTE: 4.7-5.2% on 3.14. Neither `None` for a symlink in the second element, nor a
# NOTE: second step class that says it's a symlink, was faster: all three shapes were
# NOTE: within 0.8% of each other.
Candidate: TypeAlias = tuple[str, bool, bool]
"""A directory entry that a walk hasn't acted on yet.

The elements are:

1. The filename: just the name, not the path.
2. Whether the candidate is a directory: `True` for a directory (including a Windows
   junction), `False` for a file or any symlink (even a symlink to a directory).
3. Whether the candidate is a symlink: `True` for any symlink, whatever it points to,
   and `False` for a file or a directory (including a Windows junction).
"""
