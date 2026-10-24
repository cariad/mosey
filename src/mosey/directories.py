"""Functions for working with directories.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import os

from .candidate import Candidate
from .ignore_files import read_ignore_file, split_ignore_file
from .paths import sort_key
from .rules import Layers, compile_rules, is_ignored


def list_candidates(
    directory: str,
    *,
    ignore_symlinks: bool = False,
) -> list[Candidate]:
    """Return a directory's candidates in walk order.

    Only directories, files, and symlinks are candidates; anything else is excluded.
    With `ignore_symlinks`, symlinks are excluded too.

    The walk order is documented at https://cariad.github.io/mosey/walk-order/, and
    symlinks at https://cariad.github.io/mosey/symlinks/.

    Args:
        directory: Path to the directory to list.
        ignore_symlinks: Whether or not to leave out symlinks.

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
                candidate = (
                    entry.name,
                    False,  # Is a directory
                    False,  # Is a symlink
                )

                candidates.append(candidate)
            elif entry.is_dir(follow_symlinks=False):
                candidate = (
                    entry.name,
                    True,  # Is a directory
                    False,  # Is a symlink
                )

                candidates.append(candidate)

            # Files and directories never reach this check, so ignoring symlinks costs
            # them nothing.
            #
            # NOTE: On Python 3.11 to 3.14 on arm64 macOS, the check changed walks by
            # NOTE: 0.5% or less with symlinks kept. When it left symlinks out of every
            # NOTE: walk, ignoring them changed walks of a tree without symlinks by 0.6%
            # NOTE: or less, and made walks of a tree where 5% of entries are symlinks
            # NOTE: 0.3-1.8% faster, because they yielded fewer steps.
            elif entry.is_symlink() and not ignore_symlinks:
                candidate = (
                    entry.name,
                    False,  # Is a directory
                    True,  # Is a symlink
                )

                candidates.append(candidate)

    candidates.sort(key=sort_key)
    return candidates


