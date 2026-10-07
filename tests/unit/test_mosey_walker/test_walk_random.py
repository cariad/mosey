"""Unit tests that compare the `MoseyWalker.walk` function with Git on random trees."""

import sys
from pathlib import Path

from pytest import fail

from tests.file_system_helpers import relative_paths, symlinks_allowed
from tests.git_oracle import git_list_files
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


def describe(made: str, case: RandomTree, listed: list[str], walked: list[str]) -> str:
    """Describe a tree that Git and the walk list differently.

    Args:
        made: The call that makes the tree.
        case: The tree.
        listed: What Git lists.
        walked: What the walk yields.

    Returns:
        The description.
    """
    only_listed = [path for path in listed if path not in walked]
    only_walked = [path for path in walked if path not in listed]

    return "\n".join(
        [
            f"{made} lists differently:",
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
            f"ignore_directories={ignore_directories})"
        )

        root = tmp_path / str(index)
        listed = listings.get(str(index), [])

        try:
            walked = relative_paths(root, "ignore")
        except Exception as error:
            error.add_note(f"{made} made this tree:\n{case!r}")
            raise

        if walked != listed:
            fail(describe(made, case, listed, walked), pytrace=False)
