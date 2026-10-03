"""Random lines for an ignore-file, of many kinds."""

from posixpath import join

from tests.random_trees.differences import allowed
from tests.random_trees.draft import Draft
from tests.random_trees.pieces import (
    BACKSLASH,
    ENDINGS,
    bracket,
    escape,
    finish,
    random_bracket,
    wild,
)

# Pieces of lines: wildcards, brackets, escapes and upper case.
ATOMS = [
    *("*", "?", "a*", "*.txt", "*.log", "?b", "a?", "[ab]", "[!a]", "[^a]b", "[a-b]"),
    *("[[:alpha:]]", "[[:alpha:]]*", "x[[:space:]]y", ".*", "*a*", "k*p", "*y"),
    *("a**", "**a", "a**b", "[]a]", "[a-]", "[.]a", "x?y", "*.*", "[z-a]", "??", "*b"),
    *(r"\*", r"\?", r"\[a]", r"\#a", r"\!a", "a\\ ", "x\\ y", r"\a", r"a\.txt"),
    *(r"\k\e\e\p", r"a\\b", "A", "*.LOG", "KEEP", "AB", "[A]", "Keep", "kee[P]", "B"),
    *("a\t", "*\t", r"\]", r"a\-b", r"\^a", "a-b", " a", "a.", "]a", "{a,b}"),
]

# Lines that are malformed, never match, are comments or have nothing left, match
# everything, or name the ignore-file itself.
SPECIAL = [
    *("[", "a[", "[a", "a\\", "\\", "[[:foo:]]", "*[[:foo:]]", "[!]", r"a\/", "[]"),
    *("[^]", "[]]", "[[:alpha:]", "[a-", "[\\", "a[\\]", "../a"),
    *("./a", "a//b", "//a", "a//", "./keep", "a/./b", "a/../a", "a[/]b", "*//*"),
    *("#a", "# a", "#", r"\#a", "!", "/", "!/", "//", r"\!a", "!!a", r"!\!a"),
    *(" #a", " !a", "! a", "!#a", "/!a", "*", "!*", "!*/", "/*", "!/*", ".*", "**"),
    *("ignore", "/ignore", "ign*", "!ignore", "*/ignore", "**/ignore", "ignore/"),
    *("!/ignore", "i?nore", "[i]gnore", "*e", "!*e", "!**/ignore", "ignore ", "IGNORE"),
]

# Lines holding a carriage return, or a class that could match one. Only one is removed
# from the end of a line, and no name holds one, so most of these match nothing.
CARRIAGE_RETURNS = [
    *("a\r", "a\r\r", "\ra", "a\r ", "a \r", "*\r", "?\r", "[\r]", "\r", "*\r*"),
    *("a\rb", "a[[:cntrl:]]", "a\\\r", "a[[:space:]]"),
]

# Characters to escape, including ones that don't need it.
ESCAPABLE = [*"*?[]!#\\ -^:/.,{}~%=|<>'\"$&;()+@abkqz019", "\t", "\r"]

# How often each kind of line is made.
LINE_KINDS = {
    "derived": 32,
    "composed": 18,
    "bracket": 12,
    "special": 10,
    "double-star": 9,
    "holder": 6,
    "trailing": 6,
    "escape": 4,
    "carriage-return": 3,
}


def random_line(draft: Draft, holder: str) -> str:
    """Return a random line for an ignore-file.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.

    Raises:
        AssertionError: When no line could be made.
    """
    rng = draft.rng

    for _ in range(100):
        kind = rng.choices(list(LINE_KINDS), list(LINE_KINDS.values()))[0]

        if kind == "derived":
            line = derived_line(draft, holder)
        elif kind == "composed":
            line = composed_line(draft)
        elif kind == "bracket":
            line = bracket_line(draft, holder)
        elif kind == "special":
            line = rng.choice(SPECIAL)
        elif kind == "double-star":
            line = double_star_line(draft, holder)
        elif kind == "holder":
            line = holder_line(draft, holder)
        elif kind == "trailing":
            line = trailing_line(draft, holder)
        elif kind == "escape":
            line = escape_line(draft, holder)
        else:
            line = rng.choice(CARRIAGE_RETURNS)

        if line is not None and allowed(line):
            return line

    raise AssertionError("No line could be made")


def derived_line(draft: Draft, holder: str) -> str:
    """Return a line made from an entry beneath an ignore-file's directory.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.
    """
    rng = draft.rng

    # Sometimes from the root's view, to tempt anchoring from the wrong directory.
    if holder and rng.random() < 0.15:
        holder = ""

    chosen = rng.choice(draft.beneath(holder))
    parts = chosen[len(join(holder, "")) :].split("/")
    slash = 0.5 if chosen in draft.symlinks or chosen in draft.directories else 0.3
    form = rng.choices(
        ["name", "path", "wild", "ancestor", "start", "middle", "end"],
        [25, 20, 15, 10, 10, 10, 10],
    )[0]

    if form == "path" or (form == "ancestor" and len(parts) == 1):
        body = "/".join(escape(rng, part) for part in parts)
        body = "/" + body if len(parts) == 1 or rng.random() < 0.5 else body
    elif form == "wild":
        k = rng.randrange(len(parts))
        body = "/".join(
            wild(rng, part) if i == k else escape(rng, part)
            for i, part in enumerate(parts)
        )
        body = "/" + body if len(parts) == 1 and rng.random() < 0.5 else body
    elif form == "ancestor":
        count = rng.randrange(1, len(parts))
        body = "/" + "/".join(escape(rng, part) for part in parts[:count])
    elif form == "start":
        count = rng.randint(1, min(2, len(parts)))
        body = "**/" + "/".join(escape(rng, part) for part in parts[-count:])
    elif form == "middle" and len(parts) > 1:
        body = f"{escape(rng, parts[0])}/**/{escape(rng, parts[-1])}"
    elif form == "end":
        count = rng.randint(1, len(parts))
        body = "/".join(escape(rng, part) for part in parts[:count])
        body += rng.choice(["/**", "/*"])
        body = "/" + body if rng.random() < 0.3 else body
    else:
        body = escape(rng, parts[-1])

    return finish(rng, body, 0.3, slash)


