"""Making a whole random tree, and building it."""

import random
from pathlib import Path
from typing import NamedTuple

from tests.file_system_helpers import make_tree, write_ignore_files
from tests.random_trees.draft import Draft
from tests.random_trees.ignore_files import add_ignore_files, encode


class RandomTree(NamedTuple):
    """A random tree: its ignore-files, its other files and directories, and symlinks.

    Its `repr` is valid Python, so a tree printed in a log can be pasted into `build`.
    """

    ignore_files: dict[str, bytes]
    """Each ignore-file's exact bytes, by directory ("" for the root).

    Every ignore-file is named "ignore".
    """

    tree: list[str]
    """The other files and directories, as `make_tree` takes them."""

    symlinks: dict[str, str]
    """Each symlink's path, and the path of the file or directory it points to."""


def random_tree(
    seed: str,
    index: int,
    *,
    symlinks: bool,
    ignore_directories: bool,
) -> RandomTree:
    """Make a random tree.

    The same arguments make the same tree on every operating system, and on Python 3.11
    to 3.14. Python only promises that `random()` gives the same numbers from the same
    seed, so a later version of Python might make different trees.

    Args:
        seed: The seed.
        index: The tree's index.
        symlinks: Whether the tree may hold symlinks.
        ignore_directories: Whether the tree may hold a directory named like the
            ignore-file.

    Returns:
        The tree.
    """
    draft = Draft(random.Random(f"{seed}/{index}"))
    draft.add_entries()

    if symlinks and draft.rng.random() < 0.3:
        draft.add_symlinks()

    if ignore_directories and draft.rng.random() < 0.3:
        draft.add_ignore_directory()

    add_ignore_files(draft)

    return RandomTree(
        ignore_files={
            holder: encode(draft.rng, lines) for holder, lines in draft.lines.items()
        },
        tree=sorted([*(d + "/" for d in draft.directories[1:]), *draft.files]),
        symlinks=draft.symlinks,
    )


def build(root: Path, case: RandomTree) -> None:
    """Build a random tree.

    Args:
        root: Path to the directory to build it in. It's created if it's missing.
        case: The tree.
    """
    make_tree(root, *case.tree)
    write_ignore_files(root, case.ignore_files)

    for path, target in case.symlinks.items():
        # The target is relative to the symlink's own directory, so the tree can move.
        relative = Path(*[".."] * path.count("/"), *target.split("/"))
        directory = f"{target}/" in case.tree
        (root / path).symlink_to(relative, target_is_directory=directory)
