"""Unit tests for the `Mosey.walk` function with an ignore-file name."""

import errno
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from pytest import mark, param, raises, skip

import mosey
from mosey import Mosey
from tests.file_system_helpers import (
    make_broken_symlink,
    make_symlink_to_file,
    make_tree,
    relative_paths,
    skip_if_windows_cannot_create,
    skip_if_windows_git_warns,
    symlink_target,
    write_ignore_files,
)
from tests.git_oracle import ESCAPED_SLASH, ONE_BYTE, git_list_files
from tests.markers import needs_git, needs_posix_permissions, needs_symlinks


class IgnoreCase(NamedTuple):
    """Ignore-files, the rest of a tree, and the files a walk of it yields."""

    ignore_files: dict[str, list[str] | bytes]
    """Each ignore-file's lines or exact bytes, by directory.

    Each directory is "" for the root, or a "/"-separated path. Every ignore-file is
    named "ignore". Lines are written as UTF-8, each followed by a newline.
    """

    tree: list[str]
    """The rest of the tree, as `make_tree` takes it."""

    listed: list[str]
    """The "/"-separated paths of the files the walk yields, in walk order."""

    name: str = "ignore"
    """The ignore-file name that the walk and Git are given."""

    divergence: str | None = None
    """Why Git lists differently, if it does."""


ZERO_BYTE = "Git cuts a line at its first zero byte, and Mosey drops the whole line"
"""Why Git reads a line holding a zero byte differently."""

DIFFERENTLY_CASED = (
    "Git opens the ignore-file by name, and the file system ignores case"
    if sys.platform in ("darwin", "win32")
    else None
)
"""Why Git reads a differently-cased ignore-file on macOS and Windows, or `None`."""

POWERSHELL_LINE = "*.log\r\n".encode("utf-16-le")
"""The line that Windows PowerShell 5.1's `echo "*.log" >> ignore` appends.

It's written in UTF-16, with a zero byte after every character.
"""


def build(root: Path, case: IgnoreCase) -> None:
    """Build a case's ignore-files and tree.

    Args:
        root: Path to the directory to build them in.
        case: The case to build.
    """
    skip_if_windows_cannot_create([*case.ignore_files, *case.tree])

    write_ignore_files(root, case.ignore_files)
    make_tree(root, *case.tree)


PRECEDENCE = [
    param(
        IgnoreCase(
            ignore_files={"": ["*.log"], "sub": ["!keep.log"]},
            tree=["a.log", "keep.log", "sub/a.log", "sub/keep.log"],
            listed=["ignore", "sub/ignore", "sub/keep.log"],
        ),
        id="deeper-re-includes",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["*.log", "!keep.log"], "sub": ["keep.log"]},
            tree=["a.log", "keep.log", "sub/a.log", "sub/keep.log"],
            listed=["ignore", "keep.log", "sub/ignore"],
        ),
        id="deeper-ignores",
    ),
    # "a" re-includes logs below it, "a/b" re-includes temporary files, and "a/b/c" has
    # no ignore-file, so it falls through to both.
    param(
        IgnoreCase(
            ignore_files={"": ["*.log", "*.tmp"], "a": ["!*.log"], "a/b": ["!*.tmp"]},
            tree=[
                "x.log",
                "x.tmp",
                "a/x.log",
                "a/x.tmp",
                "a/b/x.log",
                "a/b/x.tmp",
                "a/b/c/x.log",
                "a/b/c/x.tmp",
            ],
            listed=[
                "a/b/c/x.log",
                "a/b/c/x.tmp",
                "a/b/ignore",
                "a/b/x.log",
                "a/b/x.tmp",
                "a/ignore",
                "a/x.log",
                "ignore",
            ],
        ),
        id="three-levels",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["*.log"], "a/b/c": ["!keep.log"]},
            tree=[
                "keep.log",
                "a/keep.log",
                "a/b/keep.log",
                "a/b/c/keep.log",
                "a/b/c/d/keep.log",
            ],
            listed=[
                "a/b/c/d/keep.log",
                "a/b/c/ignore",
                "a/b/c/keep.log",
                "ignore",
            ],
        ),
        id="deep-re-include",
    ),
    # Both files' rules reach "a/b", which has no ignore-file of its own.
    param(
        IgnoreCase(
            ignore_files={"": ["*.log"], "a": ["*.tmp"]},
            tree=["a/b/x.log", "a/b/x.tmp", "a/b/y", "a/x.tmp"],
            listed=["a/b/y", "a/ignore", "ignore"],
        ),
        id="two-files-reach-below",
    ),
    # A nested ignore-file's rules end with its directory, so "b" is walked as if "a"
    # had none.
    param(
        IgnoreCase(
            ignore_files={"a": ["*.log"]},
            tree=["a/x.log", "a/b/x.log", "b/x.log", "x.log"],
            listed=["a/ignore", "b/x.log", "x.log"],
        ),
        id="sibling",
    ),
    # A nested ignore-file with no rules leaves the ones above it in charge.
    param(
        IgnoreCase(
            ignore_files={"": ["*.log"], "sub": ["# Only a comment"]},
            tree=["a.log", "sub/a.log", "sub/b"],
            listed=["ignore", "sub/b", "sub/ignore"],
        ),
        id="nested-file-without-rules",
    ),
]


