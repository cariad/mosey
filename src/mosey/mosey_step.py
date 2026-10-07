"""The `MoseyStep` class, which describes a file system object discovered by a walk.

This is an internal class for the `mosey` package. It isn't exported, and its shape can
change without notice. Callers annotate it with the `Step` protocol.

The walker constructs a `MoseyStep` for every file it yields, so this module is on the
hot path and favours speed over memory. This includes:

- Constructing a `MoseyStep` never validates its arguments.
- Constructing a `MoseyStep` never touches the file system.
- Values that the walker already has to hand are stored as plain attributes, even when
  that duplicates data, so callers don't need to parse values themselves.
- Anything that takes time to build, like `path`, is built on-demand then cached.
- Attributes are plain rather than read-only properties, which are slower to read. The
  `Step` protocol declares them as read-only properties, so type checkers still refuse
  to let callers change them.
"""

from pathlib import Path
from typing import Final, final


@final
class MoseyStep:
    """A file system object discovered by a walk.

    It's what the `Step` protocol describes, and pyright checks that it still matches
    wherever the walker yields one.

    The class is intentionally optimised for performance rather than memory or code
    redundancy. For example, the filename is stored twice; in `name` and part of
    `relative_as_posix`. We have those values anyway when we construct an instance, and
    "wasting" bytes on duplicate data means the caller spends less time parsing strings
    themselves.
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
    """The object's filename."""

    relative_as_posix: Final[str]
    """The object's path relative to `root` as a POSIX-style string."""

    root: Final[Path]
    """The walk's root directory."""

    def __init__(
        self,
        name: str,
        relative_as_posix: str,
        root: Path,
    ) -> None:
        """Initialise a `MoseyStep`.

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
        # Callers know this as a `Step`, so that's the name it goes by. A `Step` can't
        # be created by calling it, so the angle brackets show that this isn't a call.
        return f"<Step {self.relative_as_posix!r}>"

    @property
    def path(self) -> Path:
        """Path to the file system object, built on-demand then cached."""
        # NOTE: Some reviewers critique this code reading the `_path` slot twice, and
        # NOTE: suggest loading the path into a local variable to read twice instead.
        # NOTE:
        # NOTE: Claude helped me benchmark both approaches on Python 3.11 to 3.14 on
        # NOTE: arm64 macOS: using a local variable was never faster, and was in fact
        # NOTE: 10-20% slower on 3.13+.
        if self._path is None:
            self._path = self.root / self.relative_as_posix
        return self._path
