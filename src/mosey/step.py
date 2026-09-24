"""The `Step` class, which describes a file system object discovered by a walk.

The walker constructs a `Step` for every object it yields, so this module is on the hot
path and favours speed over memory. This includes:

- Constructing a `Step` never validates its arguments.
- Constructing a `Step` never touches the file system.
- Values that the walker already has to hand are stored as plain attributes, even when
  that duplicates data, so callers don't need to parse values themselves.
- Anything that takes time to build, like `Step.path`, is built on-demand then cached.
- Attributes are plain rather than read-only properties, which are slower to read.

`Step` is exported by the `mosey` package, so import it from there rather than this
module.

`Step` is intended to be instantiated by `mosey` internals only; external callers should
have no need to construct their own.
"""

from pathlib import Path
from typing import Final, final


@final
class Step:
    """A file system object discovered by a walk.

    The class is intentionally optimised for performance rather than memory or code
    redundancy. For example, the filename is stored twice; in [`name`][] and part of
    [`relative_as_posix`][]. We have those values anyway when we construct an instance,
    and "wasting" bytes on duplicate data means the caller spends less time parsing
    strings themselves.

    Another compromise for performance is mutability. Nothing prevents the caller
    modifying, say, `name`, to break its consistency with `relative_as_posix`. Please
    treat all attributes as read-only, because the consequences are undefined.
    """

    __slots__ = (
        "_path",
        "name",
        "relative_as_posix",
        "root",
    )

    _path: Path | None
    """The path to the object.

    `None` until it's constructed on-demand by the `path` property.
    """

    name: Final[str]
    """The object's filename.

    Fast to read. The filename is in [`relative_as_posix`][] too, and included here for
    convenience.

    The filename is exactly as the file system stores it. On macOS, that isn't always
    how Git spells it. An accented letter can be stored "decomposed", as a letter then
    a combining accent, and Git then usually reports it "composed", as one character:

    ```
    Stored, and reported by mosey:  "e" then U+0301  (bytes 65 CC 81)
    Reported by Git:                U+00E9           (bytes C3 A9)
    ```

    Git does this when `core.precomposeunicode` is on, which `git init` and `git clone`
    turn on for repositories on macOS.
    """

    relative_as_posix: Final[str]
    """The object's path relative to [`root`][] as a POSIX-style string.

    Fast to read, and the same format as the ignore-files' patterns.

    POSIX-style paths always use forward-slashes as separators regardless of the
    operating system, so this string will look familiar to Linux and macOS users
    but might be surprising in Windows where back-slashes are conventional.

    If you need a path in the local operating system's convention, read [`path`][].

    If you only need the filename, read [`name`][].

    Like [`name`][], it spells each filename exactly as the file system stores it.
    """

    root: Final[Path]
    """The walk's root directory.

    Fast to read.
    """

    def __init__(
        self,
        name: str,
        relative_as_posix: str,
        root: Path,
    ) -> None:
        """Initialise a `Step`.

        For performance, there's intentionally no validation that — for example — the
        `relative_as_posix` path describes the same filename as `name`.

        Arguments are trusted implicitly, and so this initialiser isn't intended to be
        called outside of the `mosey` package.

        Args:
            name: The object's filename.
            relative_as_posix: The object's path relative to `root` as a POSIX-style
                string.
            root: The walk's root directory.
        """
        self._path = None
        self.name = name
        self.relative_as_posix = relative_as_posix
        self.root = root

    def __repr__(self) -> str:
        """Return the canonical string representation of the step."""
        return f"Step({self.relative_as_posix!r})"

    @property
    def path(self) -> Path:
        """Path to the file system object.

        The path is constructed then cached on-demand, so consider using [`name`][] or
        [`relative_as_posix`][] instead for performance if you can.
        """
        # NOTE: Some reviewers critique this code reading the `_path` slot twice, and
        # NOTE: suggest loading the path into a local variable to read twice instead.
        # NOTE:
        # NOTE: Claude helped me benchmark both approaches on Python 3.11 to 3.14 on
        # NOTE: arm64 macOS: using a local variable was never faster, and was in fact
        # NOTE: 10-20% slower on 3.13+.
        if self._path is None:
            self._path = self.root / self.relative_as_posix
        return self._path
