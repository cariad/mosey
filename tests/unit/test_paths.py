"""Unit tests for the `paths` module."""

import os
import sys
from pathlib import Path

from pytest import mark, param, raises

from mosey.candidate import Candidate
from mosey.paths import sort_key, split_start


@mark.parametrize(
    ("candidate", "expect"),
    [
        param(
            (
                "foo.txt",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            b"foo.txt",
            id="file",
        ),
        param(
            (
                "foo",
                True,  # Is a directory
                False,  # Is a symlink
            ),
            b"foo/",
            id="directory",
        ),
        # A symlink sorts as a file, even one to a directory.
        param(
            (
                "foo",
                False,  # Is a directory
                True,  # Is a symlink
            ),
            b"foo",
            id="symlink",
        ),
        param(
            (
                "café",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            b"caf\xc3\xa9",
            id="non-ascii",
        ),
        # The key encodes the name it's given and never normalises it. "café" above
        # spells "é" as the single code point U+00E9, and this spells it as "e" then the
        # combining accent U+0301, so the two get different keys.
        param(
            (
                "cafe\u0301",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            b"cafe\xcc\x81",
            id="decomposed",
        ),
        param(
            (
                "\U0001f600",
                False,  # Is a directory
                False,  # Is a symlink
            ),
            b"\xf0\x9f\x98\x80",
            id="four-byte-character",
        ),
    ],
)
def test_sort_key(candidate: Candidate, expect: bytes) -> None:
    """A candidate's key is its filename as bytes, plus a slash if it's a directory."""
    assert sort_key(candidate) == expect


def test_sort_key__file_before_directory() -> None:
    """A file precedes a directory sharing its prefix if its next byte is below "/"."""
    file = (
        "b.txt",
        False,  # Is a directory
        False,  # Is a symlink
    )

    directory = (
        "b",
        True,  # Is a directory
        False,  # Is a symlink
    )

    file_key = sort_key(file)
    directory_key = sort_key(directory)

    assert file_key < directory_key


@mark.parametrize(
    "name",
    [
        "foo",
        "café",
        # A lone surrogate is how an undecodable byte in a filename reaches Python.
        "\udc80",
    ],
)
def test_sort_key__encodes_like_fsencode(name: str) -> None:
    """A name is encoded the same way `os.fsencode` would encode it."""
    candidate = (
        name,
        False,  # Is a directory
        False,  # Is a symlink
    )

    key = sort_key(candidate)
    expect = os.fsencode(name)

    assert key == expect


def test_sort_key__order() -> None:
    """A directory's entries sort into walk order."""
    entries = [
        (
            "ba",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b_c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b.txt",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b-c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "a",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "Z",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    # Uppercase before lowercase, then the byte after "b" decides the ties, with the
    # directory "b" sorting as "b/".
    ordered = sorted(entries, key=sort_key)

    expect = [
        (
            "Z",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "a",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b-c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b.txt",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "b_c",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "ba",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert ordered == expect


@mark.skipif(
    sys.platform == "win32",
    reason="Windows turns the placeholder U+DC80 into three bytes, not the one byte "
    "this test expects",
)
def test_sort_key__raw_bytes() -> None:
    """A directory's entries sort by their raw bytes, not by code point."""
    entries = [
        (
            "é",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "\udc80",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "z",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    directory = (
        "\udc80",
        True,  # Is a directory
        False,  # Is a symlink
    )

    key = sort_key(directory)

    assert key == b"\x80/"

    # A directory named with the single byte 0x80 isn't valid UTF-8, so, on Linux,
    # Python represents that byte with the placeholder character U+DC80. As a string,
    # that compares higher than "é" (U+00E9), so a string key would sort it after "é".
    # But the key is the raw bytes, where 0x80 comes before the 0xC3 that starts "é".
    #
    # Only Linux hands Python names like this (macOS refuses to create them), so this
    # test uses strings rather than real files.
    ordered = sorted(entries, key=sort_key)

    expect = [
        (
            "z",
            False,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "\udc80",
            True,  # Is a directory
            False,  # Is a symlink
        ),
        (
            "é",
            False,  # Is a directory
            False,  # Is a symlink
        ),
    ]

    assert ordered == expect


@mark.parametrize(
    ("start", "expect"),
    [
        (".", ()),
        ("./", ()),
        ("a", ("a",)),
        ("a/b", ("a", "b")),
        ("a//b/", ("a", "b")),
        ("./a/./b", ("a", "b")),
        ("a.b/.c/d..", ("a.b", ".c", "d..")),
        ("café/ ", ("café", " ")),
        (Path("a", "b"), ("a", "b")),
    ],
)
def test_split_start(start: os.PathLike[str] | str, expect: tuple[str, ...]) -> None:
    """A start splits into its names, tidied up like a `Path`, and "." into none."""
    assert split_start(start) == expect


def test_split_start__empty() -> None:
    """`FileNotFoundError` is raised when the start is empty."""
    with raises(FileNotFoundError):
        split_start("")


@mark.parametrize("start", ["/", "/a", "..", "a/..", "a/../b", Path("/a")])
def test_split_start__not_beneath_the_root(start: os.PathLike[str] | str) -> None:
    """`ValueError` is raised when the start isn't a path beneath the root."""
    with raises(ValueError, match="isn't a path beneath the root"):
        split_start(start)
