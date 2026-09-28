"""Functions for working with ignore-file globs.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import re
from typing import Final

SPECIAL: Final[re.Pattern[str]] = re.compile(r"(\\.?|\*+|\?|\[)", re.DOTALL)
"""Finds the parts of a glob that aren't plain text.

A backslash with the character it escapes (or with nothing, at the very end), a run of
"*", a "?", or a "[".
"""


def translate_glob(glob: str) -> str | None:
    r"""Return a glob translated into a regular expression.

    A "*" matches any run of characters, even none, and a "?" matches exactly one.
    Neither matches a "/". A backslash makes the character after it literal, and every
    other character matches only itself:

    ```text
    Glob     Matches        Doesn't match
    "a*"     "a", "abc"     "ba", "a/b"
    "a?c"    "abc"          "ac", "a/c"
    "a\*"    "a*"           "ab"
    ```

    A "?" matches one character, even one that takes several bytes, so "caf?" matches
    "café".

    Args:
        glob: The glob to translate.

    Returns:
        A regular expression that matches the whole of every name or path the glob
        matches, for use with `fullmatch`. `None` if the glob ends with a backslash that
        escapes nothing, or holds a "[" that isn't escaped, since bracket expressions
        aren't supported yet.
    """
    # NOTE: Splitting the glob, rather than stepping through it one character at a
    # NOTE: time, makes translating a 96-line file's globs about twice as fast: 37-50
    # NOTE: microseconds rather than 78-113 on Python 3.11 to 3.14 on arm64 macOS. Globs
    # NOTE: full of wildcards take about as long either way.
    parts = SPECIAL.split(glob)

    # The regular expression for the text before the first "*", then for the text after
    # each "*".
    chunks = [re.escape(parts[0])]

    # `split` puts each special part between the plain text before and after it, so the
    # parts go: text, special, text, special, text.
    for index in range(1, len(parts), 2):
        special = parts[index]

        if special == "?":
            chunks[-1] += "[^/]"
        elif special[0] == "*":
            # A run of "*" matches the same as one.
            chunks.append("")
        elif special == "[":
            # Bracket expressions aren't supported yet.
            return None
        elif special == "\\":
            # A backslash at the very end has nothing to escape, so the glob is broken
            # and matches nothing.
            return None
        else:
            # A backslash makes the character after it literal.
            chunks[-1] += re.escape(special[1])

        chunks[-1] += re.escape(parts[index + 1])

    if len(chunks) == 1:
        return chunks[0]

    # With several "*", trying every way to share a long name between them can take
    # seconds. So the text between two "*" is matched at the earliest place it fits, and
    # never moved later, which the "(?>...)" group enforces. That's safe, because
    # fitting it early leaves the most of the name for what comes after.
    #
    # The text before the first "*" has to start the name, and the text after the last
    # one has to end it, so both are matched plainly.
    head, *middle, tail = chunks
    return head + "".join(f"(?>[^/]*?{chunk})" for chunk in middle) + "[^/]*" + tail
