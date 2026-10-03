"""Random trees with ignore-files, for comparing Mosey's walk with Git's listing.

`random_tree` makes a tree from a seed and an index, and `build` creates it. The same
seed, index and options make the same tree on every operating system, and on Python 3.11
to 3.14, so a tree that fails in CI can be rebuilt anywhere. Python only promises that
`random()` gives the same numbers from the same seed, so a later version of Python might
make different trees.

A tree only holds what Linux, macOS and Windows can all create, and what Mosey and Git
read the same way:

- Every name is ASCII, Windows can create it, and it isn't a name that Windows reserves
  (like "aux"). No two names in one directory differ only in case.
- Nothing is named ".git", and nothing but an ignore-file (or a directory, if asked for)
  is named "ignore" in any casing. An ignore-file is never a symlink.
- No line holds a zero byte, and lines that Git reads differently are drawn again (see
  `differences`).

Everything the tests need is exported by this package, so import from here rather than
from the submodules:

- `tree` makes a whole tree, and builds it.
- `draft` holds a tree's files, directories and symlinks while it's being made.
- `ignore_files` chooses which directories get an ignore-file, and writes their bytes.
- `lines` makes each kind of line, from the escapes, brackets and wildcards in `pieces`.
- `differences` checks for the lines that Git reads differently.
"""

from tests.random_trees.tree import RandomTree, build, random_tree

__all__ = [
    "RandomTree",
    "build",
    "random_tree",
]
