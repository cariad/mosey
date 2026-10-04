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
    """Return a glob translated into a regular expression.

    Ignore-files are documented at https://cariad.github.io/mosey/ignore-files/.

    Args:
        glob: The glob to translate.

    Returns:
        A regular expression that matches the whole of every name or path the glob
        matches, for use with `fullmatch`. `None` if the glob ends with a backslash that
        escapes nothing, holds a "[" that nothing closes, or names an unknown class.
    """
    # NOTE: Jumping from one special part to the next with `search`, rather than
    # NOTE: stepping through the glob one character at a time, makes translating a 96-
    # NOTE: line file's globs about twice as fast: 34-47 microseconds rather than 73-106
    # NOTE: on Python 3.11 to 3.14 on arm64 macOS.
    #
    # NOTE: Stepping would be 6% slower to 19% faster on globs full of wildcards, and
    # NOTE: 5-23% faster on globs full of brackets. Splitting the glob first would be
    # NOTE: 2-13% faster on globs full of wildcards, but `SPECIAL` would then have to
    # NOTE: find whole bracket expressions, and one broken line of 2,000 characters
    # NOTE: could take over a second.

    # With several "*", trying every way to share a long name between them can take
    # seconds. So the text between two "*" is matched at the earliest place it fits, and
    # never moved later, which the "(?>...)" group enforces. That's safe, because
    # fitting it early leaves the most of the name for what comes after.
    #
    # The text before the first "*" has to start the name, and the text after the last
    # one has to end it, so both are matched plainly.
    #
    # A "**" is the same, one level up. The part of the glob between two "**" ends with
    # a "/", and only a "/" written in it can match one, so wherever it starts, it
    # covers a fixed number of whole directories. So it's matched at the earliest
    # directory where it fits, and never moved later, which leaves the most of the path
    # for what comes after. The parts before the first "**" and after the last one are
    # matched plainly.

    # NOTE: `chunk`, `part` and `finished` are local variables that grow with `+=`,
    # NOTE: which can add to a string without copying it. On Python 3.11 to 3.14 on
    # NOTE: arm64 macOS, translating 64,000 "?" takes about 15 milliseconds rather than
    # NOTE: 150 when each chunk is an item in a list, and 22,000 "*a" take about 8
    # NOTE: milliseconds rather than 55 when `part` is rebuilt with an f-string.

    # The regular expression for the text since the last "*".
    chunk = ""

    # The regular expression for the text since the last "**", up to its last "*", or
    # `None` if there's no "*" since the last "**".
    part: str | None = None

    # The regular expression for the glob up to its last "**", or `None` if there's no
    # "**" that makes up a whole path segment.
    finished: str | None = None

    # Where the plain text before the next special part starts.
    position = 0

    while match := SPECIAL.search(glob, position):
        start = match.start()
        chunk += re.escape(glob[position:start])
        position = match.end()
        special = match[0]

        if special == "?":
            chunk += "[^/]"
        elif special[0] == "*":
            whole = len(special) > 1 and (start == 0 or glob[start - 1] == "/")

            if whole and (
                position == len(glob) or glob.startswith(("/", "\\/"), position)
            ):
                # The part before the "**" is finished.
                if part is not None:
                    chunk = f"{part}[^/]*{chunk}"

                if finished is None:
                    finished = chunk
                else:
                    finished += f"(?>(?:[^/]*/)*?{chunk})"

                chunk = ""

                if position == len(glob):
                    # A "**" at the end matches everything inside, even a line break.
                    return f"{finished}(?s:.*)"
                else:
                    # An escaped "/" after the "**" counts the same as a plain one.
                    part = None
                    position = glob.index("/", position) + 1
            else:
                # Any other run of "*" matches the same as one.
                if part is None:
                    part = chunk
                else:
                    part += f"(?>[^/]*?{chunk})"

                chunk = ""
        elif special == "[":
            bracket = translate_bracket(glob, position)

            if bracket is None:
                return None

            translation, position = bracket
            chunk += translation
        elif special == "\\":
            # A backslash at the very end has nothing to escape, so the glob is broken
            # and matches nothing.
            return None
        else:
            # A backslash makes the character after it literal.
            chunk += re.escape(special[1])

    chunk += re.escape(glob[position:])

    if part is not None:
        chunk = f"{part}[^/]*{chunk}"

    if finished is None:
        return chunk

    # NOTE: Writing the last "**" with ".*", rather than as "(?:[^/]*/)*" like the
    # NOTE: others, makes matching a glob like "**/a" 24-28% faster, and one like
    # NOTE: "a/**/b" 2-6% faster, on Python 3.11 to 3.14 on arm64 macOS.

    # Each "**" but the last stays at the first directory where the part after it fits,
    # so a glob can't stall. The "(?s:...)" lets "." match a line break too, which a
    # name can hold.
    return f"{finished}(?s:.*/)?{chunk}"
