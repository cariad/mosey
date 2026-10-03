"""The runs of "*" that Git reads differently, which random trees leave out."""

import re

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
