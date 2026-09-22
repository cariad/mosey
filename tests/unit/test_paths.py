"""Unit tests for the `paths` module."""

import os
import sys

from pytest import mark, param

from mosey.paths import sort_key

requires_utf8 = mark.skipif(
    sys.getfilesystemencoding() != "utf-8",
    reason="Assumes a UTF-8 file system encoding",
)


def test_sort_key__file() -> None:
    """A file's key is its name."""
    assert sort_key("foo.txt", False) == b"foo.txt"


def test_sort_key__directory() -> None:
    """A directory's key is its name with a trailing slash."""
    assert sort_key("foo", True) == b"foo/"


def test_sort_key__file_before_directory() -> None:
    """A file precedes a directory sharing its prefix if its next byte is below "/"."""
    assert sort_key("b.txt", False) < sort_key("b", True)


@mark.parametrize(
    "name",
    [
        "foo",
        param("café", marks=requires_utf8),
        # A lone surrogate is how an undecodable byte in a filename reaches Python.
        "\udc80",
    ],
)
def test_sort_key__encodes_like_fsencode(name: str) -> None:
    """A name is encoded the same way `os.fsencode` would encode it."""
    assert sort_key(name, False) == os.fsencode(name)


@requires_utf8
@mark.skipif(
    sys.platform == "win32",
    reason="Windows escapes undecodable file names differently",
)
def test_sort_key__undecodable_name__posix() -> None:
    """Linux and macOS sort an undecodable name by its raw bytes, as Git does."""
    # A file named with the single byte 0x80 isn't valid UTF-8, so it reaches Python
    # with that byte escaped as the surrogate U+DC80.
    #
    # As a string, that compares higher than "é" (U+00E9), so a string key would sort it
    # after "é".
    #
    # But git compares the raw bytes, where 0x80 comes *before* the 0xC3 that starts
    # "é", so "\udc80" must sort first.
    assert sort_key("\udc80", False) < sort_key("é", False)


@requires_utf8
@mark.skipif(
    sys.platform != "win32",
    reason="Only Windows escapes unpaired surrogates as three bytes",
)
def test_sort_key__undecodable_name__windows() -> None:
    """Windows encodes an unpaired surrogate as three bytes that sort after "é"."""
    key = sort_key("\udc80", False)
    assert key == b"\xed\xb2\x80"
    assert key > sort_key("é", False)


def test_sort_key__git_order() -> None:
    """A directory's entries sort into the order that Git lists them."""
    entries = [
        ("ba", False),
        ("b_c", False),
        ("b", True),
        ("b.txt", False),
        ("b-c", False),
        ("a", False),
        ("Z", False),
    ]

    # Verified against `git ls-files` with a file inside the "b" directory. Uppercase
    # sorts before lowercase, then "-" (0x2d), "." (0x2e), "/" (0x2f), "_" (0x5f) and
    # "a" (0x61) decide the ties on "b".
    assert sorted(entries, key=lambda entry: sort_key(entry[0], entry[1])) == [
        ("Z", False),
        ("a", False),
        ("b-c", False),
        ("b.txt", False),
        ("b", True),
        ("b_c", False),
        ("ba", False),
    ]


@requires_utf8
@mark.skipif(
    sys.platform == "win32",
    reason="Windows encodes an unpaired surrogate as three bytes, not one",
)
def test_sort_key__git_order__raw_bytes() -> None:
    """A directory's entries sort by their raw bytes, not by code point."""
    entries = [
        ("é", False),
        ("\udc80", True),
        ("z", False),
    ]

    assert sort_key("\udc80", True) == b"\x80/"

    assert sorted(entries, key=lambda entry: sort_key(entry[0], entry[1])) == [
        ("z", False),
        ("\udc80", True),
        ("é", False),
    ]
