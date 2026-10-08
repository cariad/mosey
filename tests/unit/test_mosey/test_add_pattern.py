"""Unit tests for the `Mosey.add_pattern` function."""

from pathlib import Path

from pytest import mark, param, raises

from mosey import Mosey
from mosey.patterns import check_pattern
from tests.file_system_helpers import make_tree, write_ignore_files


def test_add_pattern() -> None:
    """Adding a pattern returns `None` rather than the `Mosey`."""
    assert Mosey().add_pattern("*.pdf") is None


def test_add_pattern__default_weight(tmp_path: Path) -> None:
    """A pattern added without a weight weighs 0."""
    make_tree(tmp_path, "a.pdf", "b.pdf")
    write_ignore_files(tmp_path, {"": ["!a.pdf"]})

    builder = Mosey()
    builder.set_ignore_filename("ignore")
    builder.add_pattern("!b.pdf", weight=0)
    builder.add_pattern("*.pdf")
    walker = builder.build()

    # The ignore-file overrules "*.pdf" and keeps "a.pdf", so "*.pdf" weighs 0 or less.
    # And "*.pdf" overrules "!b.pdf", which weighs 0 and was added first, so it weighs 0
    # or more.
    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == [
        "a.pdf",
        "ignore",
    ]


@mark.parametrize(
    "pattern",
    [
        param("a\nb", id="line-break"),
        param("a\x00b", id="null"),
        param("#a", id="comment"),
        param("\ufeffa", id="byte-order-mark"),
        param("a\r", id="carriage-return"),
        param("build\\out", id="backslash-before-letter"),
        param("!", id="nothing-to-match"),
        param("a//b", id="empty-segment"),
        param("[a", id="broken"),
    ],
)
def test_add_pattern__refused(pattern: str) -> None:
    """`ValueError` is raised, with `check_pattern`'s message, for a refused pattern."""
    with raises(ValueError) as expected:
        check_pattern(pattern)

    # Raised by `Mosey` itself, before anything is built or walked.
    with raises(ValueError) as raised:
        Mosey().add_pattern(pattern)

    assert str(raised.value) == str(expected.value)


@mark.parametrize(
    "pattern",
    [
        # Each would ignore one of the files below if it were added: "#c" matches "#c",
        # and "\c" matches "c".
        param("#c", id="comment"),
        param("\\c", id="backslash-before-letter"),
    ],
)
def test_add_pattern__refused_adds_nothing(tmp_path: Path, pattern: str) -> None:
    """A refused pattern isn't added, and the patterns added before it still apply."""
    make_tree(tmp_path, "#c", "a.log", "c")

    builder = Mosey()
    builder.add_pattern("*.log")

    with raises(ValueError):
        builder.add_pattern(pattern)

    walker = builder.build()

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["#c", "c"]
