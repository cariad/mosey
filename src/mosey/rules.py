"""Functions for working with ignore-file rules.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import re
from collections.abc import Callable
from typing import TypeAlias

from .globs import translate_glob
from .patterns import parse_pattern

Rule: TypeAlias = tuple[Callable[[str], re.Match[str] | None], bool, bool]
"""A line of an ignore-file, compiled.

The elements are:

1. The function that matches a whole name or path: the compiled glob's `fullmatch`.
2. Whether the rule is negated: `True` if it re-includes what it matches rather than
   ignoring it.
3. Whether the rule is anchored: `True` if it matches paths relative to the ignore-
   file's directory, `False` if it matches names at any depth beneath it.
"""

Rules: TypeAlias = tuple[Rule, ...]
"""Rules from one ignore-file, last line first."""

Layer: TypeAlias = tuple[str, Rules, Rules]
"""One ignore-file's rules, and the directory they apply beneath.

The elements are:

1. The ignore-file's directory relative to the walk's root, with a "/" after each name:
   "" for the root, or "a/b/" for "root/a/b".
2. The rules for files and symlinks, which leave out the lines that only match
   directories.
3. The rules for directories.
"""

Layers: TypeAlias = tuple[Layer, ...]
"""The layers that apply to a directory's entries, deepest first."""


def compile_rules(lines: list[str]) -> tuple[Rules, Rules] | None:
    """Return an ignore-file's lines compiled into rules.

    A line is dropped when nothing is left of it to match, as with "!", or when its glob
    is malformed, as with "[a". So it matches nothing, and never raises.

    Args:
        lines: The lines to compile.

    Returns:
        The rules for files and symlinks, and the rules for directories, each with the
        last line first. `None` if no line is left.
    """
    # NOTE: Keeping separate rules for files and for directories, rather than one set of
    # NOTE: rules that each say whether they only match directories, makes judging an
    # NOTE: entry against a 96-line file's rules take about 2.6-3.1 microseconds rather
    # NOTE: than 3.2-4.2 on Python 3.11 to 3.14 on arm64 macOS.
    file_rules: list[Rule] = []
    directory_rules: list[Rule] = []

    # The last line that matches decides, so we put the last line first, and
    # `is_ignored` can stop at the first rule that matches.
    for line in reversed(lines):
        pattern = parse_pattern(line)

        if pattern is None:
            continue

        glob, negated, directory_only, anchored = pattern
        source = translate_glob(glob)

        if source is None:
            continue

        rule = (re.compile(source).fullmatch, negated, anchored)
        directory_rules.append(rule)

        # A line ending with "/" only matches directories, so files and symlinks never
        # need to try it.
        if not directory_only:
            file_rules.append(rule)

    if not directory_rules:
        return None

    return (tuple(file_rules), tuple(directory_rules))


def is_ignored(layers: Layers, name: str, relative: str, is_dir: bool) -> bool:
    """Check if a directory entry is ignored.

    The deepest ignore-file with a line that matches the entry decides, and within it,
    the last line that matches. A line starting with "!" keeps what it matches, and an
    entry that no line matches is kept too. A line ending with "/" only matches
    directories. A line with any other "/" matches the entry's path from its
    ignore-file's directory, and any other line matches the entry's name, at any depth.
    For example, with these ignore-files:

    ```text
    Ignore-file   Lines
    "ignore"      "*.log", "build/"
    "sub/ignore"  "!keep.log", "/top"
    ```

    ```text
    Entry                 Ignored  Why
    "a.log"               yes      "*.log"
    "sub/a.log"           yes      "*.log", since no line in "sub/ignore" matches
    "sub/keep.log"        no       "!keep.log", in the deeper ignore-file
    "sub/top"             yes      "/top"
    "sub/x/top"           no       "/top" only matches "top" beside "sub/ignore"
    "build", a directory  yes      "build/"
    "build", a file       no       "build/" only matches directories
    ```

    Args:
        layers: The layers from the ignore-files in the entry's directory and every
            directory above it, deepest first.
        name: The entry's name.
        relative: The entry's path relative to the walk's root, with "/" between names.
        is_dir: Whether the entry is a directory. A symlink isn't, even one to a
            directory.

    Returns:
        `True` if the entry is ignored, otherwise `False`.
    """
    for prefix, file_rules, directory_rules in layers:
        # An anchored rule matches the entry's path from the layer's directory. We cut
        # that path out once per layer, rather than once for every anchored rule.
        path = relative[len(prefix) :]

        for fullmatch, negated, anchored in directory_rules if is_dir else file_rules:
            if fullmatch(path if anchored else name):
                return not negated

    return False