@mark.parametrize("case", PRECEDENCE)
def test_walk__precedence(tmp_path: Path, case: IgnoreCase) -> None:
    """The deepest ignore-file with a line that matches decides."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


ANCHORING = [
    param(
        IgnoreCase(
            ignore_files={"sub": ["/top"]},
            tree=["top", "sub/top", "sub/x/top"],
            listed=["sub/ignore", "sub/x/top", "top"],
        ),
        id="nested-anchored",
    ),
    # A wrong prefix for a nested ignore-file only shows when its anchored line reaches
    # more than one level down.
    param(
        IgnoreCase(
            ignore_files={"a/b": ["/c/d/x"]},
            tree=["c/d/x", "a/b/c/d/x", "a/b/c/d/y", "a/b/e/c/d/x"],
            listed=["a/b/c/d/y", "a/b/e/c/d/x", "a/b/ignore", "c/d/x"],
        ),
        id="deep-nested-anchored",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["/a/b/x", "a/b/y"]},
            tree=["a/b/x", "a/b/y", "a/b/z", "c/a/b/x", "c/a/b/y"],
            listed=["a/b/z", "c/a/b/x", "c/a/b/y", "ignore"],
        ),
        id="anchored-two-levels",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["a/**/z"]},
            tree=["a/z", "a/b/c/d/y", "a/b/c/d/z", "x/a/z"],
            listed=["a/b/c/d/y", "ignore", "x/a/z"],
        ),
        id="double-star-deep",
    ),
    # Only the directories strictly inside "a" are ignored, not the files in it.
    param(
        IgnoreCase(
            ignore_files={"": ["a/**/"]},
            tree=["a/d", "a/b/c", "a/b/e/f", "x/a/b/g"],
            listed=["a/d", "ignore", "x/a/b/g"],
        ),
        id="double-star-directories",
    ),
    # An escaped "/" is a "/", so this line means "**/a", which matches "a" at any
    # depth, the root included.
    param(
        IgnoreCase(
            ignore_files={"": ["**\\/a"]},
            tree=["a", "b", "x/a", "x/y/a"],
            listed=["b", "ignore"],
            divergence=ESCAPED_SLASH,
        ),
        id="double-star-escaped-slash",
    ),
]


@mark.parametrize("case", ANCHORING)
def test_walk__anchoring(tmp_path: Path, case: IgnoreCase) -> None:
    """A line with a "/" before its end matches the path from its file's directory."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


OWN_FILE = [
    # An ignore-file is an ordinary file, so its own rules can drop it, and they still
    # apply.
    param(
        IgnoreCase(
            ignore_files={"": ["ignore", "a"]},
            tree=["a", "b"],
            listed=["b"],
        ),
        id="ignores-itself",
    ),
    param(
        IgnoreCase(
            ignore_files={"sub": ["ignore", "a"]},
            tree=["a", "sub/a", "sub/b"],
            listed=["a", "sub/b"],
        ),
        id="ignores-itself-nested",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["ignore", "*.log"], "sub": ["!keep.log"]},
            tree=["a.log", "b", "sub/a.log", "sub/keep.log"],
            listed=["b", "sub/keep.log"],
        ),
        id="ignored-from-above",
    ),
    # A directory is judged only by the ignore-files above it, never by its own...
    param(
        IgnoreCase(
            ignore_files={"sub": ["sub"]},
            tree=["x", "sub/a", "sub/sub/b"],
            listed=["sub/a", "sub/ignore", "x"],
        ),
        id="names-own-directory",
    ),
    # ...and the root is never judged at all, so "*" doesn't stop the walk.
    param(
        IgnoreCase(
            ignore_files={"": ["*", "!keep"]},
            tree=["keep", "x", "sub/keep"],
            listed=["keep"],
        ),
        id="root-never-judged",
    ),
]


