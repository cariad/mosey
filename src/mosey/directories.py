"""Functions for working with directories.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import os

from .candidate import Candidate
from .paths import sort_key


def list_candidates(directory: str) -> list[Candidate]:
    """Return a directory's candidates in walk order.

    Only directories, files, and symlinks are candidates; anything else is excluded. Any
    object whose type can't be determined is also excluded.

    The walk order is documented at https://cariad.github.io/mosey/walk-order/.

    Args:
        directory: Path to the directory to list.

    Returns:
        The directory's candidates in walk order.

    Raises:
        OSError: When the directory can't be listed.
    """
    candidates: list[Candidate] = []

    # We read the whole listing and close the directory before returning.
    #
    # Sorting needs the whole listing anyway, and it means the walk never holds a
    # directory open longer than it absolutely needs to. A walk that's abandoned or
    # fails leaves nothing open.
    with os.scandir(directory) as entries:
        # What counts as a candidate? https://cariad.github.io/mosey/walk-order/
        for entry in entries:
            try:
                # Files are the most common type. Check for them first, then most
                # entries will need only one check.
                if entry.is_file(follow_symlinks=False):
                    is_dir = False
                elif entry.is_dir(follow_symlinks=False):
                    is_dir = True
                elif entry.is_symlink():
                    is_dir = False
                else:
                    continue
            except OSError:  # pragma: no cover
                # Every file system in our CI matrix records types, so we can't reach
                # this for real in our current tests. Maybe one day!
                #
                # For now we just exclude the object. We *could* raise or collect the
                # error instead, but we'll think about that another day.
                continue

            candidates.append((entry.name, is_dir))

    candidates.sort(key=sort_key)
    return candidates
