"""The `Mosey` class, which describes a walk and builds a `Walker` to take it.

`Mosey` is exported by the `mosey` package, so import it from there rather than this
module.
"""

from operator import itemgetter
from typing import final

from .binary_files import BINARY_FILE_PATTERNS
from .mosey_walker import MoseyWalker
from .patterns import check_pattern
from .rules import compile_ignore_filename_layers, compile_root_layers
from .walker import Walker


@final
class Mosey:
    """A description of a directory walk, which builds a [`Walker`][mosey.Walker].

    Describe the walk you want with this class's methods, then call
    [`build`][mosey.Mosey.build] to build a walker that follows it.

    ```python
    builder = Mosey()
    builder.set_ignore_filename(".walkignore")
    builder.add_pattern("*.pdf")
    walker = builder.build()

    for step in walker.walk("."):
        print(step.relative_as_posix)
    ```

    A walker never changes, so build one and walk with it as often as you like, on any
    number of threads.

    Describe the walk on one thread, then share the walker rather than the `Mosey`.
    """

    __slots__ = (
        "_ignore_filename",
        "_ignore_ignore_files",
        "_patterns",
    )

    _ignore_filename: str | None
    """Filename of the ignore-files to read, or `None` to read none."""

    _ignore_ignore_files: bool
    """Whether the walk leaves out the ignore-files, rather than yielding them.

    Only read when `_ignore_filename` isn't `None`.
    """

    _patterns: tuple[tuple[int, str], ...]
    """Each pattern given in code, after its weight, in the order they were added.

    A tuple rather than a list, so that a copy of a `Mosey` never shares it.
    """

    def __init__(self) -> None:
        """Initialise a `Mosey` describing a walk with no ignore-files or patterns."""
        self._ignore_filename = None
        self._ignore_ignore_files = True
        self._patterns = ()

    def add_pattern(
        self,
        pattern: str,
        *,
        weight: int = 0,
    ) -> None:
        """Add a pattern that the walk judges files and directories by.

        Write the pattern exactly like a line of an [ignore-file][ignore-files] in the
        directory you walk. The walk doesn't yield or walk the files and directories
        that the pattern ignores, whether or not the walk reads ignore-files.

        The pattern's weight says whether the ignore-files can overrule it, as
        documented at
        [default and overriding patterns][default-and-overriding-patterns].

        Args:
            pattern: The pattern. For example, `*.pdf`.
            weight: The pattern's weight, which decides whether the ignore-files can
                overrule it.

        Raises:
            ValueError: When an ignore-file would read `pattern` differently, it's
                broken, or it holds a backslash that escapes nothing, as listed at
                [default and overriding patterns][default-and-overriding-patterns].
        """
        check_pattern(pattern)
        self._patterns = (*self._patterns, (weight, pattern))

    def ignore_binary_files(
        self,
        *,
        weight: int = 0,
    ) -> None:
        """Ignore binary files, like images, archives, and applications.

        Adds every pattern in [`BINARY_FILE_PATTERNS`][mosey.BINARY_FILE_PATTERNS], in
        order, exactly as [`add_pattern`][mosey.Mosey.add_pattern] would with the same
        weight. Which files the patterns match is documented at
        [binary files][binary-files].

        Args:
            weight: The patterns' weight, which decides whether the ignore-files can
                overrule them.
        """
        # The patterns are fixed, and the tests check every one, so there's nothing to
        # check here.
        self._patterns = (
            *self._patterns,
            *((weight, pattern) for pattern in BINARY_FILE_PATTERNS),
        )

    def set_ignore_filename(
        self,
        name: str,
        *,
        ignore: bool = True,
    ) -> None:
        """Set the filename of the ignore-files that the walk reads.

        When the walk reaches a directory, it reads the directory's
        [ignore-file][ignore-files] with this name, if it has one, then doesn't yield or
        walk the files and directories that its patterns ignore.

        By default, the walk doesn't yield the ignore-files themselves either, unless a
        line or pattern re-includes them, as documented at [ignore-files][ignore-files].
        With `ignore` set to `False`, it yields them like any other file.

        The walk reads no ignore-files unless this is called. Calling it again replaces
        the name and `ignore` set before, so a walk reads ignore-files with one name
        only.

        Args:
            name: Filename of the ignore-files to read. For example, `.walkignore`.
            ignore: Whether the walk leaves out the ignore-files that no line or pattern
                re-includes, rather than yielding them.

        Raises:
            ValueError: When `name` is empty, "." or "..", or holds a slash, a backslash
                or a null character.
        """
        # The name is a filename, not a path. A backslash is refused on every operating
        # system, not only on Windows, so that the same names are accepted everywhere.
        if name in ("", ".", "..") or "/" in name or "\\" in name or "\x00" in name:
            raise ValueError(f"{name!r} isn't a filename")

        self._ignore_filename = name
        self._ignore_ignore_files = ignore

    def build(self) -> Walker:
        """Build a walker that takes the walk described.

        The walker keeps its own copy of the description and never changes, so changing
        this `Mosey` afterwards doesn't change the walkers it has already built. Build
        again for a walker that takes the new walk.

        Returns:
            A new [`Walker`][mosey.Walker].
        """
        # Patterns of equal weight stay in the order they were added in, since `sorted`
        # is stable, so the last one added that matches still decides.
        patterns = sorted(self._patterns, key=itemgetter(0))

        # In that order, the last matching rule wins, and the ignore-files rank above
        # every pattern weighing 0 and below every pattern weighing 1. So the heavy
        # patterns judge before the ignore-files, and the light ones after. Leaving out
        # the ignore-files themselves ranks below them all, so any line or pattern that
        # matches an ignore-file decides first.
        name = self._ignore_filename

        return MoseyWalker(
            heavy_layers=compile_root_layers([p for w, p in patterns if w > 0]),
            ignore_filename=name,
            ignore_filename_layers=(
                compile_ignore_filename_layers(name)
                if name is not None and self._ignore_ignore_files
                else ()
            ),
            light_layers=compile_root_layers([p for w, p in patterns if w <= 0]),
        )