@mark.parametrize("case", OWN_FILE)
def test_walk__own_file(tmp_path: Path, case: IgnoreCase) -> None:
    """An ignore-file is a file like any other, and never judges its own directory."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


DIRECTORIES = [
    # Ignoring never reorders what's left: "a/x" still comes after "a.txt".
    param(
        IgnoreCase(
            ignore_files={"": ["*.log"]},
            tree=["a-b", "a.log", "a.txt", "a/x", "a/y.log"],
            listed=["a-b", "a.txt", "a/x", "ignore"],
        ),
        id="order-kept",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["build/", "!build/keep.txt"]},
            tree=["build/keep.txt", "build/x.txt", "keep.txt"],
            listed=["ignore", "keep.txt"],
        ),
        id="ignored-directory",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["build/*", "!build/keep.txt"]},
            tree=["build/keep.txt", "build/x.txt", "keep.txt"],
            listed=["build/keep.txt", "ignore", "keep.txt"],
        ),
        id="ignored-contents",
    ),
    # "logs" is ignored, so its own ignore-file is never read.
    param(
        IgnoreCase(
            ignore_files={"": ["*.log", "logs/"], "logs": ["!*.log"]},
            tree=["a.log", "keep", "logs/b.log", "logs/c"],
            listed=["ignore", "keep"],
        ),
        id="ignored-directory-not-read",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["build/"], "sub": ["!build/"]},
            tree=["build/a", "sub/build/a"],
            listed=["ignore", "sub/build/a", "sub/ignore"],
        ),
        id="deeper-re-includes-directory",
    ),
    # Everything is ignored except directories, which are walked, and text files.
    param(
        IgnoreCase(
            ignore_files={"": ["*", "!*/", "!*.txt"]},
            tree=["a.txt", "b.log", "sub/c.txt", "sub/d.log", "sub/e/f.txt"],
            listed=["a.txt", "sub/c.txt", "sub/e/f.txt"],
        ),
        id="allow-list",
    ),
    # A directory named like the ignore-file is walked like any other, and its own
    # ignore-file is read.
    param(
        IgnoreCase(
            ignore_files={"sub/ignore": ["a"]},
            tree=["x", "sub/ignore/a", "sub/ignore/b"],
            listed=["sub/ignore/b", "sub/ignore/ignore", "x"],
        ),
        id="directory-named-like-ignore-file",
    ),
]


@mark.parametrize("case", DIRECTORIES)
def test_walk__directories(tmp_path: Path, case: IgnoreCase) -> None:
    """An ignored directory is never walked, and what's left keeps its order."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


RAW_NAMES = [
    param(
        IgnoreCase(
            ignore_files={"": ["*.TXT"]},
            tree=["a.txt", "b.TXT"],
            listed=["a.txt", "ignore"],
        ),
        id="case-sensitive",
    ),
    # Names and patterns are never normalised. The pattern spells "é" as the single
    # character U+00E9, and the root's file spells it as "e" followed by U+0301, a
    # combining accent. Only the file in "sub" is spelled like the pattern.
    param(
        IgnoreCase(
            ignore_files={"": ["café"]},
            tree=["cafe\u0301", "sub/café"],
            listed=["cafe\u0301", "ignore"],
        ),
        id="decomposed-name",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["cafe\u0301"]},
            tree=["café", "sub/cafe\u0301"],
            listed=["café", "ignore"],
        ),
        id="composed-name",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["caf?"]},
            tree=["cafe", "café", "cafex"],
            listed=["cafex", "ignore"],
            divergence=ONE_BYTE,
        ),
        id="question-mark-non-ascii",
    ),
]


