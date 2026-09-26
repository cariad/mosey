"""Unit tests for the `paths` module."""

import os
import sys

from pytest import mark, param

from mosey.candidate import Candidate
from mosey.paths import sort_key


@mark.parametrize(
    ("candidate", "expect"),
    [
        param(
            ("foo.txt", False),
            b"foo.txt",
            id="file",
        ),
        param(
            ("foo", True),
            b"foo/",
            id="directory",
        ),
        param(
            ("café", False),
            b"caf\xc3\xa9",
            id="non-ascii",
        ),
        # The key encodes the name it's given and never normalises it. "café" above
        # spells "é" as the single code point U+00E9, and this spells it as "e" then the
        # combining accent U+0301, so the two get different keys.
        param(
            ("cafe\u0301", False),
            b"cafe\xcc\x81",
            id="decomposed",
        ),
        param(
            ("\U0001f600", False),
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
    assert sort_key(("b.txt", False)) < sort_key(("b", True))


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
    assert sort_key((name, False)) == os.fsencode(name)


def test_sort_key__order() -> None:
    """A directory's entries sort into walk order."""
    entries = [
        ("ba", False),
        ("b_c", False),
        ("b", True),
        ("b.txt", False),
        ("b-c", False),
        ("a", False),
        ("Z", False),
    ]

    # Uppercase before lowercase, then the byte after "b" decides the ties, with the
    # directory "b" sorting as "b/".
    assert sorted(entries, key=sort_key) == [
        ("Z", False),
        ("a", False),
        ("b-c", False),
        ("b.txt", False),
        ("b", True),
        ("b_c", False),
        ("ba", False),
    ]


@mark.skipif(
    sys.platform == "win32",
    reason="Windows turns the placeholder U+DC80 into three bytes, not the one byte "
    "this test expects",
)
def test_sort_key__raw_bytes() -> None:
    """A directory's entries sort by their raw bytes, not by code point."""
    entries = [
        ("é", False),
        ("\udc80", True),
        ("z", False),
    ]

    assert sort_key(("\udc80", True)) == b"\x80/"

    # A directory named with the single byte 0x80 isn't valid UTF-8, so, on Linux,
    # Python represents that byte with the placeholder character U+DC80. As a string,
    # that compares higher than "é" (U+00E9), so a string key would sort it after "é".
    # But the key is the raw bytes, where 0x80 comes before the 0xC3 that starts "é".
    #
    # Only Linux hands Python names like this (macOS refuses to create them), so this
    # test uses strings rather than real files.
    assert sorted(entries, key=sort_key) == [
        ("z", False),
        ("\udc80", True),
        ("é", False),
    ]
