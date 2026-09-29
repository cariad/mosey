"""Functions for working with ignore-file globs.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import re
from typing import Final

CLASSES: Final[dict[str, str]] = {
    "alnum": "0-9A-Za-z",
    "alpha": "A-Za-z",
    "blank": r"\t\x20",
    "cntrl": r"\x00-\x1f\x7f",
    "digit": "0-9",
    "graph": r"\x21-\x2e\x30-\x7e",
    "lower": "a-z",
    "print": r"\x20-\x2e\x30-\x7e",
    "punct": r"\x21-\x2e\x3a-\x40\x5b-\x60\x7b-\x7e",
    "space": r"\t\n\r\x20",
    "upper": "A-Z",
    "xdigit": "0-9A-Fa-f",
}
"""The classes that a bracket expression can name, like "[:digit:]", and their members.

Each class's members are written as the inside of a regular expression's "[...]".
They're ASCII characters only, and never "/", since a bracket expression never matches
one.
"""

SPECIAL: Final[re.Pattern[str]] = re.compile(r"(\\.?|\*+|\?|\[)", re.DOTALL)
"""Finds the parts of a glob that aren't plain text.

A backslash with the character it escapes (or with nothing, at the very end), a run of
"*", a "?", or a "[".
"""


def translate_bracket(glob: str, start: int) -> tuple[str, int] | None:
    """Return a bracket expression translated into a regular expression.

    Args:
        glob: The glob that holds the bracket expression.
        start: The index just after the expression's "[".

    Returns:
        The regular expression, and the index just after the expression's closing "]".
        `None` if nothing closes the expression, or it names an unknown class.
    """
    negated = glob.startswith(("!", "^"), start)
    index = start + 1 if negated else start

    # A "]" first in the set is a member, not the end.
    first = index

    # The inside of the regular expression's "[...]", and whether any member is a "/".
    members = ""
    slash = False

    while True:
        if index == len(glob):
            # Nothing closes the set, so the glob is broken and matches nothing.
            return None

        character = glob[index]

        if character == "]" and index > first:
            break

        if character == "[" and glob.startswith(":", index + 1):
            # "[:" starts a class if the next "]", even an escaped one, comes straight
            # after another ":". Otherwise the "[" is a member like any other.
            close = glob.find("]", index + 2)

            if close > index + 2 and glob[close - 1] == ":":
                name = glob[index + 2 : close - 1]

                if name not in CLASSES:
                    # An unknown class breaks the glob, so it matches nothing.
                    return None

                members += CLASSES[name]
                index = close + 1
                continue

        if character == "\\":
            # A backslash makes the character after it a member, whatever it is.
            index += 1

            if index == len(glob):
                return None

            character = glob[index]

        low = high = character
        index += 1

        # A "-" makes a range, unless it's the last member in the set.
        if glob.startswith("-", index) and glob[index + 1 : index + 2] not in ("", "]"):
            index += 1
            high = glob[index]

            if high == "\\":
                index += 1

                if index == len(glob):
                    return None

                high = glob[index]

            index += 1

        # A range whose ends are the wrong way round matches only its first character.
        high = max(low, high)

        slash = slash or low <= "/" <= high

        if low == high:
            members += re.escape(low)
        else:
            members += f"{re.escape(low)}-{re.escape(high)}"

    if negated:
        return f"[^/{members}]", index + 1

    if slash:
        # A bracket expression never matches "/", even when one of its members does.
        return f"(?!/)[{members}]", index + 1

    return f"[{members}]", index + 1


def translate_glob(glob: str) -> str | None:
    r"""Return a glob translated into a regular expression.

    A "*" matches any run of characters, even none, and a "?" matches exactly one. A
    bracket expression matches one character from a set. None of them matches a "/". A
    backslash makes the character after it literal, and every other character matches
    only itself:

    ```text
    Glob            Matches        Doesn't match
    "a*"            "a", "abc"     "ba", "a/b"
    "a?c"           "abc"          "ac", "a/c"
    "a\*"           "a*"           "ab"
    "a[bc]"         "ab", "ac"     "ad", "abc"
    "a[!b]c"        "adc"          "abc", "a/c"
    "a[b-d]"        "ac"           "ae"
    "a[[:digit:]]"  "a1"           "ab"
    ```

    In a bracket expression, a "!" or "^" straight after the "[" negates the set, and a
    "]" first in the set is a member rather than the end. A range whose ends are the
    wrong way round, like "y-a", matches only its first character. A "-" is a member
    when it's first or last in the set, or straight after a range or a class. A
    backslash makes the character after it a member. The classes are "[:alnum:]",
    "[:alpha:]", "[:blank:]", "[:cntrl:]", "[:digit:]", "[:graph:]", "[:lower:]",
    "[:print:]", "[:punct:]", "[:space:]", "[:upper:]" and "[:xdigit:]", and they hold
    ASCII characters only.

    A "?" or a bracket expression matches one character, even one that takes several
    bytes, so "caf?" and "caf[!x]" match "café".

    Args:
        glob: The glob to translate.

    Returns:
        A regular expression that matches the whole of every name or path the glob
        matches, for use with `fullmatch`. `None` if the glob ends with a backslash that
        escapes nothing, holds a "[" that nothing closes, or names an unknown class.
    """
    # NOTE: Jumping from one special part to the next with `search`, rather than
    # NOTE: stepping through the glob one character at a time, makes translating a 96-
    # NOTE: line file's globs over twice as fast: 39-53 microseconds rather than 91-127
    # NOTE: on Python 3.11 to 3.14 on arm64 macOS.
    #
    # NOTE: Globs full of wildcards take about as long either way. Splitting the glob
    # NOTE: first would be 3-10% faster on those, but `SPECIAL` would then have to find
    # NOTE: whole bracket expressions, and one broken line of 2,000 characters could
    # NOTE: take over a second.

    # The regular expression for the text before the first "*", then for the text after
    # each "*".
    chunks = [""]

    # Where the plain text before the next special part starts.
    position = 0

    while match := SPECIAL.search(glob, position):
        chunks[-1] += re.escape(glob[position : match.start()])
        position = match.end()
        special = match[0]

        if special == "?":
            chunks[-1] += "[^/]"
        elif special[0] == "*":
            # A run of "*" matches the same as one.
            chunks.append("")
        elif special == "[":
            bracket = translate_bracket(glob, position)

            if bracket is None:
                return None

            translation, position = bracket
            chunks[-1] += translation
        elif special == "\\":
            # A backslash at the very end has nothing to escape, so the glob is broken
            # and matches nothing.
            return None
        else:
            # A backslash makes the character after it literal.
            chunks[-1] += re.escape(special[1])

    chunks[-1] += re.escape(glob[position:])

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
