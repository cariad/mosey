"""Pieces of ignore-file lines: escaped names, bracket expressions and wildcards."""

import random

BACKSLASH = "\\"

# Spaces are removed from the end of a line unless they're escaped, and tabs never are.
ENDINGS = [" ", "  ", "\\ ", "\\  ", "\\\\ ", "\\\\\\ ", "\t", " \t", "\t ", "\\\t"]

CLASSES = [
    *("alnum", "alpha", "blank", "cntrl", "digit", "graph", "lower", "print"),
    *("punct", "space", "upper", "xdigit"),
]

# Pieces of bracket expressions, some of them malformed.
BRACKET_PIECES = [
    *("a", "b", "z", "A", ".", "-", "]", "[", "!", "^", ":", " ", "*", "?", "/", "\t"),
    *(r"\]", r"\\", r"\-", r"\^", r"\!", r"\[", r"\a", "\\ "),
    *("a-z", "z-a", r"a-\]", "--0", "!--", ".-0", "]-a", " -~", "0-9", "9-0"),
    *("[:bogus:]", "[:ALPHA:]", "[::]", "[=a=]", "[.a.]", "[:", "[:alpha", ":]"),
    *(f"[:{name}:]" for name in CLASSES),
]


def escape(rng: random.Random, name: str) -> str:
    """Escape a name so that a glob matches it exactly, almost always.

    Args:
        rng: The random number generator.
        name: The name.

    Returns:
        The glob.
    """
    escaped = ""

    for character in name:
        if character in "\\*?[":
            escaping = rng.random() < 0.92
            escaped += BACKSLASH + character if escaping else character
        elif rng.random() < 0.04:
            # An escape before any other character only keeps it as it is.
            escaped += BACKSLASH + character
        else:
            escaped += character

    return escaped


def bracket(rng: random.Random, character: str) -> str:
    """Return a bracket expression that matches a character, or sometimes doesn't.

    Args:
        rng: The random number generator.
        character: The character.

    Returns:
        The bracket expression.
    """

    def member(c: str) -> str:
        escaping = c in "\\]-^![" or rng.random() < 0.15
        return BACKSLASH + c if escaping else c

    code = ord(character)
    negation = rng.choice("!^")
    shape = rng.randrange(9)

    if shape == 0:
        return f"[{member(character)}]"

    if shape == 1:
        low = chr(max(0x20, code - rng.randint(0, 3)))
        high = chr(min(0x7E, code + rng.randint(0, 3)))
        return f"[{member(low)}-{member(high)}]"

    if shape == 2:
        # A range whose ends are the wrong way round matches only its first.
        high = chr(max(0x20, code - rng.randint(1, 5)))
        return f"[{member(character)}-{member(high)}]"

    if shape == 3:
        return f"[[:{rng.choice(CLASSES)}:]{member(character)}]"

    if shape == 4:
        others = rng.sample([c for c in "abxyz.-]^!q" if c != character], 2)
        return f"[{negation}{''.join(member(c) for c in others)}]"

    if shape == 5:
        return f"[]{member(character)}]"

    if shape == 6:
        dashed = [f"[-{member(character)}]", f"[{member(character)}-]"]
        return rng.choice(dashed)

    if shape == 7:
        # A negated set that holds the character doesn't match it.
        return f"[{negation}{member(character)}]"

    return f"[{member(character)}a-c-x]"


def random_bracket(rng: random.Random) -> str:
    """Return a random bracket expression, which might be malformed.

    Args:
        rng: The random number generator.

    Returns:
        The bracket expression.
    """
    inner = rng.choice(["", "", "!", "^"]) + rng.choice(["", "", "]"])
    inner += "".join(rng.choices(BRACKET_PIECES, k=rng.randint(0, 4)))
    return "[" + inner + ("]" if rng.random() < 0.93 else "")


def wild(rng: random.Random, name: str) -> str:
    """Return a glob that almost always matches a name, and maybe others.

    Args:
        rng: The random number generator.
        name: The name.

    Returns:
        The glob.
    """
    if rng.random() < 0.2:
        return rng.choice(["*", "**", "?" * len(name)])

    k = rng.randrange(len(name))
    head = escape(rng, name[:k])
    tail = escape(rng, name[k + 1 :])
    shape = rng.randrange(6)

    if shape == 0:
        return head + "?" + tail

    if shape == 1:
        return head + "*"

    if shape == 2:
        return "*" + tail

    if shape == 3:
        return head + "*" + escape(rng, name[k:]) + "*"

    return head + bracket(rng, name[k]) + tail


def finish(rng: random.Random, body: str, negate: float, slash: float) -> str:
    """Add a random "!", a trailing "/" and trailing spaces or tabs to a line.

    Args:
        rng: The random number generator.
        body: The line so far.
        negate: The chance of a "!".
        slash: The chance of a trailing "/".

    Returns:
        The line.
    """
    if body.startswith(("#", "!")) and rng.random() < 0.9:
        body = BACKSLASH + body

    if rng.random() < slash and not body.endswith("/"):
        body += "/"

    if rng.random() < negate:
        body = "!" + body

    if rng.random() < 0.05:
        body += rng.choice(ENDINGS)

    return body
