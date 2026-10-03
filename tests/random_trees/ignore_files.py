"""The ignore-files in a random tree: which directories have one, and their bytes."""

import random
from posixpath import join

from tests.random_trees.differences import allowed
from tests.random_trees.draft import Draft
from tests.random_trees.lines import random_line
from tests.random_trees.pieces import BACKSLASH

UTF8_BOM = bytes([0xEF, 0xBB, 0xBF])


def add_ignore_files(draft: Draft) -> None:
    """Add an ignore-file to the root and to about a third of the directories.

    Args:
        draft: The tree so far.
    """
    rng = draft.rng

    for directory in draft.directories:
        if join(directory, "ignore") in draft.directories:
            continue

        if not directory or rng.random() < 0.35:
            draft.lines[directory] = []

    for holder in draft.lines:
        r = rng.random()

        if r < 0.12:
            draft.lines[holder] = nothing_lines(rng)
        elif r < 0.22:
            draft.lines[holder] = directory_only_lines(draft, holder)
        else:
            count = rng.randint(0, 5)
            draft.lines[holder] = [random_line(draft, holder) for _ in range(count)]

    for directory in draft.directories:
        if directory.endswith("/ignore"):
            aim_at_ignore_directory(draft, directory)


def aim_at_ignore_directory(draft: Draft, path: str) -> None:
    """Add one or two lines aimed at a directory named like the ignore-file.

    Args:
        draft: The tree so far.
        path: The directory's path.
    """
    rng = draft.rng
    above = [holder for holder in draft.lines if path.startswith(join(holder, ""))]

    for _ in range(rng.randint(1, 2)):
        holder = rng.choice(above)
        relative = path[len(join(holder, "")) :]
        choices = [
            *("ignore/", "!ignore/", "ignore", "!ignore", "**/ignore/", "ignore/*"),
            *("**/ignore/*", "**/ignore/**", f"/{relative}/", f"!{relative}/"),
            *(f"{relative}/*", f"!{relative}/a", f"{relative}/ignore", "*/"),
            *(f"!{relative}/ignore", "!*/", "ign*/", "i?nore/", "[i]gnore"),
        ]

        draft.lines[holder].append(rng.choice(choices))


def nothing_lines(rng: random.Random) -> list[str]:
    """Return lines that compile to nothing: none, comments, malformed or blank.

    Args:
        rng: The random number generator.

    Returns:
        The lines.
    """
    pool = rng.choice(
        [
            [],
            ["#a", "# a", "#", "#*", "#ignore", "#!a", "#a/"],
            ["[", "a[", "[a", "a\\", "\\", "[!]", "[]", r"a\/", "[[:foo:]]"],
            ["", "   ", " ", "!", "/", "!/", "//"],
        ]
    )

    count = rng.randint(1, 4) if pool else 0
    return [rng.choice(pool) for _ in range(count)]


def directory_only_lines(draft: Draft, holder: str) -> list[str]:
    """Return one to four lines that each end with "/".

    Args:
        draft: The tree so far.
        holder: The ignore-file's directory.

    Returns:
        The lines.
    """
    count = draft.rng.randint(1, 4)
    lines: list[str] = []

    while len(lines) < count:
        line = random_line(draft, holder)

        if line.endswith(BACKSLASH):
            continue

        line = line if line.endswith("/") else line + "/"

        if allowed(line):
            lines.append(line)

    return lines


def encode(rng: random.Random, lines: list[str]) -> bytes:
    """Return an ignore-file's bytes, with random line endings and maybe a BOM.

    Args:
        rng: The random number generator.
        lines: The file's lines.

    Returns:
        The bytes.
    """
    r = rng.random()

    if r < 0.15:
        endings = ["\r\n"] * len(lines)
    elif r < 0.22:
        endings = [rng.choice(["\n", "\r\n"]) for _ in lines]
    else:
        endings = ["\n"] * len(lines)

    if lines and rng.random() < 0.2:
        endings[-1] = ""

    bom = UTF8_BOM if rng.random() < 0.15 else b""
    text = "".join(line + end for line, end in zip(lines, endings, strict=True))
    return bom + text.encode("ascii")
