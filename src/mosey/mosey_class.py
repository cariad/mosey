"""The `Mosey` class, which walks directories and yields `Step` for matching objects.

`Mosey` is exported by the `mosey` package, so import it from there rather than this
module.
"""

import errno
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

from .directories import list_candidates
from .exceptions import raise_file_not_found
from .step import Step


class Mosey:
    """A directory walker."""

    def _iterate(self, root: Path, root_str: str) -> Iterator[Step]:
        """Walk a directory and yield a `Step` for every file.

        The directory is expected to have been validated before calling.

        The walk is depth-first; when it meets a directory, it walks everything inside
        that directory before moving onto the directory's next sibling.

        Each directory's entries are sorted into Git's order, so the files come out in
        the order Git would list them.

        For example, given this directory:

        ```
        root/
        ├── b/
        │   └── x
        ├── b.txt
        └── c
        ```

        ...the walk yields its files in this order:

        ```
        b.txt
        b/x
        c
        ```

        Args:
            root: Path to the directory to walk, exactly as the caller passed it. Each
                `Step` keeps this, so it might be relative, and it can't be rebuilt
                from `root_str`.
            root_str: Absolute path to the same directory, for listing it and the
                directories beneath it.

                This can't be worked out from `root` in here. A generator's body
                doesn't run until the first call to `next()`, and by then the caller
                might have changed the working directory that a relative `root`
                resolves against. So `walk` works it out while it validates `root`.

        Yields:
            A `Step` for every file beneath `root`.
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
        stack = [(root_str, "", iter(list_candidates(root_str)))]

        # NOTE: Some reviewers suggest a loop that takes one candidate at a time with
        # NOTE: `next(iterator, None)` instead, and never breaks out of a `for` loop.
        # NOTE:
        # NOTE: Claude helped me benchmark both shapes on Python 3.11 to 3.14 on arm64
        # NOTE: macOS; the `next` approach took 20-26% longer looping per file, which
        # NOTE: made a walk of a real directory about 2% slower.
        while stack:
            directory, prefix, candidates = stack[-1]

            for name, is_dir in candidates:
                if is_dir:
                    path = os.path.join(directory, name)

                    # Add this subdirectory to the stack...
                    stack.append(
                        (path, prefix + name + "/", iter(list_candidates(path)))
                    )

                    # ...and now break to walk it.
                    #
                    # When it's done, *this* directory's frame will be back on top of
                    # the stack, and its iterator carries on from the candidate after
                    # the subdirectory.
                    break

                yield Step(name, prefix + name, root)

            else:
                # We're done with this directory.
                stack.pop()

    def walk(self, root: os.PathLike[str] | str) -> Iterator[Step]:
        """Walk a directory and yield a [`Step`][mosey.Step] for every file.

        Args:
            root: Path to the directory to walk.

        Returns:
            An iterator of [`Step`][mosey.Step]; one for every file.

                The iterator raises [`OSError`][] when it can't list a directory beneath
                `root`, say because it vanished or permissions deny reading it.

        Raises:
            FileNotFoundError: When `root` is empty, doesn't exist, or can't exist (e.g.
                when its parent isn't a directory).
            NotADirectoryError: When `root` isn't a directory.
            OSError: When the operating system can't resolve `root` for another reason,
                like its name being too long or a loop of symlinks.

                For a loop of symlinks, [`errno`][OSError.errno] is:

                - [`errno.EINVAL`][] on Windows, where [`winerror`][OSError.winerror] is
                  1921 (`ERROR_CANT_RESOLVE_FILENAME`).
                - [`errno.ELOOP`][] on Linux and macOS.
            PermissionError: When file system permissions deny reaching, listing or
                searching `root`.
            ValueError: When `root` contains a null character.
        """
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

        # A preflight check to see if we've got permission to walk the directory. We
        # won't actually start iterating, so it'll be quick. `scandir` will raise
        # `PermissionError` if we're not allowed to look.
        with os.scandir(root_str):
            pass

        # Reading a directory isn't enough to walk it. We also need permission to
        # *search* it ("execute" on POSIX), otherwise we could list the names inside but
        # never reach them.
        #
        # Nothing above checks that. `scandir` only lists names, which needs permission
        # to read. And `os.stat(root_str)` only searched the root's *parents* on the way
        # to the root. A directory's search permission is only checked when a path goes
        # *through* it to a name inside, so to test the root we need to look up a name
        # inside the root.
        #
        # We can't look up a real child because the root might be empty, and we can't
        # make one because we might not be allowed to write. But every directory holds
        # the name ".", which refers to the directory itself. So "root/." always exists,
        # and `os.stat` will find it if we can search the root or raise
        # `PermissionError` if we can't.
        #
        # We skip this on Windows for two reasons:
        #
        # Firstly, there's nothing to check. Windows has an equivalent permission named
        # "Traverse Folder", but by default it grants every user the "Bypass traverse
        # checking" privilege, so it's never enforced.
        #
        # Secondly, it would break extended-length paths. Windows normally tidies a path
        # before using it -- which includes collapsing any "." and ".." parts -- and
        # limits it to 260 characters. Starting a path with "\\?\" (for example,
        # "\\?\C:\docs") switches that tidying off and passes the path to the file
        # system verbatim, which is how programs reach paths longer than the limit.
        # With the tidying off, "\\?\C:\docs\." wouldn't collapse to the "docs"
        # directory; it'd ask for an object inside "docs" literally named ".", and
        # `os.stat` would fail for a perfectly good root.
        if sys.platform != "win32":
            os.stat(os.path.join(root_str, "."))

        # Validation is done, so hand over to the generator.
        #
        # We intentionally don't `yield` anything in this function so that the checks
        # above run immediately rather than waiting for the first call to `next()`.
        return self._iterate(root_path, os.fspath(root_path.absolute()))