def read_directory(
    directory: str,
    prefix: str,
    heavy_layers: Layers,
    layers: Layers,
    ignore_filename: str | None,
    ignore_filename_layers: Layers,
    *,
    ignore_symlinks: bool = False,
) -> tuple[list[Candidate], Layers]:
    """Return a directory's candidates that aren't ignored, in walk order.

    With an ignore-file name, the directory's ignore-file is the candidate with exactly
    that name, unless it's a directory. A symlink with that name is read through the
    link, even when the walk ignores symlinks, but then it's left out before anything
    is judged, so nothing can re-include it. The file's rules go in front of the layers
    from the directories above, and each candidate is then judged against them all, the
    ignore-file included. So a directory's own ignore-file judges everything inside it,
    but never the directory itself, which only the ignore-files above it and the
    patterns given in code can judge.

    The heavy layers judge each candidate before any of the others, so they overrule
    every ignore-file. When the directory holds the ignore-file, the ignore-filename
    layers judge after all the others, so they only leave out the ignore-file if nothing
    else matches it.

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
        ignore_filename_layers: The layers that leave out the ignore-file, or no layers
            to yield it.
        ignore_symlinks: Whether the walk ignores symlinks.

    Returns:
        The candidates that aren't ignored, in walk order, and the layers for the
        directory's subdirectories: this directory's own, if its ignore-file has any
        rules, then `layers`. Neither the heavy layers nor `ignore_filename_layers` are
        ever among them.

    Raises:
        OSError: When the directory can't be listed, the type of an object within it
            can't be looked up, or the ignore-file can't be read.
    """
    # Every symlink is listed, even when the walk ignores them, so that a symlinked
    # ignore-file can still be found and read. They're left out once it has been.
    candidates = list_candidates(
        directory,
    )

    # The layers that judge last of all, and only in this directory.
    lowest: Layers = ()

    # We look for the ignore-file in the listing rather than trying to open it, so a
    # directory without one costs no extra system call. It also means the name has to
    # match exactly: a file named "IGNORE" is never read as "ignore", even on a file
    # system that would open it.
    #
    # NOTE: The listing is sorted, and a file and a symlink with the same name share a
    # NOTE: sort key, so one binary search with `bisect` could find the ignore-file too,
    # NOTE: but most directories are too small for that to pay off. Scanning twice for a
    # NOTE: name that isn't there took about 105-140 nanoseconds with 5 candidates and
    # NOTE: 300-400 with 20, and a search about 170-240 and 310-470, so a search only
    # NOTE: wins above about 15-35. When the ignore-file is a file, the first scan stops
    # NOTE: at it, and beat a search even with 100. With the name set, walks of a
    # NOTE: virtual environment's site-packages, where most directories hold 10 or fewer
    # NOTE: candidates, and of a generated tree with about 21 in each, changed by -0.8%
    # NOTE: to +0.5% with a search on Python 3.11 to 3.14 on arm64 macOS, about the 0.7%
    # NOTE: that two identical copies of the code differed by. A single scan, with a
    # NOTE: marker for symlinks that equals `False`, saved 0.8% or less: not enough to
    # NOTE: be worth a marker that equals what it isn't.
    #
    # The ignore-file is a file or a symlink, so the listing might hold either.
    ignore_file: Candidate | None = None

    if ignore_filename is not None:
        as_file = (
            ignore_filename,
            False,  # Is a directory
            False,  # Is a symlink
        )

        as_symlink = (
            ignore_filename,
            False,  # Is a directory
            True,  # Is a symlink
        )

        if as_file in candidates:
            ignore_file = as_file
        elif as_symlink in candidates:
            ignore_file = as_symlink

    if ignore_file is not None:
        path = os.path.join(
            directory,
            ignore_file[0],
        )

        rules = compile_rules(split_ignore_file(read_ignore_file(path)))

        # The deepest ignore-file decides first, so this directory's rules go in front.
        if rules is not None:
            layers = ((prefix, *rules), *layers)

        # Leaving out the ignore-file ranks below every ignore-file and pattern, so its
        # layers go behind all the others, whether or not the file has rules. They only
        # match a file or symlink with exactly the ignore-file's name, and the only one
        # is the ignore-file itself, so they'd change nothing in a directory without it.
        # Like the heavy layers, they're never returned.
        #
        # NOTE: On Python 3.11 and 3.14 on arm64 macOS, leaving out the ignore-files
        # NOTE: this way changed walks of 24,000 files in a virtual environment's
        # NOTE: site-packages by under 2%, with no ignore-files or with 38. In a
        # NOTE: generated tree of 23,000 files, with an ignore-file in each of its 1,111
        # NOTE: directories, walks took 2.3-2.6% longer. A pattern for the name in the
        # NOTE: light layers took 4-11% longer on 3.14, because every entry in every
        # NOTE: directory was then judged. Judging only the ignore-file a second time,
        # NOTE: with these layers last, cost about a third as much as this with an
        # NOTE: ignore-file in every directory, but needs another scan of the listing.
        lowest = ignore_filename_layers

    # The walk never yields a symlink when it ignores them, so they're left out here,
    # before any line or pattern could re-include one.
    if ignore_symlinks:
        candidates = [candidate for candidate in candidates if not candidate[2]]

    # The heavy layers go in front of every ignore-file's, but only for judging. They're
    # never returned with the other layers, so a subdirectory's ignore-file still goes
    # in front of the layers from the directories above, and behind the heavy layers.
    #
    # NOTE: Adding the heavy layers here, once per directory, judged a walk as fast as
    # NOTE: passing them to `is_ignored` separately, or keeping them in front of the
    # NOTE: returned layers and adding each ignore-file's behind them: within 0.6% on
    # NOTE: Python 3.11 and 3.14 on arm64 macOS.
    judging = heavy_layers + layers + lowest

    if not judging:
        return candidates, layers

    # Each candidate that isn't ignored is kept as it is, rather than built again.
    kept = [
        candidate
        for candidate in candidates
        if not is_ignored(
            judging,
            candidate[0],
            prefix + candidate[0],
            candidate[1],
        )
    ]

    return kept, layers
