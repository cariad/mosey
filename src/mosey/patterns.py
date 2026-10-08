"""Functions for working with ignore-file patterns.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

from typing import TypeAlias

from .globs import SPECIAL, translate_glob

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


def check_pattern(text: str) -> None:
    """Check that a pattern given in code means what an ignore-file's line would.

    A broken line in an ignore-file matches nothing, because the file belongs to the
    tree being walked. A pattern given in code belongs to the caller, so a mistake is
    refused instead. Every pattern this accepts means exactly what the same line means
    in an ignore-file, and isn't broken.

    Default and overriding patterns are documented at
    https://cariad.github.io/mosey/default-and-overriding-patterns/.

    Args:
        text: The pattern to check.

    Raises:
        ValueError: When an ignore-file would read the pattern differently, it's broken,
            or it holds a backslash that escapes nothing.
    """
    # Reading an ignore-file splits it into lines, so no line can hold a line break,
    # and drops any line holding a zero byte, which no name can hold.
    if "\n" in text:
        raise ValueError(f"{text!r} holds a line break")

    if "\x00" in text:
        raise ValueError(f"{text!r} holds a null character")

    # An ignore-file reads a line starting with "#" as a comment.
    if text.startswith("#"):
        raise ValueError(f"{text!r} would be a comment")

    # Reading an ignore-file removes a byte order mark from the start of the file, and a
    # carriage return from the end of each line. They're the usual leftovers of reading
    # a text file without care, and invisible, so we refuse them rather than let the
    # pattern match something else.
    if text.startswith("\ufeff"):
        raise ValueError(f"{text!r} starts with a byte order mark")

    if text.endswith("\r"):
        raise ValueError(f"{text!r} ends with a carriage return")

    # A backslash only escapes something before "\", "*", "?", "[", "]", "!", "#", a
    # space, "-" or "^", so one before anything else is most likely a Windows path, like
    # "build\out" or "node_modules\@types" from `os.path.join`, which matches a name
    # like "buildout" rather than "out" inside "build". Backslashes escape each other in
    # pairs, so "\\" is skipped whole.
    index = text.find("\\")

    while index != -1:
        escaped = text[index + 1 : index + 2]

        # At the very end, `escaped` is empty, and `"" in "..."` is `True`, so a
        # backslash there is left for the check for broken globs below.
        if escaped not in "\\*?[]!# -^":
            raise ValueError(
                f"{text!r} has a backslash before {escaped!r}, which escapes nothing"
            )

        index = text.find("\\", index + 2)

    pattern = parse_pattern(text)

    if pattern is None:
        raise ValueError(f"{text!r} has nothing to match")

    glob = pattern[0]

    # No path has an empty, "." or ".." segment, so a glob like "./a" or "a//b" can
    # never match. We only check the glob as it's written: a bracket form like "[.]/a"
    # or "a[/]b" slips through, but nobody writes one of those by accident.
    if any(segment in ("", ".", "..") for segment in glob.split("/")):
        raise ValueError(
            f'{text!r} has an empty, "." or ".." segment, so never matches'
        )

    if SPECIAL.search(glob) is not None and translate_glob(glob) is None:
        raise ValueError(f"{text!r} is broken, so never matches")


def parse_pattern(text: str) -> Pattern | None:
    """Return a line of an ignore-file parsed into a pattern.

    Trailing spaces are removed, unless a backslash escapes one. Then a "!" at the start
    negates the pattern, a "/" at the end means it only matches directories, and a "/"
    anywhere else anchors it. One "/" at the start is removed.

    Everything else stays in the glob exactly as written. Nothing is tidied up, so lines
    like "./a" and "a//b" parse, but can never match a path.

    Ignore-files are documented at https://cariad.github.io/mosey/ignore-files/.

    Args:
        text: The line to parse.

    Returns:
        The pattern, or `None` if nothing is left of the line to match, as with "!" or
        "/".
    """
    # Trailing spaces are invisible and easy to leave behind by accident, so we remove
    # them. Only spaces, though: a filename can end with other whitespace.
    #
    # NOTE: We only call `trim_spaces` for a line that ends with a space. Calling it for
    # NOTE: every line made parsing a 96-line file 9-13% slower on Python 3.11 to 3.14
    # NOTE: on arm64 macOS, and checking first made no difference to lines without one.
    pattern = text.rstrip(" ")

    if len(pattern) != len(text):
        pattern = trim_spaces(text)

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


def trim_spaces(text: str) -> str:
    """Return a line of an ignore-file without the spaces at its end.

    A space that a backslash escapes is kept.

    Ignore-files are documented at https://cariad.github.io/mosey/ignore-files/.

    Args:
        text: The line.

    Returns:
        The line without the spaces at its end.
    """
    pattern = text.rstrip(" ")

    if len(pattern) != len(text):
        # To keep a trailing space, escape it with a backslash: "a\ " matches a name
        # ending with a space. Backslashes escape each other in pairs, so the space is
        # only escaped when an odd number of them come right before it. Then we put that
        # one space back, and any after it stay removed.
        backslashes = len(pattern) - len(pattern.rstrip("\\"))

        if backslashes % 2:
            pattern = text[: len(pattern) + 1]

    return pattern
