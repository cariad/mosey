"""Helpers for comparing Mosey with Git.

Git's `ls-files` can list the files beneath a directory, leaving out the ones that its
ignore-files ignore, so tests use it to check what Mosey should yield. Git is only a
test oracle: it's never the reason for any of Mosey's behaviour.

The comparisons need Git 2.32 or later.
"""

import atexit
import os
import re
import subprocess
from functools import cache
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
from typing import Final

MINIMUM_VERSION: Final[tuple[int, int]] = (2, 32)
"""The oldest version of Git that the comparisons can use.

Git 2.32 added `GIT_CONFIG_GLOBAL`, which keeps the user's own Git settings out of the
comparisons.
"""

# Git waits forever to read an ignore-file that's a FIFO, so a mistake in a test could
# otherwise hang the whole run.
TIMEOUT: Final[float] = 10
"""Seconds to wait for any Git command before giving up."""


def git_environment() -> dict[str, str]:
    """Return the environment to run Git in.

    Git reads settings from environment variables and from files in the home directory,
    and the comparisons must not depend on who runs the tests or how. For example, Git
    runs hooks with `GIT_INDEX_FILE` set, which would make `ls-files` leave out every
    file that the hook's repository tracks.

    Returns:
        This process's environment without its own Git variables, and set up so that
        Git reads no settings except the repository's.
    """
    workspace = git_workspace()

    # On Windows, `os.environ` upper-cases every name, so this catches every spelling.
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_") and name != "XDG_CONFIG_HOME"
    }

    environment["GIT_CONFIG_GLOBAL"] = os.fspath(workspace / "empty")
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["HOME"] = os.fspath(workspace / "home")
    return environment


def git_list_files(root: Path, ignore_filename: str) -> list[str]:
    """Return the files beneath a directory that Git doesn't ignore.

    Git reads the ignore-file in `root` and in every directory beneath it.

    Each path is relative to `root` and uses "/" as its separator on every operating
    system, like `Step.relative_as_posix`. Git lists them in ascending byte order, which
    is also Mosey's walk order, so the two lists compare directly.

    Args:
        root: Path to the directory to list.
        ignore_filename: Name of the ignore-file to read in each directory.

    Returns:
        The relative path of every file that Git doesn't ignore, in Git's order.

    Raises:
        RuntimeError: When Git is older than `MINIMUM_VERSION` or isn't installed,
            fails, or prints anything to stderr.
        subprocess.TimeoutExpired: When Git takes too long.
        ValueError: When anything beneath `root` is named ".git", in any casing.
    """
    # Git always leaves out anything named ".git", and lists a directory holding a
    # repository as a single entry, but Mosey never skips anything by name. So a tree
    # like that can't be compared. With `core.ignorecase` off, Git only leaves out an
    # exact ".git", but we refuse every casing to be safe.
    #
    # `os.walk` doesn't follow symlinks, but it does report their names.
    for directory, directories, files in os.walk(root):
        for name in (*directories, *files):
            if name.lower() == ".git":
                path = os.path.join(directory, name)
                raise ValueError(f"Can't compare a tree holding {path!r} with Git")

    # The repository is empty and outside the tree, so every file in the tree is one of
    # the "others" that it doesn't track.
    output = run_git(
        f"--git-dir={git_repository()}",
        "--work-tree=.",
        "ls-files",
        "--others",
        f"--exclude-per-directory={ignore_filename}",
        "-z",
        cwd=root,
    )

    # `-z` gives every name exactly, rather than quoting unusual ones, and ends each one
    # with a zero byte. So the last item after splitting is empty.
    return [os.fsdecode(path) for path in output.split(b"\0")[:-1]]


