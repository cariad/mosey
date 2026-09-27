"""Functions for working with ignore-file patterns.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

from typing import TypeAlias

# NOTE: `Pattern` is a plain tuple rather than a named tuple because a tuple literal is
# NOTE: far cheaper to build. Parsing a 96-line file takes about 9-11 microseconds
# NOTE: rather than 16-21 on Python 3.11 to 3.14 on arm64 macOS.
Pattern: TypeAlias = tuple[str, bool, bool, bool]
"""A line of an ignore-file, parsed.

The elements are:

1. The glob: what's left of the line to match against. Backslashes are kept, so the glob
   still says which characters were escaped.
2. Whether the pattern is negated: `True` if it re-includes what it matches rather than
   ignoring it.
3. Whether the pattern matches only directories.
4. Whether the pattern is anchored: `True` if it matches paths relative to the ignore-
   file's directory, `False` if it matches names at any depth beneath it.
"""


def parse_pattern(text: str) -> Pattern | None:
    r"""Return a line of an ignore-file parsed into a pattern.

    Trailing spaces are removed, unless a backslash escapes one. Then a "!" at the start
    negates the pattern, a "/" at the end means it only matches directories, and a "/"
    anywhere else anchors it. One "/" at the start is removed:

    ```text
    Line      Glob    Negated  Directories only  Anchored
    "a  "     "a"     no       no                no
    "a\  "    "a\ "   no       no                no
    "!a"      "a"     yes      no                no
    "a/"      "a"     no       yes               no
    "/a"      "a"     no       no                yes
    "a/b"     "a/b"   no       no                yes
    ```

    Everything else stays in the glob exactly as written. Nothing is tidied up, so lines
    like "./a" and "a//b" parse, but can never match a path.

    Args:
        text: The line to parse.

    Returns:
        The pattern, or `None` if nothing is left of the line to match, as with "!" or
        "/".
    """
    # Trailing spaces are invisible and easy to leave behind by accident, so we remove
    # them. Only spaces, though: a filename can end with other whitespace.
    pattern = text.rstrip(" ")

    if len(pattern) != len(text):
        # To keep a trailing space, escape it with a backslash: "a\ " matches a name
        # ending with a space. Backslashes escape each other in pairs, so the space is
        # only escaped when an odd number of them come right before it. Then we put that
        # one space back, and any after it stay removed.
        backslashes = len(pattern) - len(pattern.rstrip("\\"))

        if backslashes % 2:
            pattern = text[: len(pattern) + 1]

    # Only a "!" at the very start negates, so " !a" and "\!a" are patterns for names
    # holding a "!". The backslash stays in the glob, which reads it as an escape.
    #
    # NOTE: Checking the first and last characters by index rather than with
    # NOTE: `startswith` and `endswith` makes this function 13-20% faster on Python 3.11
    # NOTE: and 3.12 on arm64 macOS, but 6-13% slower on 3.13 and 3.14.
    negated = pattern.startswith("!")

    if negated:
        pattern = pattern[1:]

    # We check the very last character as it is, so even an escaped "a\/" means
    # directories only. That leaves the glob "a\", whose backslash escapes nothing, and
    # it never matches.
    directory_only = pattern.endswith("/")

    if directory_only:
        pattern = pattern[:-1]

    # Any other "/" anchors the pattern, even one inside brackets or escaped with a
    # backslash. One at the start only anchors, so we remove it: "/a" means the "a"
    # beside the ignore-file, and nowhere deeper.
    anchored = "/" in pattern
    pattern = pattern.removeprefix("/")

    # Nothing is left of lines like "!" and "/", so there's nothing to match.
    if not pattern:
        return None

    return (pattern, negated, directory_only, anchored)