@mark.parametrize("case", RAW_NAMES)
def test_walk__raw_names(tmp_path: Path, case: IgnoreCase) -> None:
    """Names and patterns are compared exactly as written, and never normalised."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


FILE_FORMAT = [
    param(
        IgnoreCase(
            ignore_files={"sub": b"\xef\xbb\xbf*.log\r\n!keep.log\r\n"},
            tree=["a.log", "sub/a.log", "sub/keep.log"],
            listed=["a.log", "sub/ignore", "sub/keep.log"],
        ),
        id="bom-and-crlf",
    ),
    # The appended line, and the zero byte that starts the line after it, are dropped.
    param(
        IgnoreCase(
            ignore_files={"sub": b"a\n" + POWERSHELL_LINE},
            tree=["x.log", "sub/a", "sub/b.log", "sub/c"],
            listed=["sub/b.log", "sub/c", "sub/ignore", "x.log"],
            divergence=ZERO_BYTE,
        ),
        id="powershell",
    ),
    # Without a final newline, the file's last line joins the appended one.
    param(
        IgnoreCase(
            ignore_files={"": b"a" + POWERSHELL_LINE},
            tree=["a", "ab", "b.log"],
            listed=["a", "ab", "b.log", "ignore"],
            divergence=ZERO_BYTE,
        ),
        id="powershell-no-final-newline",
    ),
    param(
        IgnoreCase(
            ignore_files={"": b"ab\x00cd\nx\n"},
            tree=["ab", "abcd", "x", "y"],
            listed=["ab", "abcd", "ignore", "y"],
            divergence=ZERO_BYTE,
        ),
        id="zero-byte",
    ),
    # A line holding a zero byte matches nothing, even inside brackets, where the zero
    # byte would otherwise be a member like any other.
    param(
        IgnoreCase(
            ignore_files={"": b"[!\x00]\n"},
            tree=["a", "ab"],
            listed=["a", "ab", "ignore"],
        ),
        id="zero-byte-in-brackets",
    ),
]


@mark.parametrize("case", FILE_FORMAT)
def test_walk__file_format(tmp_path: Path, case: IgnoreCase) -> None:
    """A BOM, Windows line endings and lines holding a zero byte are handled."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


NAMES = [
    # Only a file with exactly the given name is read.
    param(
        IgnoreCase(
            ignore_files={"": ["a"], "sub": ["b"]},
            tree=["a", "b", "sub/a", "sub/b"],
            listed=["a", "b", "ignore", "sub/a", "sub/b", "sub/ignore"],
            name="rules",
        ),
        id="other-name",
    ),
    param(
        IgnoreCase(
            ignore_files={"": ["a"], "sub": ["b"]},
            tree=["a", "b", "sub/a", "sub/b"],
            listed=["a", "b", "ignore", "sub/a", "sub/b", "sub/ignore"],
            name="Ignore",
            divergence=DIFFERENTLY_CASED,
        ),
        id="differently-cased-name",
    ),
]


@mark.parametrize("case", NAMES)
def test_walk__names(tmp_path: Path, case: IgnoreCase) -> None:
    """Only a file with exactly the given name is read as an ignore-file."""
    build(tmp_path, case)
    assert relative_paths(tmp_path, case.name) == case.listed


@needs_git
@mark.parametrize(
    "case",
    [
        *PRECEDENCE,
        *ANCHORING,
        *OWN_FILE,
        *DIRECTORIES,
        *RAW_NAMES,
        *FILE_FORMAT,
        *NAMES,
    ],
)
def test_walk__git(tmp_path: Path, case: IgnoreCase) -> None:
    """Git lists exactly the files that the walk yields."""
    build(tmp_path, case)

    skip_if_windows_git_warns(
        tmp_path,
        case.name,
    )

    listed = git_list_files(tmp_path, case.name)

    if case.divergence:
        # Git should still list something different, or the reason no longer holds.
        assert listed != case.listed
        skip(case.divergence)

    assert listed == case.listed


@mark.parametrize(
    "list_paths",
    [
        param(relative_paths, id="walk"),
        param(git_list_files, marks=needs_git, id="git"),
    ],
)
def test_walk__example(
    tmp_path: Path,
    list_paths: Callable[[Path, str], list[str]],
) -> None:
    """The ignore-files page's example lists the files the page says."""
    # The example from the ignore-files page, with its ignore-files named as the page
    # names them.
    make_tree(
        tmp_path,
        "build/app.log",
        "debug.log",
        "readme.md",
        "todo.txt",
        "tools/build",
        "tools/debug.log",
        "tools/keep.log",
        "tools/todo.txt",
    )

    (tmp_path / ".walkignore").write_bytes(b"*.log\nbuild/\n/todo.txt\n")
    (tmp_path / "build" / ".walkignore").write_bytes(b"!app.log\n")
    (tmp_path / "tools" / ".walkignore").write_bytes(b"!keep.log\n")

    assert list_paths(tmp_path, ".walkignore") == [
        ".walkignore",
        "readme.md",
        "tools/.walkignore",
        "tools/build",
        "tools/keep.log",
        "tools/todo.txt",
    ]


