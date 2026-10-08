"""Functions for working with ignore-file rules.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import re
from collections.abc import Callable
from typing import TypeAlias

from .globs import SPECIAL, translate_glob
from .patterns import parse_pattern

Fullmatch: TypeAlias = Callable[
    [
        str,
    ],
    re.Match[str] | None,
]
"""A compiled regular expression's `fullmatch`."""

Line: TypeAlias = tuple[
    str,
    bool,
    bool,
    int,
]
"""A line of an ignore-file, ready to go into a matcher.

The elements are:

1. The name or path the line matches if it's plain, or else its glob's regular
   expression.
2. Whether the line is plain: `True` if its glob holds no "*", "?", "[" or backslash,
   so it only matches itself.
3. Whether the line is anchored: `True` if it matches paths relative to the ignore-
   file's directory, `False` if it matches names at any depth beneath it.
4. The line's outcome (see `Matcher`).
"""

Matcher: TypeAlias = tuple[
    dict[str, int],
    Fullmatch | None,
    tuple[int, ...],
    dict[str, int],
    Fullmatch | None,
    tuple[int, ...],
]
"""One ignore-file's lines, compiled to judge one kind of entry.

Each line has an outcome: a number that grows down the file, and is odd if the line
ignores what it matches, or even if it's negated. So of the lines that match an entry,
the one with the biggest outcome decides, and 0 means none does.

The elements are:

1. The plain unanchored lines: each name, and the outcome of the last line for it.
2. The `fullmatch` of one regular expression for every other unanchored line, or
   `None` if there are none.
3. The outcome of each line in that expression, by the number of the group that follows
   it.
4. The plain anchored lines: each path, and the outcome of the last line for it.
5. The `fullmatch` of one regular expression for every other anchored line, or `None`
   if there are none.
6. The outcome of each line in that expression, by the number of the group that follows
   it.
"""

Layer: TypeAlias = tuple[
    str,
    Matcher,
    Matcher,
]
"""One ignore-file's rules, or the patterns given in code, and the directory they apply
beneath.

The elements are:

1. The ignore-file's directory relative to the walk's root, with a "/" after each name:
   "" for the root, or "a/b/" for "root/a/b". Patterns given in code apply beneath the
   root, so theirs is always "".
2. The matcher for files and symlinks, which leaves out the lines that only match
   directories.
3. The matcher for directories.
"""

Layers: TypeAlias = tuple[Layer, ...]
"""Layers in the order they judge an entry. The first with a matching line decides."""


def compile_rules(
    lines: list[str],
) -> tuple[Matcher, Matcher] | None:
    """Return an ignore-file's lines compiled into matchers.

    A line is dropped when nothing is left of it to match, as with "!", or when its glob
    is malformed, as with "[a". So it matches nothing, and never raises.

    Args:
        lines: The lines to compile.

    Returns:
        The matcher for files and symlinks, and the matcher for directories. `None` if
        no line is left.
    """
    # NOTE: Keeping separate matchers for files and for directories, rather than one
    # NOTE: matcher whose lines check the entry's type as they match, makes judging an
    # NOTE: entry take 9-18% less time on Python 3.11 to 3.14 on arm64 macOS, though
    # NOTE: one matcher compiles a large ignore-file about a third faster.
    file_lines: list[Line] = []
    directory_lines: list[Line] = []

    # How many lines have been kept so far.
    position = 0

    for line in lines:
        pattern = parse_pattern(line)

        if pattern is None:
            continue

        glob, negated, directory_only, anchored = pattern

        # A plain glob only matches itself, so it's looked up rather than translated.
        plain = SPECIAL.search(glob) is None
        text = glob if plain else translate_glob(glob)

        if text is None:
            continue

        position += 1
        kept = (text, plain, anchored, position * 2 + (not negated))
        directory_lines.append(kept)

        # A line ending with "/" only matches directories, so files and symlinks never
        # need to try it.
        if not directory_only:
            file_lines.append(kept)

    if not position:
        return None

    return compile_matcher(file_lines), compile_matcher(directory_lines)


