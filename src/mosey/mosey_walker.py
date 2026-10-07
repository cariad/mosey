"""The `MoseyWalker` class, which walks directories and yields a step for each file.

This is an internal class for the `mosey` package. It isn't exported, and its shape can
change without notice. `Mosey.build` creates one, and callers annotate it with the
`Walker` protocol.
"""

import errno
import os
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import Final, final

from .directories import list_candidates, read_directory
from .exceptions import raise_file_not_found
from .mosey_step import MoseyStep
from .step import Step


@final
class MoseyWalker:
    """A directory walker, built by `Mosey.build`.

    It's what the `Walker` protocol describes, and pyright checks that it still matches
    wherever `Mosey.build` returns one.
    """

    __slots__ = ("_ignore_filename",)

    _ignore_filename: Final[str | None]
    """Filename of the ignore-files to read, or `None` to read none."""

    def __init__(self, *, ignore_filename: str | None) -> None:
        """Initialise a `MoseyWalker`.

        Arguments are trusted implicitly, and so this initialiser isn't intended to be
        called outside of the `mosey` package. `Mosey.build` checks them first.

        Args:
            ignore_filename: Filename of the ignore-files to read, or `None` to read
                none.
        """
        self._ignore_filename = ignore_filename

    def _iterate(self, root: Path) -> Iterator[Step]:
        """Walk a directory and yield a `Step` for every file that isn't ignored.

        The walk is depth-first and yields files in the walk order documented at
        https://cariad.github.io/mosey/walk-order/.

        The directory is expected to have been validated before calling.

        Args:
            root: Path to the directory to walk.

        Yields:
            A `Step` for every file beneath `root` that isn't ignored.
        """
        # The walk keeps its own stack of directories rather than recursing. A recursive
        # generator would pass every file up through one `yield from` per level, so the
        # deeper the file, the more it costs to yield.
        #
        # `stack` is every directory we're partway through, deepest last. Each frame
        # holds:
        #
        #  - The directory's path, for listing its subdirectories.
        #  - The directory's path relative to the root, as a POSIX-style prefix for its
        #    entries: "" for the root, or "a/b/" for "root/a/b".
        #  - An iterator over the directory's remaining candidates. It has to be an
        #    iterator rather than the list itself, so that the `for` loop below resumes
        #    where it left off instead of starting the list again.
        #  - The layers from the ignore-files in the directory and every directory above
        #    it, deepest first, for reading its subdirectories. They're always empty
        #    when there's no ignore-file name.
        #
        # A relative root is resolved against the working directory each time a
        # directory is listed, so changing the working directory partway through a walk
        # changes what gets walked. We don't guard against that: each step's path
        # starts with the same relative root, so it would point into the new directory
        # anyway. `os.walk` behaves the same way.
        root_str = os.fspath(root)

        # NOTE: We check for an ignore-file name here and for every subdirectory below,
        # NOTE: rather than keep a second copy of the loop for walks without a name. On
        # NOTE: Python 3.11 to 3.14 on arm64 macOS, a walk with no name took 0-0.6%
        # NOTE: longer than before ignore-files, and a walk with a name that no file in
        # NOTE: the tree has took 0.6-1.4% longer.
        if self._ignore_filename is None:
            root_candidates, root_layers = list_candidates(root_str), ()
        else:
            root_candidates, root_layers = read_directory(
                root_str,
                "",
                (),
                self._ignore_filename,
            )

        stack = [(root_str, "", iter(root_candidates), root_layers)]

        # NOTE: Some reviewers suggest a loop that takes one candidate at a time with
        # NOTE: `next(iterator, None)` instead, and never breaks out of a `for` loop.
        # NOTE:
        # NOTE: Claude helped me benchmark both shapes on Python 3.11 to 3.14 on arm64
        # NOTE: macOS; the `next` approach took 20-26% longer looping per file, which
        # NOTE: made a walk of a real directory about 2% slower.
        while stack:
            directory, prefix, candidates, layers = stack[-1]

            for name, is_dir in candidates:
                if is_dir:
                    path = os.path.join(directory, name)
                    path_prefix = prefix + name + "/"

                    # Without an ignore-file name, the subdirectory is listed exactly as
                    # it would be if ignore-files didn't exist.
                    if self._ignore_filename is None:
                        path_candidates, path_layers = list_candidates(path), layers
                    else:
                        path_candidates, path_layers = read_directory(
                            path, path_prefix, layers, self._ignore_filename
                        )

                    # Add this subdirectory to the stack...
                    stack.append(
                        (path, path_prefix, iter(path_candidates), path_layers)
                    )

                    # ...and now break to walk it.
                    #
                    # When it's done, *this* directory's frame will be back on top of
                    # the stack, and its iterator carries on from the candidate after
                    # the subdirectory.
                    break

                yield MoseyStep(name, prefix + name, root)

            else:
                # We're done with this directory.
                stack.pop()

    def walk(self, root: os.PathLike[str] | str) -> Iterator[Step]:
        """Walk a directory, as documented by the `Walker` protocol's `walk`."""
        # `Path` normalises an empty string to ".", which would walk the current working
        # directory. This feels a bit unexpected, so we'll protect the user and have
        # them pass an explicit "." if that's what they want.
        #
        # `os.stat("")` would raise `FileNotFoundError`, so we'll do the same.
        if not os.fspath(root):
            raise_file_not_found("")

        # This probably looks like we've just taken a string, converted it to a `Path`,
        # then converted it back to a string -- but *this* string was cleaned up and
        # normalised by the `Path` conversion, so it's in a good state for walking.
        #
        # We need the string to use the file system's native path separators, so we
        # can't use `root_path.as_posix()`.
        #
        # We *could* use `str(root_path)`, which pathlib documents as the native file
        # system path, but `os.fspath` makes the intent explicit: we want the path
        # string, not just *any* string representation.
        root_path = Path(root)
        root_str = os.fspath(root_path)

        # A relative root is found from the working directory, so check that the working
        # directory still exists. If it's been deleted, `os.getcwd` raises
        # `FileNotFoundError`; without this check, the walk would quietly find nothing.
        if not root_path.is_absolute():
            os.getcwd()

        # Will raise:
        #  - `FileNotFoundError` if there's nothing there.
        #  - `PermissionError` if permissions deny searching one of the root's parents.
        #    `stat` doesn't need permission to read the root itself; we check that
        #    further down.
        try:
            root_stat = os.stat(root_str)
        except NotADirectoryError as error:
            # One of the root's parents isn't a directory (say, "README.md/docs"), so
            # the root can't exist.
            #
            # POSIX reports that as "not a directory" while Windows reports "not found".
            #
            # No object exists at the path either way, so we normalise to
            # `FileNotFoundError` for consistency across platforms.
            #
            # This can't be confused with the root itself not being a directory;
            # `os.stat` succeeds for that, and we check for it below. That relies on
            # `Path` having stripped any trailing separator above, because POSIX reports
            # "file/" as "not a directory" too.
            #
            # We pass the original error along as the cause so the traceback still shows
            # that a parent isn't a directory.
            raise_file_not_found(root_str, error)

        # We check `stat.S_ISDIR` instead of `root_path.is_dir()` because `is_dir`
        # handles permissions failures a bit differently between Python releases
        # (raising the exception vs swallowing and returning `False`).
        #
        # And `is_dir` calls `os.stat` anyway, which we've already done to check if the
        # object exists, so we may as well reuse the result we've already got.
        if not stat.S_ISDIR(root_stat.st_mode):
            raise NotADirectoryError(
                errno.ENOTDIR,
                os.strerror(errno.ENOTDIR),
                root_str,
            )

        # A preflight check to see if we've got permission to list the directory. We
        # won't actually start iterating, so it'll be quick. `scandir` will raise
        # `PermissionError` if we're not allowed to look.
        with os.scandir(root_str):
            pass

        # Validation is done, so hand over to the generator.
        #
        # We intentionally don't `yield` anything in this function so that the checks
        # above run immediately rather than waiting for the first call to `next()`.
        return self._iterate(root_path)
