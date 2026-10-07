"""The `Mosey` class, which describes a walk and builds a `Walker` to take it.

`Mosey` is exported by the `mosey` package, so import it from there rather than this
module.
"""

from typing import final

from .mosey_walker import MoseyWalker
from .walker import Walker


@final
class Mosey:
    """A description of a directory walk, which builds a [`Walker`][mosey.Walker].

    Describe the walk you want with this class's methods, then call
    [`build`][mosey.Mosey.build] to build a walker that follows it.

    ```python
    builder = Mosey()
    builder.set_ignore_filename(".walkignore")
    walker = builder.build()

    for step in walker.walk("."):
        print(step.relative_as_posix)
    ```

    A walker never changes, so build one and walk with it as often as you like, on any
    number of threads.

    Describe the walk on one thread, then share the walker rather than the `Mosey`.
    """

    __slots__ = ("_ignore_filename",)

    _ignore_filename: str | None
    """Filename of the ignore-files to read, or `None` to read none."""

    def __init__(self) -> None:
        """Initialise a `Mosey` describing a walk that reads no ignore-files."""
        self._ignore_filename = None

    def set_ignore_filename(self, name: str) -> None:
        """Set the filename of the ignore-files that the walk reads.

        When the walk reaches a directory, it reads the directory's
        [ignore-file][ignore-files] with this name, if it has one, then doesn't yield or
        walk the files and directories that its patterns ignore.

        The walk reads no ignore-files unless this is called. Calling it again replaces
        the name set before, so a walk reads ignore-files with one name only.

        Args:
            name: Filename of the ignore-files to read. For example, `.walkignore`.

        Raises:
            ValueError: When `name` is empty, "." or "..", or holds a slash, a backslash
                or a null character.
        """
        # The name is a filename, not a path. A backslash is refused on every operating
        # system, not only on Windows, so that the same names are accepted everywhere.
        if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
            raise ValueError(f"{name!r} isn't a filename")

        self._ignore_filename = name

    def build(self) -> Walker:
        """Build a walker that takes the walk described.

        The walker keeps its own copy of the description and never changes, so changing
        this `Mosey` afterwards doesn't change the walkers it has already built. Build
        again for a walker that takes the new walk.

        Returns:
            A new [`Walker`][mosey.Walker].
        """
        return MoseyWalker(ignore_filename=self._ignore_filename)
