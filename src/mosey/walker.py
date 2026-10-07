"""The `Walker` protocol, which describes a walker that yields a `Step` for each file.

`Walker` is exported by the `mosey` package, so import it from there rather than this
module.
"""

import os
from collections.abc import Iterator
from typing import Protocol

from .step import Step


class Walker(Protocol):
    """A directory walker, built by [`Mosey.build`][mosey.Mosey.build].

    `Walker` is the type to annotate walkers with: you never create one yourself.

    A walker never changes once it's built, so one walker can take any number of walks,
    one after another or at the same time, on any number of threads. Each call to
    [`walk`][mosey.Walker.walk] returns its own iterator: share the walker between
    threads, but never an iterator.
    """

    def walk(self, root: os.PathLike[str] | str) -> Iterator[Step]:
        """Walk a directory and yield a [`Step`][mosey.Step] for every file not ignored.

        Files are yielded in a deterministic walk order, documented at
        https://cariad.github.io/mosey/walk-order/.

        When the walker has an ignore-file name (set by
        [`Mosey.set_ignore_filename`][mosey.Mosey.set_ignore_filename]), each
        directory's [ignore-file][ignore-files] is read when the walk reaches the
        directory, and the files and directories its patterns ignore aren't yielded or
        walked, along with everything inside them.

        A relative root is found from the working directory each time a subdirectory is
        read, so don't change the working directory during a walk.

        Args:
            root: Path to the directory to walk.

        Returns:
            An iterator of [`Step`][mosey.Step]; one for every file not ignored.

                The iterator raises [`OSError`][] when it can't list `root` or a
                directory beneath it, say because it vanished, or permissions deny
                reading it or searching the directory that holds it.

                When the walker has an ignore-file name, it also raises [`OSError`][]
                when it can't read an ignore-file, say because it's a broken symlink or
                permissions deny reading it.

                `root` itself isn't listed until the first step is requested.

        Raises:
            FileNotFoundError: When `root` is empty, doesn't exist, or can't exist (e.g.
                when its parent isn't a directory).
            NotADirectoryError: When `root` isn't a directory.
            OSError: When the operating system can't resolve `root` for another reason,
                like its name being too long or a loop of symlinks.
            PermissionError: When file system permissions deny reaching or listing
                `root`.
            ValueError: When `root` contains a null character.
        """
        ...