@cache
def git_repository() -> Path:
    """Return the path to a bare repository for the comparisons.

    The repository is created on the first call and shared by every call after it.
    Listing files never changes it.

    Returns:
        Path to the repository.

    Raises:
        RuntimeError: When Git is older than `MINIMUM_VERSION`, or isn't installed.
    """
    if not has_git():
        minimum = f"{MINIMUM_VERSION[0]}.{MINIMUM_VERSION[1]}"
        found = git_version() or "no Git"
        raise RuntimeError(f"Need Git {minimum} or later, but found {found}")

    workspace = git_workspace()
    path = workspace / "repository"

    # `--template=` leaves out the usual sample hooks and `info/exclude` file.
    # `--quiet` hides a hint about naming the default branch, which would otherwise
    # count as an error.
    run_git("init", "--bare", "--quiet", "--template=", os.fspath(path))

    settings = [
        # `git init` turns this on when the file system ignores case, like macOS's
        # does by default, and then patterns ignore case too.
        ("core.ignorecase", "false"),
        # On macOS, `git init` turns this on, and then Git composes the names it lists,
        # so "e" followed by a combining accent comes back as a single "é".
        ("core.precomposeunicode", "false"),
        # `ls-files` only reads this file with `--exclude-standard`, which we don't
        # pass, but just in case.
        ("core.excludesFile", os.fspath(workspace / "empty")),
        # These caches are off unless something turns them on, and nothing else
        # configures this repository, but a listing should never depend on an earlier
        # one.
        ("core.fscache", "false"),
        ("core.fsmonitor", "false"),
        ("core.untrackedCache", "false"),
    ]

    for name, value in settings:
        run_git(f"--git-dir={path}", "config", name, value)

    return path


@cache
def git_version() -> str | None:
    """Return the version that Git reports, or `None` if Git isn't installed.

    Returns:
        What `git --version` prints (for example, "git version 2.54.0"), or `None` if
        Git isn't installed.
    """
    try:
        return run_git("--version").decode().strip()
    except FileNotFoundError:
        return None


@cache
def git_workspace() -> Path:
    """Return a temporary directory for Git's repository and settings.

    The directory is created on the first call and deleted when Python exits. It holds
    an empty home directory, "home", and an empty file, "empty".

    Returns:
        Path to the directory.
    """
    path = Path(mkdtemp(prefix="mosey-git-"))
    atexit.register(rmtree, path)

    (path / "empty").write_bytes(b"")
    (path / "home").mkdir()
    return path


def has_git(minimum: tuple[int, int] = MINIMUM_VERSION) -> bool:
    """Check if Git is installed.

    Args:
        minimum: The oldest version to accept, as the major and minor values.

    Returns:
        `True` if Git `minimum` or later is installed, otherwise `False`.
    """
    version = git_version()

    if version is None:
        return False

    # Git for Windows and Apple add to the version (say, "git version 2.54.0.windows.1"
    # or "git version 2.54.0 (Apple Git-157)"), so we only read the first two numbers.
    match = re.match(r"git version (\d+)\.(\d+)", version)
    return match is not None and (int(match[1]), int(match[2])) >= minimum


def run_git(*arguments: str, cwd: Path | None = None) -> bytes:
    """Run Git and return what it prints to stdout.

    Args:
        *arguments: Arguments to pass to Git.
        cwd: Path to the directory to run Git in, or `None` for the current one.

    Returns:
        What Git prints to stdout.

    Raises:
        FileNotFoundError: When Git isn't installed.
        RuntimeError: When Git fails, or prints anything to stderr.
        subprocess.TimeoutExpired: When Git takes longer than `TIMEOUT`.
    """
    completed = subprocess.run(
        ["git", *arguments],
        capture_output=True,
        check=False,
        cwd=cwd,
        env=git_environment(),
        timeout=TIMEOUT,
    )

    # Git exits with 0 after some warnings, for example when it can't read an
    # ignore-file, so anything on stderr counts as a failure too.
    if completed.returncode or completed.stderr:
        stderr = completed.stderr.decode(errors="replace")
        raise RuntimeError(f"Git exited with {completed.returncode}: {stderr}")

    return completed.stdout