def compile_matcher(
    lines: list[Line],
) -> Matcher:
    """Return lines compiled into a matcher.

    Args:
        lines: The lines, in the order the ignore-file holds them.

    Returns:
        The matcher.
    """
    names: dict[str, int] = {}
    name_sources: list[tuple[str, int]] = []

    paths: dict[str, int] = {}
    path_sources: list[tuple[str, int]] = []

    for text, plain, anchored, outcome in lines:
        if plain:
            # A later line for the same name or path replaces the earlier one.
            (paths if anchored else names)[text] = outcome
        elif anchored:
            path_sources.append((text, outcome))
        else:
            name_sources.append((text, outcome))

    return (
        names,
        *join_sources(name_sources),
        paths,
        *join_sources(path_sources),
    )


def compile_root_layers(lines: list[str]) -> Layers:
    """Return patterns given in code compiled into layers.

    The patterns are tied to the walk's root, like lines of an ignore-file there, so
    they make one layer, with the prefix "".

    Args:
        lines: The patterns to compile, lowest rank first, so the last one that
            matches decides, as in an ignore-file.

    Returns:
        The layer, or no layers if there are no patterns.
    """
    rules = compile_rules(lines)
    return () if rules is None else (("", *rules),)


def join_sources(
    sources: list[tuple[str, int]],
) -> tuple[Fullmatch | None, tuple[int, ...]]:
    """Return regular expressions joined into one, and the outcome of each.

    Args:
        sources: Each regular expression and its outcome, in the order the ignore-file
            holds them.

    Returns:
        The joined regular expression's `fullmatch`, and each outcome by the number of
        the group that follows its regular expression. `None` and no outcomes if there
        are no regular expressions.
    """
    if not sources:
        return None, ()

    # NOTE: An empty group after each regular expression, rather than a group around
    # NOTE: it, lets Python skip one at once when it starts with a plain character that
    # NOTE: the name or path doesn't. A group around each made judging an entry take
    # NOTE: 6-15% longer on Python 3.11 to 3.14 on arm64 macOS.

    # The joined expression tries each regular expression in turn, and stops at the
    # first that matches. So the last line goes first, and the empty group after it
    # says which one matched. A translated glob holds no capturing group of its own, so
    # the empty groups are numbered 1, 2, 3 and so on.
    last_first = sources[::-1]
    joined = "|".join(f"{source}()" for source, _ in last_first)
    return re.compile(joined).fullmatch, (0, *(outcome for _, outcome in last_first))


def is_ignored(layers: Layers, name: str, relative: str, is_dir: bool) -> bool:
    """Check if a directory entry is ignored.

    The first layer with a line that matches the entry decides, and within it, the last
    line that matches.

    Ignore-files are documented at https://cariad.github.io/mosey/ignore-files/, and
    default and overriding patterns at
    https://cariad.github.io/mosey/default-and-overriding-patterns/.

    Args:
        layers: The layers that judge the entry, in order: the patterns given in code
            that overrule the ignore-files, then the layers from the ignore-files in the
            directory that holds the entry and every directory above it, deepest first,
            then the patterns given in code that the ignore-files overrule.
        name: The entry's name.
        relative: The entry's path relative to the walk's root, with "/" between names.
        is_dir: Whether the entry is a directory. A symlink isn't, even one to a
            directory.

    Returns:
        `True` if the entry is ignored, otherwise `False`.
    """
    for prefix, file_matcher, directory_matcher in layers:
        names, name_match, name_outcomes, paths, path_match, path_outcomes = (
            directory_matcher if is_dir else file_matcher
        )

        # Of the lines that match, the one with the biggest outcome decides. Every
        # regular expression is followed by a group, so a match always has a
        # `lastindex`; the `or 0` is only there for the type checker.
        outcome = names.get(name, 0)

        if name_match is not None and (match := name_match(name)):
            other = name_outcomes[match.lastindex or 0]

            if other > outcome:
                outcome = other

        if paths or path_match is not None:
            # An anchored line matches the entry's path from the layer's directory.
            path = relative[len(prefix) :]
            other = paths.get(path, 0)

            if other > outcome:
                outcome = other

            if path_match is not None and (match := path_match(path)):
                other = path_outcomes[match.lastindex or 0]

                if other > outcome:
                    outcome = other

        if outcome:
            return outcome % 2 == 1

    return False