@needs_symlinks
def test_walk__ignore_file_is_broken_symlink(tmp_path: Path) -> None:
    """A broken symlinked ignore-file raises when the walk reaches its directory."""
    make_tree(tmp_path, "a", "b/c", "d")
    make_broken_symlink(tmp_path / "b" / "ignore")
    steps = Mosey(ignore_filename="ignore").walk(tmp_path)

    # Everything before "b" is yielded...
    assert next(steps).relative_as_posix == "a"

    # ...and then the walk stops.
    with raises(FileNotFoundError) as raised:
        next(steps)

    assert raised.value.filename == os.fspath(tmp_path / "b" / "ignore")


@needs_symlinks
def test_walk__ignore_file_is_symlink(tmp_path: Path) -> None:
    """A symlinked ignore-file is yielded as a file, and its rules apply."""
    path = tmp_path / "sub" / "ignore"
    make_tree(tmp_path, "a.log", "sub/b.log", "sub/c")
    make_symlink_to_file(path)
    symlink_target(path).write_bytes(b"*.log\n")

    assert relative_paths(tmp_path, "ignore") == [
        "a.log",
        "sub/c",
        "sub/ignore",
        "sub/ignore.target",
    ]


@needs_posix_permissions
def test_walk__ignore_file_read_is_denied(tmp_path: Path) -> None:
    """An unreadable ignore-file raises from the iterator, not from `walk`."""
    file = tmp_path / "ignore"
    file.write_bytes(b"a\n")

    # Write but not read.
    file.chmod(0o200)

    try:
        # The root's ignore-file isn't read until the first step is requested...
        steps = Mosey(ignore_filename="ignore").walk(tmp_path)

        # ...so that's when the error comes.
        with raises(PermissionError) as raised:
            next(steps)

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == os.fspath(file)
    finally:
        # Leave the file readable, as we found it.
        file.chmod(0o600)


def test_walk__ignore_filename(tmp_path: Path) -> None:
    """The walk reads the ignore-files with the name it's given, and no others."""
    # The root's file named "ignore" would drop everything, so a walk that read it
    # couldn't yield the rest. "sub" has no such file, so a walk that only read a
    # directory's file when one named "ignore" was there would yield "sub/b".
    write_ignore_files(tmp_path, {"": ["*"]})
    make_tree(tmp_path, "a", "b", "sub/a", "sub/b")
    (tmp_path / "rules").write_bytes(b"a\n")
    (tmp_path / "sub" / "rules").write_bytes(b"b\n")

    assert relative_paths(tmp_path, "rules") == ["b", "ignore", "rules", "sub/rules"]


@needs_posix_permissions
def test_walk__ignored_directory_listing_is_denied(tmp_path: Path) -> None:
    """An ignored directory is never listed, so it doesn't matter if it can't be."""
    make_tree(tmp_path, "a", "b/x", "c")
    write_ignore_files(tmp_path, {"": ["b/"]})
    denied = tmp_path / "b"

    # Write and search ("execute") but not read, so "b" can't be listed.
    denied.chmod(0o300)

    try:
        # Prove that "b" can't be listed.
        with raises(PermissionError):
            relative_paths(tmp_path)

        assert relative_paths(tmp_path, "ignore") == ["a", "c", "ignore"]
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        denied.chmod(0o700)


def test_walk__lazy_directory_ignore_file(tmp_path: Path) -> None:
    """A directory's ignore-file isn't read until the walk reaches the directory."""
    make_tree(tmp_path, "a", "b/x", "b/y")
    write_ignore_files(tmp_path, {"b": ["x"]})
    steps = Mosey(ignore_filename="ignore").walk(tmp_path)

    assert next(steps).relative_as_posix == "a"

    # The walk has read the root, so it knows "b" exists, but it hasn't read "b"
    # itself yet.
    write_ignore_files(tmp_path, {"b": ["y"]})

    assert [step.relative_as_posix for step in steps] == ["b/ignore", "b/x"]


def test_walk__lazy_root_ignore_file(tmp_path: Path) -> None:
    """The root's ignore-file isn't read until the first step is requested."""
    make_tree(tmp_path, "a", "b")
    write_ignore_files(tmp_path, {"": ["a"]})
    steps = Mosey(ignore_filename="ignore").walk(tmp_path)
    write_ignore_files(tmp_path, {"": ["b"]})

    assert [step.relative_as_posix for step in steps] == ["a", "ignore"]


