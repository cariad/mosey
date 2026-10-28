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

from .candidate import Candidate
from .directories import list_candidates, read_directory
from .exceptions import raise_file_not_found
from .mosey_step import MoseyStep
from .paths import split_start
from .rules import Layers
from .step import Step


@final
class MoseyWalker:
    """A directory walker, built by `Mosey.build`.

    It's what the `Walker` protocol describes, and pyright checks that it still matches
    wherever `Mosey.build` returns one.
    """

    __slots__ = (
        "_heavy_layers",
        "_ignore_filename",
        "_ignore_filename_layers",
        "_ignore_symlinks",
        "_judges",
        "_light_layers",
    )

    _heavy_layers: Final[Layers]
    """The layers for the patterns given in code that overrule every ignore-file."""

    _ignore_filename: Final[str | None]
    """Filename of the ignore-files to read, or `None` to read none."""

    _ignore_filename_layers: Final[Layers]
    """The layers that leave out the ignore-files, or no layers to yield them.

    They judge after every other layer, and only in a directory that holds the
    ignore-file."""

    _ignore_symlinks: Final[bool]
    """Whether the walk ignores symlinks, so that it never yields them."""

    _judges: Final[bool]
    """Whether the walk judges any entries: `True` if it reads ignore-files or has any
    patterns given in code."""

    _light_layers: Final[Layers]
    """The layers for the patterns given in code that every ignore-file overrules."""

    def __init__(
        self,
        *,
        heavy_layers: Layers,
        ignore_filename: str | None,
        ignore_filename_layers: Layers,
        ignore_symlinks: bool,
        light_layers: Layers,
    ) -> None:
        """Initialise a `MoseyWalker`.

        Arguments are trusted implicitly, and so this initialiser isn't intended to be
        called outside of the `mosey` package. `Mosey.build` checks them first.

        Args:
            heavy_layers: The layers for the patterns given in code that overrule every
                ignore-file.
            ignore_filename: Filename of the ignore-files to read, or `None` to read
                none.
            ignore_filename_layers: The layers that leave out the ignore-files
                themselves, or no layers to yield them.
            ignore_symlinks: Whether the walk ignores symlinks, so that it never yields
                them.
            light_layers: The layers for the patterns given in code that every
                ignore-file overrules.
        """
        self._heavy_layers = heavy_layers
        self._ignore_filename = ignore_filename
        self._ignore_filename_layers = ignore_filename_layers
        self._ignore_symlinks = ignore_symlinks
        self._light_layers = light_layers

        self._judges = (
            ignore_filename is not None or bool(heavy_layers) or bool(light_layers)
        )

    def _iterate(
        self,
        root: Path,
        names: tuple[str, ...],
    ) -> Iterator[Step]:
        """Walk a directory and yield a `Step` for every file that isn't ignored.

        The walk is depth-first and yields files in the walk order documented at
        https://cariad.github.io/mosey/walk-order/.

        The directory, and the directory to start in, are expected to have been
        validated before calling.

        Args:
            root: Path to the directory to walk.
            names: The names of the directories to pass through to reach the directory
                to start in, outermost first.

                For example, `("a", "b")` starts in "root/a/b".

                An empty tuple starts in `root` itself.

        Yields:
            A `Step` for every file that isn't ignored.
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
        #    it, deepest first, then the light layers, for reading its subdirectories.
        #    They're always empty when the walk judges nothing.
        #
        # A relative root is resolved against the working directory each time a
        # directory is listed, so changing the working directory partway through a walk
        # changes what gets walked. We don't guard against that: each step's path
        # starts with the same relative root, so it would point into the new directory
        # anyway. `os.walk` behaves the same way.
        directory = os.fspath(root)
        prefix = ""

        # The light layers start the walk's layers, so each ignore-file's layer goes in
        # front of them, and every ignore-file overrules them.
        candidates, layers = self._read_directory(
            directory,
            prefix,
            self._light_layers,
        )

        # The walk reaches the directory to start in just as a walk of the root would on
        # its way there, reading every ignore-file above it, but listing nothing beside
        # it. Documented at https://cariad.github.io/mosey/starting-directories/.
        for name in names:
            # The name was checked to be a directory in the listing, so if it isn't a
            # candidate now, it's ignored, and a walk of the root would never reach it.
            if (name, True, False) not in candidates:
                return

            directory = os.path.join(directory, name)
            prefix = prefix + name + "/"

            candidates, layers = self._read_directory(
                directory,
                prefix,
                layers,
            )

        stack = [(directory, prefix, iter(candidates), layers)]

        # NOTE: Some reviewers suggest a loop that takes one candidate at a time with
        # NOTE: `next(iterator, None)` instead, and never breaks out of a `for` loop.
        # NOTE:
        # NOTE: Claude helped me benchmark both shapes on Python 3.11 to 3.14 on arm64
        # NOTE: macOS; the `next` approach took 20-26% longer looping per file, which
        # NOTE: made a walk of a real directory about 2% slower.
        while stack:
            directory, prefix, candidates, layers = stack[-1]

            for name, is_dir, is_symlink in candidates:
                if is_dir:
                    path = os.path.join(directory, name)
                    path_prefix = prefix + name + "/"

                    # When the walk judges nothing, the subdirectory is listed exactly
                    # as it would be if ignore-files and patterns didn't exist.
                    if self._judges:
                        path_candidates, path_layers = read_directory(
                            path,
                            path_prefix,
                            self._heavy_layers,
                            layers,
                            self._ignore_filename,
                            self._ignore_filename_layers,
                            ignore_symlinks=self._ignore_symlinks,
                        )
                    else:
                        path_candidates = list_candidates(
                            path,
                            ignore_symlinks=self._ignore_symlinks,
                        )

                        path_layers = layers

                    # Add this subdirectory to the stack...
                    stack.append(
                        (
                            path,
                            path_prefix,
                            iter(path_candidates),
                            path_layers,
                        )
                    )

                    # ...and now break to walk it.
                    #
                    # When it's done, *this* directory's frame will be back on top of
                    # the stack, and its iterator carries on from the candidate after
                    # the subdirectory.
                    break

                yield MoseyStep(
                    name,
                    prefix + name,
                    root,
                    is_symlink=is_symlink,
                )

            else:
                # We're done with this directory.
                stack.pop()

    def _read_directory(
        self,
        directory: str,
        prefix: str,
        layers: Layers,
    ) -> tuple[list[Candidate], Layers]:
        """Return a directory's candidates that aren't ignored, and its layers.

        The walk reads its root, and the directories down to the one it starts in, with
        this. It reads every other directory itself, in the same way, to save a call.

        Args:
            directory: Path to the directory to read.
            prefix: The directory's path relative to the walk's root, with a "/" after
                each name: "" for the root, or "a/b/" for "root/a/b".
            layers: The layers from the ignore-files in every directory above this one,
                deepest first, then the light layers.

        Returns:
            The candidates that aren't ignored, in walk order, and the layers for the
            directory's subdirectories.
        """
        # NOTE: We check whether the walk judges anything here and for every
        # NOTE: subdirectory in `_iterate`, rather than keep a second copy of the loop
        # NOTE: for walks that don't. On Python 3.11 to 3.14 on arm64 macOS, a walk with
        # NOTE: no name or patterns took 0-0.6% longer than before ignore-files, and a
        # NOTE: walk with a name that no file in the tree has took 0.6-1.4% longer.
        # NOTE: Adding default and overriding patterns changed neither: within 0.2%.
        if self._judges:
            return read_directory(
                directory,
                prefix,
                self._heavy_layers,
                layers,
                self._ignore_filename,
                self._ignore_filename_layers,
                ignore_symlinks=self._ignore_symlinks,
            )

        candidates = list_candidates(
            directory,
            ignore_symlinks=self._ignore_symlinks,
        )

        return candidates, layers

    def walk(
        self,
        root: os.PathLike[str] | str,
        *,
        start: os.PathLike[str] | str = ".",
    ) -> Iterator[Step]:
        """Walk a directory, as documented by the `Walker` protocol's `walk`."""
        # The path to start in is checked before the file system is touched.
        names = split_start(start)

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

        # The directory to start in is checked one name at a time, by looking for each
        # name in its directory's listing, spelled exactly as the file system spells
        # it, and never following a symlink, because a walk of the root would never
        # walk into one. Like the root, a directory to start in that can't exist raises
        # `FileNotFoundError`, and one that isn't a directory raises
        # `NotADirectoryError`.
        #
        # Each name is only joined on with `os.path.join` once it's found in the
        # listing. Joining one that isn't there would throw away everything before it on
        # Windows if it had a drive, like "C:", so an error names its path by adding it
        # after a separator instead. Joining nothing to the root first ends it with a
        # separator, unless it already ends with one, like "/" or "C:\\".
        base = os.path.join(root_str, "")
        start_str = root_str

        for index, name in enumerate(names):
            candidates = list_candidates(start_str)

            if (name, True, False) in candidates:
                start_str = os.path.join(start_str, name)
                continue

            path = base + os.sep.join(names[: index + 1])

            if (name, False, False) not in candidates and (
                name,
                False,
                True,
            ) not in candidates:
                raise_file_not_found(path)

            # Something beneath a file or a symlink can't be walked to, so it can't
            # exist as far as the walk is concerned.
            if index < len(names) - 1:
                raise_file_not_found(base + os.sep.join(names))

            raise NotADirectoryError(
                errno.ENOTDIR,
                os.strerror(errno.ENOTDIR),
                path,
            )

        if names:
            with os.scandir(start_str):
                pass

        # Validation is done, so hand over to the generator.
        #
        # We intentionally don't `yield` anything in this function so that the checks
        # above run immediately rather than waiting for the first call to `next()`.
        return self._iterate(
            root_path,
            names,
        )