def composed_line(draft: Draft) -> str:
    """Return a line of one to four parts: names, wildcards, brackets and "**".

    Args:
        draft: The tree so far.

    Returns:
        The line.
    """
    rng = draft.rng
    body = ""
    previous = ""

    for i in range(rng.choice([1, 1, 1, 2, 2, 3, 4])):
        r = rng.random()

        if r < 0.2:
            part = rng.choice(["**", "**", "***"])
        elif r < 0.45:
            part = rng.choice(ATOMS)
        elif r < 0.6:
            part = random_bracket(rng) + rng.choice(["", "*", "a", "?"])
        else:
            part = escape(rng, draft.name())

        if i:
            escaped = not previous.startswith("**") and rng.random() < 0.05
            body += "\\/" if escaped else "/"

        body += part
        previous = part

    body = "/" + body if rng.random() < 0.25 else body
    return finish(rng, body, 0.25, 0.25)


def bracket_line(draft: Draft, holder: str) -> str:
    """Return a line with bracket expressions, often in place of a name's letters.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.
    """
    rng = draft.rng
    beneath = draft.beneath(holder)

    if rng.random() < 0.6:
        name = rng.choice(beneath).rsplit("/", 1)[-1]
        body = "".join(
            bracket(rng, c) if rng.random() < 0.4 else escape(rng, c) for c in name
        )
    else:
        body = "".join(
            random_bracket(rng)
            if rng.random() < 0.6
            else rng.choice(["a", "*", "?", "x"])
            for _ in range(rng.randint(1, 3))
        )

    body = "/" + body if rng.random() < 0.2 else body
    return finish(rng, body, 0.2, 0.15)


def double_star_line(draft: Draft, holder: str) -> str:
    """Return a line with "**", often more than one.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.
    """
    rng = draft.rng
    paths = [path.split("/") for path in draft.beneath(holder)]
    parts = rng.choice(paths)
    first = escape(rng, parts[0])
    last = escape(rng, parts[-1])
    other = escape(rng, rng.choice(rng.choice(paths)))

    body = rng.choice(
        [
            *(f"**/{first}/**/{last}", f"{first}/**", f"**/{first}/**"),
            *(f"**/{last}", f"{first}/**/{last}", f"{first}/**/", f"/**/{last}"),
            *(f"/{first}/**/{other}/**/{last}", f"**/{first}/**/{other}/**/{last}"),
            *(f"***/{last}", f"**/**/{last}", f"{first}/**/**", f"**{last}"),
            *(f"{first}**", f"{first}/**{last}", f"**/{first}*/**", f"{first}/***"),
            *(f"**/[{last[0]}]*", f"{first}/*/**/{last}", f"**/{first}/**/"),
            *(f"**/*/**/{last}", "**/.*"),
            *("**", "/**", "**/", "**/*", "*/**", "***", "**/**"),
        ]
    )

    return finish(rng, body, 0.25, 0.1)


def holder_line(draft: Draft, holder: str) -> str | None:
    """Return a line naming a directory beneath that holds an ignore-file.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line, or `None` if no such directory is beneath.
    """
    rng = draft.rng

    inside = [
        directory
        for directory in draft.lines
        if directory.startswith(join(holder, "")) and directory != holder
    ]

    if not inside:
        return None

    relative = rng.choice(inside)[len(join(holder, "")) :]
    name = escape(rng, relative.rsplit("/", 1)[-1])

    return rng.choice(
        [
            *(name, f"{name}/", f"/{relative}", f"{relative}/", f"{relative}/*"),
            *(f"!{relative}/ignore", f"{relative}/**", f"{relative}/ignore"),
            *(f"!{relative}/", f"**/{name}/", f"{relative}/*/"),
        ]
    )


def trailing_line(draft: Draft, holder: str) -> str:
    """Return a line that ends with spaces, escaped spaces or tabs.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.
    """
    rng = draft.rng
    beneath = draft.beneath(holder)

    if rng.random() < 0.7:
        body = escape(rng, rng.choice(beneath).rsplit("/", 1)[-1])
    else:
        body = rng.choice(["a", "*", "x y", "?", "a\t", "[a ]"])

    body = "!" + body if rng.random() < 0.15 else body
    body = body + "/" if rng.random() < 0.15 else body
    return body + rng.choice(ENDINGS)


def escape_line(draft: Draft, holder: str) -> str:
    """Return a line with many escapes, of any character.

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The line.
    """
    rng = draft.rng
    beneath = draft.beneath(holder)

    if rng.random() < 0.6:
        name = rng.choice(beneath).rsplit("/", 1)[-1]
        body = "".join(BACKSLASH + c if rng.random() < 0.6 else c for c in name)
    else:
        body = "".join(
            BACKSLASH + rng.choice(ESCAPABLE)
            if rng.random() < 0.6
            else rng.choice("ab.")
            for _ in range(rng.randint(1, 4))
        )

    return finish(rng, body, 0.2, 0.1)
