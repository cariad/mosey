"""Unit tests for initialisation of the `Mosey` class."""

from pytest import mark, param, raises

from mosey import Mosey


def test_mosey_init() -> None:
    """Instantiating `Mosey` does not raise any exceptions."""
    Mosey()


@mark.parametrize(
    "name",
    [
        param(".moseyignore", id="leading-dot"),
        param("a.b", id="dot-inside"),
        # Only exactly "." and ".." are refused, never a name that starts with them.
        param("..a", id="leading-dots"),
        param("...", id="three-dots"),
        param("a b", id="space"),
        param("café", id="non-ascii"),
    ],
)
def test_mosey_init__ignore_filename(name: str) -> None:
    """Any name that isn't a path is accepted as the ignore-file name."""
    Mosey(ignore_filename=name)


@mark.parametrize(
    "name",
    [
        param("", id="empty"),
        param(".", id="dot"),
        param("..", id="dot-dot"),
        param("a/b", id="slash"),
        param("/a", id="leading-slash"),
        param("a/", id="trailing-slash"),
        # A backslash is refused on every operating system, not only on Windows.
        param("a\\b", id="backslash"),
        param("\\", id="lone-backslash"),
        param("a\x00b", id="null"),
    ],
)
def test_mosey_init__ignore_filename_is_not_a_name(name: str) -> None:
    """`ValueError` is raised when the ignore-file name isn't a plain name."""
    # Raised by `Mosey` itself, before anything is walked.
    with raises(ValueError) as raised:
        Mosey(ignore_filename=name)

    assert str(raised.value) == f"{name!r} isn't a filename"


def test_mosey_init__ignore_filename_is_keyword_only() -> None:
    """`TypeError` is raised when the ignore-file name is passed by position."""
    with raises(TypeError):
        Mosey("ignore")  # pyright: ignore[reportCallIssue]
