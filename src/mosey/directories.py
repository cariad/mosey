"""Functions for working with directories.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import os

from .candidate import Candidate
from .paths import sort_key


def list_candidates(directory: str) -> list[Candidate]:
    """List a directory's candidates in Git's order.

    Args:
        directory: Path to the directory to list.

    Returns:
        The directory's candidates, sorted into Git's order. Only directories, files
        and symlinks are candidates. Anything else, or anything that can't be
        inspected, is left out, just as Git leaves it out.

        Unlike Git, we never leave anything out by its name, not even ".git". Which
        names to skip is for ignore-files to decide, not this function.

        Each name is exactly as the file system stores it, which on macOS isn't always
        how Git spells or orders it.

    Raises:
        OSError: When the directory can't be listed.
    """
    candidates: list[Candidate] = []

    # We read the whole listing and close the directory before returning.
    #
    # Sorting needs the whole listing anyway, and it means the walk never holds a
    # directory open longer than it absolutely needs to. A walk that's abandoned or
    # fails leaves nothing open.
    with os.scandir(directory) as entries:
        # We don't follow symlinks, so a symlink is never a directory. Its candidate is
        # always a file, whatever it points to, and the walk never goes into it. That's
        # how Git sees symlinks, too.
        #
        # Windows also has junctions, which link to a directory much like a symlink
        # does. Git doesn't count a junction as a symlink, though -- it treats it as a
        # real directory and walks into it. Python agrees, so `is_dir` is True for a
        # junction and we walk into it too. Don't "fix" this; it would break consistency
        # with Git.
        for entry in entries:
            # Git leaves out ".git" at this point, before it even checks the type,
            # because that's where Git keeps its own data. With `core.ignorecase` set,
            # as it usually is on macOS and Windows, it leaves out ".GIT" and ".Git"
            # too.
            #
            # We intentionally break from Git here. Mosey knows nothing about any tool's
            # directories, Git's included, so it never skips anything by name. That'll
            # be up to ignore-files. Don't "fix" this; it would bake in a rule that
            # users can't undo.
            #
            # Git only lists directories, files and symlinks. It skips anything else,
            # like FIFOs, sockets and devices, so we do too. We check here, while each
            # `DirEntry` has its type cached, rather than calling `lstat` later.
            #
            # These checks only touch the disk when the file system doesn't record each
            # object's type in the listing, as some network file systems don't. Then
            # the first check calls `lstat` (and the rest reuse its result), which can
            # fail -- say, when we're allowed to read the directory's names but not to
            # search it.
            #
            # Git skips an object whose type it can't find and carries on with the rest,
            # so we do too. Python raises `OSError` for most failures, but an object
            # that vanished since the listing is reported as not a directory, file or
            # symlink, so the type check skips that too.
            try:
                # Files are usually the most common type, so we check for them first.
                # Then a file costs one check rather than two. Listing 2,000 files and
                # 100 directories got 3% to 6% faster on Python 3.11 to 3.14 on arm64
                # macOS.
                if entry.is_file(follow_symlinks=False):
                    is_dir = False
                elif entry.is_dir(follow_symlinks=False):
                    is_dir = True
                elif entry.is_symlink():
                    is_dir = False
                else:
                    continue
            except OSError:  # pragma: no cover
                # Every file system in our CI matrix records types, so we can't reach
                # this for real in our current tests. Maybe one day!
                #
                # For now we skip the object silently, as Git does. We *could* raise or
                # collect this error instead, but we'll think about that another day.
                continue

            # We keep each name exactly as the file system stores it, even where Git
            # wouldn't.
            #
            # macOS can store an accented letter "decomposed" -- as a letter then a
            # combining accent: "é" as "e" (0x65) then U+0301 (0xCC 0x81), rather than
            # as U+00E9 (0xC3 0xA9). HFS+ always stores names that way, and APFS keeps
            # whichever form a name was created with.
            #
            # `git init` and `git clone` on macOS turn on `core.precomposeunicode`, and
            # then Git reports decomposed names as composed. That changes the order too:
            # "e" then U+0301 sorts before "f", but U+00E9 sorts after it. Where the
            # setting is off or missing, Git reports names as stored, just as we do.
            #
            # When ignore-files arrive, note that a composed pattern won't match a
            # decomposed name here, though it would in Git.
            candidates.append((entry.name, is_dir))

    candidates.sort(key=sort_key)
    return candidates
