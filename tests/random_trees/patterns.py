"""The patterns given in code to a random tree's walk, and their weights."""

from mosey import Mosey
from tests.random_trees.differences import allowed, kept_spaces
from tests.random_trees.draft import Draft
from tests.random_trees.lines import random_line


def flip(line: str) -> str:
    """Add a "!" to the start of a line, or remove the one it starts with.

    Args:
        line: The line.

    Returns:
        The line with its "!" added or removed.
    """
    return line[1:] if line.startswith("!") else "!" + line


def random_pattern(draft: Draft, weight: int, earlier: list[str]) -> str:
    """Return a random pattern that `Mosey.add_pattern` accepts.

    Args:
        draft: The tree so far.
        weight: The pattern's weight.
        earlier: The patterns made so far.

    Returns:
        The pattern.

    Raises:
        AssertionError: When no pattern could be made.
    """
    rng = draft.rng
    lines = [line for holder_lines in draft.lines.values() for line in holder_lines]

    for _ in range(100):
        r = rng.random()

        # Sometimes a line of an ignore-file, or an earlier pattern, with its "!" added
        # or removed, so that they disagree and the weights decide.
        if r < 0.15 and lines:
            pattern = flip(rng.choice(lines))
        elif r < 0.3 and earlier:
            pattern = flip(rng.choice(earlier))
        else:
            # A pattern is tied to the walk's root, like a line of an ignore-file there.
            pattern = random_line(draft, "")

        if not allowed(pattern):
            continue

        # Git is given the heavier patterns with `--exclude`, which keeps their spaces.
        if weight > 0 and kept_spaces(pattern):
            continue

        try:
            Mosey().add_pattern(pattern)
        except ValueError:
            continue

        return pattern

    raise AssertionError("No pattern could be made")


def random_patterns(draft: Draft) -> tuple[tuple[str, int], ...]:
    """Return 0 to 5 patterns weighing 1 or more, and 0 to 5 weighing 0 or less.

    Args:
        draft: The tree so far.

    Returns:
        Each pattern and its weight, in the order to add them.
    """
    rng = draft.rng

    weights = [
        *(rng.randint(1, 3) for _ in range(rng.randint(0, 5))),
        *(rng.randint(-2, 0) for _ in range(rng.randint(0, 5))),
    ]

    # The walk sorts the patterns by weight, so we add them in any order.
    rng.shuffle(weights)
    patterns: list[str] = []

    for weight in weights:
        patterns.append(random_pattern(draft, weight, patterns))

    return tuple(zip(patterns, weights, strict=True))
