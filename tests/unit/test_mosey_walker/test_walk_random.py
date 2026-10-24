"""Unit tests that compare the `MoseyWalker.walk` function with Git on random trees."""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pytest import fail

from tests.file_system_helpers import build_walker, relative_paths, symlinks_allowed
from tests.git_oracle import git_list_files, git_repository
from tests.markers import needs_git
from tests.random_trees import RandomTree, build, random_tree

SEED = f"{sys.platform}-{sys.version_info.major}.{sys.version_info.minor}"
"""The seed that every random tree is made from, along with its index.

Each operating system and version of Python has its own, so every CI job compares
different trees. Any of them can be made again anywhere, from its seed, index and
options, which a failure prints as a call to `random_tree`.
"""

TREES = 300
"""How many random trees to compare."""

PATTERNS_SEED = f"{SEED}/patterns"
"""The seed that every random tree with patterns is made from, along with its index.

Like `SEED`, each operating system and version of Python has its own. It differs from
`SEED`, so the trees with patterns aren't the trees without them.
"""

TREES_WITH_PATTERNS = 100
"""How many random trees with patterns to compare."""


def check(
    made: str,
    case: RandomTree,
    root: Path,
    listed: list[str],
) -> None:
    """Check that a walk of a random tree yields what Git lists, symlinks and all.

    The tree is walked twice: once as it is, when each step must say whether it's one
    of the tree's symlinks, and once ignoring symlinks, when the walk must yield what
    Git lists apart from them.

    Args:
        made: The call that makes the tree.
        case: The tree.
        root: Path to the tree.
        listed: What Git lists.
    """
    try:
        steps = list(build_walker(case.ignore_filename, case.patterns).walk(root))

        ignoring = relative_paths(
            root,
            case.ignore_filename,
            case.patterns,
            ignore_symlinks=True,
        )

    except Exception as error:
        error.add_note(f"{made} made this tree:\n{case!r}")
        raise

    walked = [step.relative_as_posix for step in steps]

    if walked != listed:
        fail(describe(made, case, listed, walked), pytrace=False)

    flagged = [step.relative_as_posix for step in steps if step.is_symlink]
    symlinks = [path for path in walked if path in case.symlinks]

    if flagged != symlinks:
        fail(
            f"{made} flags symlinks differently:\n{case!r}\n"
            f"Flagged: {flagged!r}\nSymlinks: {symlinks!r}",
            pytrace=False,
        )

    # Git never lists anything beneath a symlink, so leaving out the symlinks it lists
    # leaves what a walk that ignores them yields.
    kept = [path for path in listed if path not in case.symlinks]

    if ignoring != kept:
        fail(
            describe(
                made,
                case,
                kept,
                ignoring,
                ignore_symlinks=True,
            ),
            pytrace=False,
        )


def describe(
    made: str,
    case: RandomTree,
    listed: list[str],
    walked: list[str],
    ignore_symlinks: bool = False,
) -> str:
    """Describe a tree that Git and the walk list differently.

    Args:
        made: The call that makes the tree.
        case: The tree.
        listed: What Git lists, without the symlinks when the walk ignores them.
        walked: What the walk yields.
        ignore_symlinks: Whether the walk ignores symlinks.

    Returns:
        The description.
    """
    only_listed = [path for path in listed if path not in walked]
    only_walked = [path for path in walked if path not in listed]
    ignoring = ", ignoring symlinks" if ignore_symlinks else ""

    return "\n".join(
        [
            f"{made} lists differently{ignoring}:",
            repr(case),
            f"Only Git lists: {only_listed!r}",
            f"Only the walk yields: {only_walked!r}",
            f"Git lists: {listed!r}",
            f"The walk yields: {walked!r}",
        ]
    )


@needs_git
def test_walk__random_trees(tmp_path: Path) -> None:
    """Git lists exactly the files that the walk yields, in every random tree."""
    # GitHub Actions' runners can make symlinks, so CI fails rather than leave them out,
    # as `needs_symlinks` does.
    symlinks = symlinks_allowed()

    # Git for Windows warns about a directory named like the ignore-file, and the Git
    # helper counts a warning as a failure.
    ignore_directories = sys.platform != "win32"

    cases = [
        random_tree(
            SEED,
            index,
            symlinks=symlinks,
            ignore_directories=ignore_directories,
            patterns=False,
        )
        for index in range(TREES)
    ]

    for index, case in enumerate(cases):
        build(tmp_path / str(index), case)

    # A tree's ignore-files only apply inside its own folder, so one listing of every
    # tree gives each tree's listing, with one run of Git rather than one per tree. If
    # Git fails, its message names the path, which starts with the tree's index.
    listings: dict[str, list[str]] = {}

    for path in git_list_files(tmp_path, "ignore"):
        index, _, relative = path.partition("/")
        listings.setdefault(index, []).append(relative)

    for index, case in enumerate(cases):
        made = (
            f"random_tree({SEED!r}, {index}, symlinks={symlinks}, "
            f"ignore_directories={ignore_directories}, patterns=False)"
        )

        check(
            made,
            case,
            tmp_path / str(index),
            listings.get(str(index), []),
        )


@needs_git
def test_walk__random_trees_with_patterns(tmp_path: Path) -> None:
    """Git lists exactly what the walk yields, in every random tree with patterns."""
    # Symlinks, and directories named like the ignore-file, as in
    # `test_walk__random_trees` and for the same reasons.
    symlinks = symlinks_allowed()
    ignore_directories = sys.platform != "win32"

    cases = [
        random_tree(
            PATTERNS_SEED,
            index,
            symlinks=symlinks,
            ignore_directories=ignore_directories,
            patterns=True,
        )
        for index in range(TREES_WITH_PATTERNS)
    ]

    for index, case in enumerate(cases):
        build(tmp_path / str(index), case)

    # The patterns are tied to the directory that Git lists, so one listing of every
    # tree, as in `test_walk__random_trees`, would tie them to the wrong directory. So
    # each tree gets a run of Git of its own, and the runs are independent, so they run
    # at the same time. The repository is made first, so they never race to make it.
    git_repository()

    with ThreadPoolExecutor() as executor:
        listings = [
            executor.submit(
                git_list_files,
                tmp_path / str(index),
                case.ignore_filename,
                case.patterns,
            )
            for index, case in enumerate(cases)
        ]

    for index, (case, listing) in enumerate(zip(cases, listings, strict=True)):
        made = (
            f"random_tree({PATTERNS_SEED!r}, {index}, symlinks={symlinks}, "
            f"ignore_directories={ignore_directories}, patterns=True)"
        )

        try:
            listed = listing.result()
        except Exception as error:
            error.add_note(f"{made} made this tree:\n{case!r}")
            raise

        check(
            made,
            case,
            tmp_path / str(index),
            listed,
        )
