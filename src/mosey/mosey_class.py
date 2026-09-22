"""The `Mosey` class, which walks directories and yields `Step` for matching objects.

This module is still in early development, so expect `NotImplementedError` to be raised
early and often where functionality is missing.

`Mosey` is exported by the `mosey` package, so import it from there rather than this
module.
"""

import errno
import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

from .exceptions import raise_file_not_found
from .step import Step


class Mosey:
    """A directory walker."""

    def _iterate(self) -> Iterator[Step]:
        """Yield a `Step` for every matching file system object.

        Raises:
            NotImplementedError: Always; the function isn't implemented.
        """
        # TODO: Implement the walk here.
        raise NotImplementedError()

    def walk(self, root: os.PathLike[str] | str) -> Iterator[Step]:
        """Walk a directory.

        Args:
            root: Path to the directory to walk.

        Returns:
            An iterator of [`Step`][mosey.Step]; one for every matching object.

        Raises:
            FileNotFoundError: When `root` is empty, doesn't exist, or can't exist (e.g.
                when its parent isn't a directory).
            NotADirectoryError: When `root` isn't a directory.
            NotImplementedError: Always; the function isn't implemented.
            OSError: When the operating system can't resolve `root` for another reason,
                like its name being too long or a loop of symlinks.

                For a loop of symlinks, [`errno`][OSError.errno] is:

                - [`errno.EINVAL`][] on Windows, where [`winerror`][OSError.winerror] is
                  1921 (`ERROR_CANT_RESOLVE_FILENAME`).
                - [`errno.ELOOP`][] on Linux and macOS.
            PermissionError: When file system permissions deny the walk.
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
        return self._iterate()
