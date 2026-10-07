"""The `Step` protocol, which describes a file system object discovered by a walk.

`Step` is exported by the `mosey` package, so import it from there rather than this
module.
"""

from pathlib import Path
from typing import Protocol


class Step(Protocol):
    """A file system object discovered by a walk.

    A [`Walker`][mosey.Walker] yields one for every file it finds. `Step` is the type to
    annotate them with: you never create one yourself.

    Treat every member as read-only. Type checkers refuse to let you change them, but
    nothing stops it at run time, and the consequences are undefined.
    """

    @property
    def name(self) -> str:
        """The object's filename.

        Fast to read. The filename is in [`relative_as_posix`][] too, and included here
        for convenience.

        It's spelled exactly as the file system reports it, without any translation.
        """
        ...

    @property
    def path(self) -> Path:
        """Path to the file system object.

        The path is constructed then cached on-demand, so consider using [`name`][] or
        [`relative_as_posix`][] instead for performance if you can.
        """
        ...

    @property
    def relative_as_posix(self) -> str:
        """The object's path relative to [`root`][] as a POSIX-style string.

        Fast to read, and the same format as the [ignore-files'][ignore-files] patterns.

        POSIX-style paths always use forward slashes as separators regardless of the
        operating system, so this string will look familiar to Linux and macOS users
        but might be surprising in Windows where backslashes are conventional.

        If you need a path in the local operating system's convention, read [`path`][].

        If you only need the filename, read [`name`][].

        Like [`name`][], it spells each filename exactly as the file system reports it.
        """
        ...

    @property
    def root(self) -> Path:
        """The walk's root directory.

        Fast to read.
        """
        ...
