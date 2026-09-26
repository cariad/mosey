"""Unit tests for the `ignore_files` module."""

import os
import subprocess
import sys

from pytest import mark, param

import mosey
from mosey.ignore_files import split_ignore_file
from mosey.paths import FS_ENCODING


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"",
            [],
            id="empty",
        ),
        param(
            b"a",
            ["a"],
            id="one-line",
        ),
        param(
            b"a\nb",
            ["a", "b"],
            id="final-line-without-newline",
        ),
        param(
            b"a\nb\n",
            ["a", "b"],
            id="final-newline",
        ),
        param(
            b"\n",
            [],
            id="only-a-newline",
        ),
        param(
            b"a\n\nb\n",
            ["a", "b"],
            id="empty-line",
        ),
        param(
            b"a\n\n",
            ["a"],
            id="final-empty-line",
        ),
        param(
            b" a \n",
            [" a "],
            id="spaces",
        ),
        param(
            b"  \n",
            ["  "],
            id="only-spaces",
        ),
        param(
            b"\ta\t\n",
            ["\ta\t"],
            id="tabs",
        ),
        # Lines keep their order, and repeats are kept, because a later line can
        # override an earlier one.
        param(
            b"\xef\xbb\xbflogs\n# Logs\r\n\nbuild/\nlogs",
            ["logs", "build/", "logs"],
            id="example",
        ),
    ],
)
def test_split_ignore_file(data: bytes, expect: list[str]) -> None:
    """An ignore-file's contents are split at each newline, and empty lines dropped."""
    assert split_ignore_file(data) == expect


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"a\r\nb\r\n",
            ["a", "b"],
            id="windows-line-endings",
        ),
        param(
            b"a\nb\r\nc",
            ["a", "b", "c"],
            id="mixed-line-endings",
        ),
        param(
            b"a\r",
            ["a"],
            id="final-line-without-newline",
        ),
        param(
            b"a\r\n\r\nb\r\n",
            ["a", "b"],
            id="empty-line",
        ),
        param(
            b"a\r\r\n",
            ["a\r"],
            id="only-one-is-removed",
        ),
        param(
            b"a\rb\n",
            ["a\rb"],
            id="middle",
        ),
        param(
            b"\ra\n",
            ["\ra"],
            id="start",
        ),
    ],
)
def test_split_ignore_file__carriage_return(data: bytes, expect: list[str]) -> None:
    """One carriage return is removed from the end of each line, and no others."""
    assert split_ignore_file(data) == expect


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"# a\nb\n",
            ["b"],
            id="comment",
        ),
        param(
            b"#\nb\n",
            ["b"],
            id="only-a-hash",
        ),
        param(
            b"a\n# b",
            ["a"],
            id="final-line-without-newline",
        ),
        param(
            b" # a\n",
            [" # a"],
            id="leading-space",
        ),
        param(
            b"\\# a\n",
            ["\\# a"],
            id="escaped",
        ),
        param(
            b"a # b\n",
            ["a # b"],
            id="middle",
        ),
    ],
)
def test_split_ignore_file__comments(data: bytes, expect: list[str]) -> None:
    """A line that starts with "#" is a comment, and is dropped."""
    assert split_ignore_file(data) == expect


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"ab\x00cd\nx\n",
            ["x"],
            id="middle",
        ),
        # Windows PowerShell 5.1 appending "*.log" to an existing file, in UTF-16.
        param(
            b"a\n*\x00.\x00l\x00o\x00g\x00\r\x00\n\x00",
            ["a"],
            id="powershell",
        ),
    ],
)
def test_split_ignore_file__nul(data: bytes, expect: list[str]) -> None:
    """A line holding a zero byte is dropped."""
    assert split_ignore_file(data) == expect


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"\xef\xbb\xbfa\n",
            ["a"],
            id="start",
        ),
        param(
            b"\xef\xbb\xbf",
            [],
            id="only-a-bom",
        ),
        param(
            b"\xef\xbb\xbf\n",
            [],
            id="empty-line",
        ),
        param(
            b"\xef\xbb\xbf# a\nb\n",
            ["b"],
            id="comment",
        ),
        param(
            b"a\n\xef\xbb\xbfb\n",
            ["a", "\ufeffb"],
            id="second-line",
        ),
        param(
            b"\xef\xbb\xbf\xef\xbb\xbfa\n",
            ["\ufeffa"],
            id="twice",
        ),
    ],
)
def test_split_ignore_file__bom(data: bytes, expect: list[str]) -> None:
    """A UTF-8 byte order mark is removed from the very start, and nowhere else."""
    assert split_ignore_file(data) == expect


