"""Functions for working with directories.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import os

from .candidate import Candidate
from .ignore_files import read_ignore_file, split_ignore_file
from .paths import sort_key
from .rules import Layers, compile_rules, is_ignored


def list_candidates(directory: str) -> list[Candidate]:
    """Return a directory's candidates in walk order.

    Only directories, files, and symlinks are candidates; anything else is excluded.

    The walk order is documented at https://cariad.github.io/mosey/walk-order/.

    Args:
        directory: Path to the directory to list.

    Returns:
        The directory's candidates in walk order.

    Raises:
        OSError: When the directory can't be listed, or the type of an object within it
            can't be looked up.
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
            # Files are the most common type. Check for them first, then most entries
            # will need only one check.
            #
            # Most file systems record each object's type in the listing. On a file
            # system that doesn't, the first check will look it up. If that fails, then
            # we intentionally let the exception rise rather than catch and skip the
            # entry.
            if entry.is_file(follow_symlinks=False):
                is_dir = False
            elif entry.is_dir(follow_symlinks=False):
                is_dir = True
            elif entry.is_symlink():
                is_dir = False
            else:
                continue

            candidates.append((entry.name, is_dir))

    candidates.sort(key=sort_key)
    return candidates


def read_directory(
    directory: str,
    prefix: str,
    heavy_layers: Layers,
    layers: Layers,
    ignore_filename: str | None,
) -> tuple[list[Candidate], Layers]:
    """Return a directory's candidates that aren't ignored, in walk order.

    With an ignore-file name, the directory's ignore-file is the candidate with exactly
    that name, unless it's a directory. A symlink with that name is read through the
    link. The file's rules go in front of the layers from the directories above, and
    each candidate is then judged against them all, the ignore-file included. So a
    directory's own ignore-file judges everything inside it, but never the directory
    itself, which only the ignore-files above it and the patterns given in code can
    judge.

    The heavy layers judge each candidate before any of the others, so they overrule
    every ignore-file.

    Args:
        directory: Path to the directory to read.
        prefix: The directory's path relative to the walk's root, with a "/" after each
            name: "" for the root, or "a/b/" for "root/a/b".
        heavy_layers: The layers for the patterns given in code that overrule every
            ignore-file.
        layers: The layers from the ignore-files in every directory above this one,
            deepest first, then the layers for the patterns given in code that every
            ignore-file overrules.
        ignore_filename: The ignore-file's name, or `None` to read none.

    Returns:
        The candidates that aren't ignored, in walk order, and the layers for the
        directory's subdirectories: this directory's own, if its ignore-file has any
        rules, then `layers`. The heavy layers are never among them.

    Raises:
        OSError: When the directory can't be listed, the type of an object within it
            can't be looked up, or the ignore-file can't be read.
    """
    candidates = list_candidates(directory)

    # We look for the ignore-file in the listing rather than trying to open it, so a
    # directory without one costs no extra system call. It also means the name has to
    # match exactly: a file named "IGNORE" is never read as "ignore", even on a file
    # system that would open it.
    #
    # NOTE: The listing is sorted, so a binary search with `bisect` could find the
    # NOTE: ignore-file too, but most directories are too small for that to pay off.
    # NOTE: Scanning costs about 7-11 nanoseconds per candidate, and a search about
    # NOTE: 280-450 with 10 candidates, so a search only wins above about 50-100. Walks
    # NOTE: of two trees of mostly small directories, with the name set but absent, took
    # NOTE: 0.4-1.9% longer with a search on Python 3.11 to 3.14 on arm64 macOS.
    if ignore_filename is not None and (ignore_filename, False) in candidates:
        path = os.path.join(directory, ignore_filename)
        rules = compile_rules(split_ignore_file(read_ignore_file(path)))

        # The deepest ignore-file decides first, so this directory's rules go in front.
        if rules is not None:
            layers = ((prefix, *rules), *layers)

    # The heavy layers go in front of every ignore-file's, but only for judging. They're
    # never returned with the other layers, so a subdirectory's ignore-file still goes
    # in front of the layers from the directories above, and behind the heavy layers.
    #
    # NOTE: Adding the heavy layers here, once per directory, judged a walk as fast as
    # NOTE: passing them to `is_ignored` separately, or keeping them in front of the
    # NOTE: returned layers and adding each ignore-file's behind them: within 0.6% on
    # NOTE: Python 3.11 and 3.14 on arm64 macOS.
    judging = heavy_layers + layers

    if judging:
        candidates = [
            (name, is_dir)
            for name, is_dir in candidates
            if not is_ignored(judging, name, prefix + name, is_dir)
        ]

    return candidates, layers
