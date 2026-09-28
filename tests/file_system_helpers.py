"""File system helper functions for unit tests."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pytest import skip

from mosey import Mosey
from mosey.patterns import Pattern
from tests.git_oracle import git_list_files


def can_make_symlinks() -> bool:
    """Check if symlinks can be created.

    Linux and macOS always allow it, but Windows only allows it for administrators and
    users who've enabled Developer Mode.

    Returns:
        `True` if symlinks can be created, otherwise `False`.
    """
    with TemporaryDirectory() as directory:
        try:
            Path(directory, "link").symlink_to("target")
        except OSError:
            return False

    return True


def format_pattern(pattern: Pattern) -> str:
    """Return an ignore-file line that means the same as a pattern.

    Every space in the glob is escaped, so none can be trimmed from the end of the line.
    A pattern that wrongly kept a trailing space then matches differently, rather than
    being trimmed back into the right one.

    Args:
        pattern: The pattern to write as a line.

    Returns:
        The line.
    """
    glob, negated, directory_only, anchored = pattern
    characters = iter(glob)
    escaped = ""

    for character in characters:
        if character == "\\":
            # Keep an escape as it is, along with the character it escapes.
            escaped += character + next(characters, "")
        elif character == " ":
            escaped += "\\ "
        else:
            escaped += character

    prefix = ("!" if negated else "") + ("/" if anchored else "")
    return prefix + escaped + ("/" if directory_only else "")


def list_files(root: Path, tree: list[str], lines: list[str]) -> list[str]:
    """Create a tree with an ignore-file, and return the files Git lists beneath it.

    Args:
        root: Path to the directory to create the tree in.
        tree: Files and directories to create, as `make_tree` takes them.
        lines: Lines to write to the ignore-file, named "ignore", in the root.

    Returns:
        The files Git lists, in order.
    """
    root.mkdir()
    make_tree(root, *tree)
    (root / "ignore").write_bytes("".join(f"{line}\n" for line in lines).encode())
    return git_list_files(root, "ignore")


def make_broken_symlink(path: Path) -> None:
    """Create a symlink to a target that doesn't exist.

    The symlink points to the sibling of `path` named by `symlink_target`. If that
    sibling already exists then the symlink won't be broken, and no error is raised.

    Args:
        path: Path to create the symlink at.

    Raises:
        FileExistsError: When `path` already exists.
    """
    path.symlink_to(symlink_target(path))


def make_directory(path: Path) -> None:
    """Create a directory.

    Args:
        path: Path to create the directory at.

    Raises:
        FileExistsError: When `path` already exists.
    """
    path.mkdir()


def make_fifo(path: Path) -> None:
    """Create a FIFO (a named pipe).

    Args:
        path: Path to create the FIFO at.

    Raises:
        AssertionError: When called on Windows, which can't create FIFOs.
        FileExistsError: When `path` already exists.
    """
    # `os.mkfifo` doesn't exist on Windows. This assertion convinces pyright that we
    # won't call it when we're running on Windows.
    assert sys.platform != "win32"

    os.mkfifo(path)


def make_file(path: Path) -> None:
    """Create an empty file.

    An existing file is truncated rather than raising `FileExistsError`.

    Args:
        path: Path to create the file at.
    """
    path.write_text("")


def make_junction(path: Path) -> None:
    """Create a Windows junction to a directory.

    A junction links to a directory much like a symlink does, but any user can create
    one without admin rights or Developer Mode.

    The directory is created as the sibling of `path` named by `symlink_target`.

    Args:
        path: Path to create the junction at.

    Raises:
        AssertionError: When called on any platform except Windows.
        FileExistsError: When `path` or its target sibling already exists.
    """
    # `_winapi` only exists on Windows. This assertion convinces Pyright that we can use
    # it.
    assert sys.platform == "win32"

    # Python has no public function for creating a junction, so we borrow the private
    # one that CPython's own tests use. It can be our little secret.
    import _winapi

    target = symlink_target(path)
    target.mkdir()
    _winapi.CreateJunction(os.fspath(target), os.fspath(path))


def make_nothing(path: Path) -> None:
    """Create nothing, leaving the path missing.

    A no-op, so that a missing path can be a test case alongside the other helpers.

    Args:
        path: Path to leave missing.
    """


def make_symlink_to_directory(path: Path) -> None:
    """Create a symlink to a directory.

    The directory is created as the sibling of `path` named by `symlink_target`.

    Args:
        path: Path to create the symlink at.

    Raises:
        FileExistsError: When `path` or its target sibling already exists.
    """
    target = symlink_target(path)
    target.mkdir()

    # Windows has distinct file and directory symlinks, and a link doesn't change its
    # kind to suit its target. Python would pick the right kind here anyway, since the
    # target already exists, but being explicit means we don't depend on that. Other
    # platforms ignore the flag.
    path.symlink_to(target, target_is_directory=True)


def make_symlink_to_file(path: Path) -> None:
    """Create a symlink to a file.

    The file is created as the sibling of `path` named by `symlink_target`. An existing
    file there is truncated rather than raising `FileExistsError`.

    Args:
        path: Path to create the symlink at.

    Raises:
        FileExistsError: When `path` already exists.
    """
    target = symlink_target(path)
    target.write_text("")

    # No `target_is_directory` here: file symlinks are the default on Windows, and other
    # platforms don't distinguish.
    path.symlink_to(target)


def make_tree(root: Path, *paths: str) -> None:
    """Create a tree of empty files and directories.

    Each path is relative to `root` and uses "/" as its separator on every operating
    system. A path ending with "/" is a directory, and anything else is an empty file.
    Missing parent directories are created.

    A path can't be absolute or contain "..", so nothing is created outside `root`.

    For example:

    ```python
    make_tree(root, "a/b.txt", "a/c/", "d.txt")
    ```

    Creates:

    ```
    root/
    ├── a/
    │   ├── b.txt
    │   └── c/
    └── d.txt
    ```

    An existing file is truncated rather than raising `FileExistsError`.

    Args:
        root: Path to the directory to create the tree in. Will be created if it doesn't
            exist, like any other missing parent.
        *paths: Paths of the files and directories to create, relative to `root`.

    Raises:
        OSError: When one path needs a file where another needs a directory (say, "a"
            and "a/b"). On Windows, this can be a misleading `PermissionError`.
        ValueError: When a path is absolute or contains "..".
    """
    for path in paths:
        # `root / path` would throw `root` away for an absolute path, and ".." would
        # climb out of it. Either could truncate a real file outside the test's
        # directory, so we refuse them.
        #
        # We check the path in the local operating system's own flavour, so that
        # Windows catches its drives ("C:"), shares ("//server/share") and "\"
        # separators too.
        relative = Path(path)
        if relative.anchor or ".." in relative.parts:
            raise ValueError(f"{path!r} would reach outside the root")

        target = root / relative

        if path.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            make_file(target)


def relative_paths(root: Path) -> list[str]:
    """Walk a directory and return every step's relative path, in order.

    Args:
        root: Path to the directory to walk.

    Returns:
        The relative path of every step.
    """
    return [step.relative_as_posix for step in Mosey().walk(root)]


def skip_if_windows_cannot_create(paths: list[str]) -> None:
    """Skip the test on Windows if Windows can't create any of the paths exactly.

    Windows refuses some names, and changes others ("a " becomes "a"), so a test that
    needs one is only run on Linux and macOS.

    Args:
        paths: Paths relative to a root, using "/" as their separator, as `make_tree`
            takes them.
    """
    if sys.platform != "win32":
        return

    for path in paths:
        if not windows_can_create(path):
            skip(f"Windows can't create {path!r}")


def symlink_target(path: Path) -> Path:
    """Return the path that a symlink made by these helpers will point to.

    The target will be a sibling of the symlink and named after it (say, "link.target"
    for "link"), so symlinks made in the same directory never share a target.

    Args:
        path: Path to the symlink.

    Returns:
        Path to the symlink's target.
    """
    return path.with_name(f"{path.name}.target")


def windows_can_create(path: str) -> bool:
    r"""Check if Windows can create every name in a path, exactly as written.

    Windows refuses a name holding a control character or any of `\ : * ? " < > |`, and
    drops a space or dot from the end of one, so `make_tree(root, "a ")` makes "a"
    instead. These rules come from Microsoft's documentation on naming files.

    Args:
        path: Path relative to a root, using "/" as its separator, as `make_tree` takes
            it.

    Returns:
        `True` if Windows can create every name in `path` exactly, otherwise `False`.
    """
    for name in path.split("/"):
        if name.endswith((" ", ".")):
            return False

        if any(ord(character) < 32 or character in '\\:*?"<>|' for character in name):
            return False

    return True