@mark.skipif(
    sys.platform != "linux",
    reason="Only Linux takes its file system encoding from the locale",
)
def test_split_ignore_file__bom__not_utf8() -> None:
    """A UTF-8 byte order mark is removed when the file system encoding isn't UTF-8."""
    # Only UTF-8 decodes the BOM's bytes to U+FEFF, so they have to be removed before
    # decoding. Every CI runner's file system encoding is UTF-8, so we check this in a
    # child interpreter that has UTF-8 mode and locale coercion switched off, so that
    # it takes its encoding from the C locale instead.
    #
    # That's also how Python starts inside Apache's mod_wsgi, as installed on Ubuntu
    # 24.04 and Debian 12.
    child = (
        "import os\n"
        "import sys\n"
        "from mosey.ignore_files import split_ignore_file\n"
        "encoding = sys.getfilesystemencoding()\n"
        "assert encoding != 'utf-8', encoding\n"
        "assert split_ignore_file(b'\\xef\\xbb\\xbfa\\n') == ['a']\n"
        "name = b'caf\\xc3\\xa9'\n"
        "assert split_ignore_file(b'\\xef\\xbb\\xbf' + name) == [os.fsdecode(name)]\n"
    )

    # The child starts with `-S`, so it skips the virtual environment's `.pth` files.
    # Under the C locale it can't use a path in them that isn't ASCII (Python 3.11
    # crashes, and later versions can't find mosey), so `PYTHONPATH` points it straight
    # at mosey instead.
    subprocess.run(
        [sys.executable, "-S", "-X", "utf8=0", "-c", child],
        check=True,
        env={
            **os.environ,
            "LC_ALL": "C",
            "PYTHONCOERCECLOCALE": "0",
            "PYTHONPATH": os.path.dirname(os.path.dirname(mosey.__file__)),
        },
    )


@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"caf\xc3\xa9\n",
            ["café"],
            id="non-ascii",
        ),
        # "café" above spells "é" as the single code point U+00E9, and this spells it as
        # "e" then the combining accent U+0301. Lines are never normalised, so this
        # stays as it is.
        param(
            b"cafe\xcc\x81\n",
            ["cafe\u0301"],
            id="decomposed",
        ),
        param(
            b"\xf0\x9f\x98\x80\n",
            ["\U0001f600"],
            id="four-byte-character",
        ),
        param(
            b"caf\xe9\n",
            ["caf\udce9"],
            id="invalid",
        ),
    ],
)
def test_split_ignore_file__decoding(data: bytes, expect: list[str]) -> None:
    """Lines are decoded with the file system encoding, escaping undecodable bytes."""
    assert split_ignore_file(data) == expect


def test_split_ignore_file__every_byte() -> None:
    """Every byte decodes without raising, and nothing is lost."""
    # Every byte except the newline, which would split the line, and the zero byte,
    # which would drop it. The carriage return isn't at the end, so it's kept like any
    # other byte.
    data = bytes(byte for byte in range(256) if byte not in b"\n\x00")
    [line] = split_ignore_file(data)
    assert line.encode(FS_ENCODING, "surrogateescape") == data
