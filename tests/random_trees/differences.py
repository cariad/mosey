"""The lines and patterns that Git reads differently, which random trees leave out."""

import re

from mosey.patterns import trim_spaces

# Git reads a run of "*" that makes up a whole segment, straight before an escaped "/",
# as at least one directory, and Mosey reads the "\/" as a plain "/".
ESCAPED_SLASH = re.compile(r"(?:^|/)\*{2,}\\/")

# Git before 2.52 also matches "foo**/bar" against "foobar", and most likely lets
# "/a**" match "a/b". So we leave out a run of "*" straight after other text when a "/"
# (escaped or not) follows it, or when it ends a line that holds another "/".
STAR_RUN = re.compile(r"[^/*]\*{2,}\\?/(?! *$)|/.*[^/*]\*{2,}/? *$")


def allowed(line: str) -> bool:
    """Check that a line holds none of the runs of "*" that Git reads differently.

    Args:
        line: The line.

    Returns:
        `True` if it holds none, otherwise `False`.
    """
    pattern = line.removeprefix("!")
    return not ESCAPED_SLASH.search(pattern) and not STAR_RUN.search(pattern)


def kept_spaces(pattern: str) -> bool:
    r"""Check if Mosey removes any spaces from the end of a pattern.

    Git keeps every space at the end of a pattern given with `--exclude`, so a random
    tree never gives Git a pattern weighing 1 or more that Mosey removes spaces from.
    Mosey keeps a space that a backslash escapes, as in "a\ ", so those stay in.

    Args:
        pattern: The pattern.

    Returns:
        `True` if Mosey removes at least one space, otherwise `False`.
    """
    return len(trim_spaces(pattern)) < len(pattern)
