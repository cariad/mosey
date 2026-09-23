"""The `Candidate` type, which describes a directory entry before a walk acts on it.

This is an internal type for the `mosey` package. It isn't explicitly exported by the
package, and its shape can change without notice.
"""

from typing import TypeAlias

Candidate: TypeAlias = tuple[str, bool]
"""A directory entry that a walk hasn't acted on yet.

A walk lists a directory's candidates and sorts them into Git's order before deciding
what to do with each one: yield it as a `Step`, descend it, or skip it.

The first element is the entry's filename: just the name, not the path.

The second indicates whether or not the entry is a directory. It's `False` for a symlink
to a directory unless the walk will descend it; Git stores symlinks as files, so it
sorts them by name alone.

It's a plain tuple rather than a named tuple because one is built per entry, and a
tuple literal is built in C while a named tuple costs a Python call. On Python 3.14 on
arm64 macOS, that's about 17 nanoseconds against 160.
"""