@mark.parametrize(
    "make",
    [
        param(Mosey, id="default"),
        param(lambda: Mosey(ignore_filename=None), id="none"),
    ],
)
def test_walk__no_ignore_filename(tmp_path: Path, make: Callable[[], Mosey]) -> None:
    """Without an ignore-file name, no file is read as an ignore-file."""
    make_tree(tmp_path, "a", "b/c")
    write_ignore_files(tmp_path, {"": ["a"], "b": ["*"]})

    assert [step.relative_as_posix for step in make().walk(tmp_path)] == [
        "a",
        "b/c",
        "b/ignore",
        "ignore",
    ]


@mark.skipif(
    sys.platform != "linux",
    reason="Only Linux takes its file system encoding from the locale",
)
def test_walk__not_utf8(tmp_path: Path) -> None:
    """Names and lines decode alike when the file system encoding isn't UTF-8."""
    # Every CI runner's file system encoding is UTF-8, so we walk in a child interpreter
    # that has UTF-8 mode and locale coercion switched off, so that it takes its
    # encoding from the C locale instead: ASCII. That's also how Python starts inside
    # Apache's mod_wsgi, as installed on Ubuntu 24.04 and Debian 12.
    #
    # ASCII can't decode either of the two bytes that spell "é", so the child sees each
    # one as a placeholder character, in a name and in a line alike. So there, "caf?"
    # misses "café" and "caf??" matches it, the other way round from UTF-8, and a line
    # holding the name's bytes still matches the name.
    make_tree(
        tmp_path,
        "one/cafe",
        "one/café",
        "two/cafe",
        "two/café",
        "three/cafe",
        "three/café",
    )
    (tmp_path / "ignore").write_bytes(b"/one/caf?\n/two/caf??\n/three/caf\xc3\xa9\n")

    # The child writes each path's raw bytes, so that the comparison below doesn't
    # depend on how either interpreter decodes them.
    child = (
        "import os\n"
        "import sys\n"
        "from mosey import Mosey\n"
        "encoding = sys.getfilesystemencoding()\n"
        "assert encoding != 'utf-8', encoding\n"
        "steps = Mosey(ignore_filename='ignore').walk(sys.argv[1])\n"
        "paths = [os.fsencode(step.relative_as_posix) for step in steps]\n"
        "sys.stdout.buffer.write(b'\\0'.join(paths))\n"
    )

    # The child starts with `-S`, so it skips the virtual environment's `.pth` files.
    # Under the C locale it can't use a path in them that isn't ASCII (Python 3.11
    # crashes, and later versions can't find mosey), so `PYTHONPATH` points it straight
    # at mosey instead.
    walked = subprocess.run(
        [sys.executable, "-S", "-X", "utf8=0", "-c", child, os.fspath(tmp_path)],
        check=True,
        stdout=subprocess.PIPE,
        env={
            **os.environ,
            "LC_ALL": "C",
            "PYTHONCOERCECLOCALE": "0",
            "PYTHONPATH": os.path.dirname(os.path.dirname(mosey.__file__)),
        },
    ).stdout.split(b"\0")

    # Git lists the same files, since it reads names and lines one byte at a time.
    assert walked == [b"ignore", b"one/caf\xc3\xa9", b"three/cafe", b"two/cafe"]


def test_walk__same_root_twice(tmp_path: Path) -> None:
    """Each walk reads the ignore-files again, so it sees any change since the last."""
    make_tree(tmp_path, "a", "b")
    write_ignore_files(tmp_path, {"": ["a"]})
    walker = Mosey(ignore_filename="ignore")

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["b", "ignore"]

    write_ignore_files(tmp_path, {"": ["b"]})

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == ["a", "ignore"]


@needs_posix_permissions
def test_walk__search_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when a directory's ignore-file can't be looked up."""
    make_tree(tmp_path, "a", "sub/b", "sub/ignore", "z")
    path = tmp_path / "sub"

    # Read and write but not search ("execute"), so the directory's names can be listed
    # but nothing inside it can be opened. Without an ignore-file name, "sub/b" and
    # "sub/ignore" would be yielded, since listing a directory doesn't need search.
    path.chmod(0o600)

    try:
        steps = Mosey(ignore_filename="ignore").walk(tmp_path)

        assert next(steps).relative_as_posix == "a"

        with raises(PermissionError) as raised:
            next(steps)

        assert raised.value.filename == os.fspath(path / "ignore")
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)
