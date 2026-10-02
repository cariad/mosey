"""Unit tests for the `read_directory` function."""

import errno
import os
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from pytest import mark, param, raises

from mosey.candidate import Candidate
from mosey.directories import list_candidates, read_directory
from mosey.rules import Layers
from tests.file_system_helpers import (
    make_broken_symlink,
    make_fifo,
    make_junction,
    make_symlink_loop,
    make_symlink_to_directory,
    make_symlink_to_file,
    make_tree,
    skip_if_windows_cannot_create,
    symlink_target,
    write_ignore_files,
)
from tests.git_oracle import git_list_files
from tests.markers import (
    needs_fifos,
    needs_git,
    needs_junctions,
    needs_posix_permissions,
    needs_symlinks,
)
from tests.timeouts import alarm


class DirectoryCase(NamedTuple):
    """Ignore-files, a tree, a directory in it, and what reading that returns."""

    ignore_files: dict[str, list[str]]
    """Each ignore-file's lines, by directory: "" for the root, or a "/"-separated path.

    Only the case's directory and the directories above it can have one.
    """

    tree: list[str]
    """The rest of the tree, as `make_tree` takes it."""

    directory: str
    """The "/"-separated path of the directory to read, or "" for the root."""

    kept: list[str]
    """The kept candidates' names in walk order, each directory's ending with "/"."""

    prefixes: list[str]
    """The prefixes of the layers it returns, deepest first."""


def prefixes(layers: Layers) -> list[str]:
    """Return each layer's prefix.

    Args:
        layers: The layers.

    Returns:
        The prefixes, in the layers' order.
    """
    # A layer's rules hold compiled patterns' `fullmatch` methods, which only compare
    # equal while `re` caches the patterns, so we compare layers by their prefixes
    # instead.
    return [prefix for prefix, _, _ in layers]


def written(candidates: list[Candidate]) -> list[str]:
    """Return candidates' names as `DirectoryCase.kept` writes them.

    Args:
        candidates: The candidates.

    Returns:
        Each candidate's name, with a "/" after a directory's.
    """
    return [f"{name}/" if is_dir else name for name, is_dir in candidates]


def read_case(root: Path, case: DirectoryCase) -> tuple[list[str], list[str]]:
    """Build a case's tree, and read its directory the way a walk would.

    The root and each directory down to the case's are read in turn, each with the
    layers that its parent returned.

    Args:
        root: Path to the directory to build the tree in.
        case: The case to build and read.

    Returns:
        The names of the candidates kept in the case's directory, written as
        `DirectoryCase.kept` writes them, and the prefixes of the layers returned.
    """
    write_ignore_files(root, case.ignore_files)
    make_tree(root, *case.tree)

    directory = os.fspath(root)
    prefix = ""
    layers: Layers = ()

    for name in case.directory.split("/") if case.directory else []:
        candidates, layers = read_directory(directory, prefix, layers, "ignore")

        # A walk only reads a directory that its parent kept.
        assert (name, True) in candidates

        directory = os.path.join(directory, name)
        prefix += f"{name}/"

    candidates, layers = read_directory(directory, prefix, layers, "ignore")
    return written(candidates), prefixes(layers)


ABSENT = [
    param(
        DirectoryCase(
            ignore_files={},
            tree=["a", "b/"],
            directory="",
            kept=["a", "b/"],
            prefixes=[],
        ),
        id="absent",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"]},
            tree=["sub/a.log", "sub/b"],
            directory="sub",
            kept=["b"],
            prefixes=[""],
        ),
        id="absent-below-root",
    ),
    param(
        DirectoryCase(
            ignore_files={"a": ["*.log"]},
            tree=["a/b/x.log", "a/b/y"],
            directory="a/b",
            kept=["y"],
            prefixes=["a/"],
        ),
        id="absent-below-middle",
    ),
]


@mark.parametrize("case", ABSENT)
def test_read_directory__absent(tmp_path: Path, case: DirectoryCase) -> None:
    """Without an ignore-file, the candidates are judged by the layers it's given."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


# An ignore-file with no line left adds no layer, but it's still a candidate, judged by
# the layers above like any other file.
NOTHING_LEFT = [
    param(
        DirectoryCase(
            ignore_files={"": []},
            tree=["a"],
            directory="",
            kept=["a", "ignore"],
            prefixes=[],
        ),
        id="empty",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"], "sub": ["# *.txt", "#*"]},
            tree=["sub/a.log", "sub/b.txt"],
            directory="sub",
            kept=["b.txt", "ignore"],
            prefixes=[""],
        ),
        id="only-comments",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["[a", "!"]},
            tree=["[a", "b"],
            directory="",
            kept=["[a", "b", "ignore"],
            prefixes=[],
        ),
        id="only-malformed-lines",
    ),
    # The empty root file adds no layer, so none is passed down to "sub".
    param(
        DirectoryCase(
            ignore_files={"": [], "sub": ["a"]},
            tree=["sub/a", "sub/b"],
            directory="sub",
            kept=["b", "ignore"],
            prefixes=["sub/"],
        ),
        id="empty-above",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["ignore"], "sub": []},
            tree=["sub/a"],
            directory="sub",
            kept=["a"],
            prefixes=[""],
        ),
        id="empty-ignored-from-above",
    ),
]


@mark.parametrize("case", NOTHING_LEFT)
def test_read_directory__nothing_left(tmp_path: Path, case: DirectoryCase) -> None:
    """An ignore-file with no line left adds no layer."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


OWN_RULES = [
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"]},
            tree=["a.log", "b.txt", "c/"],
            directory="",
            kept=["b.txt", "c/", "ignore"],
            prefixes=[""],
        ),
        id="root",
    ),
    param(
        DirectoryCase(
            ignore_files={"sub": ["*.log"]},
            tree=["a.log", "sub/a.log", "sub/b.txt"],
            directory="sub",
            kept=["b.txt", "ignore"],
            prefixes=["sub/"],
        ),
        id="below-root",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*.log", "!keep.log"]},
            tree=["a.log", "keep.log"],
            directory="",
            kept=["ignore", "keep.log"],
            prefixes=[""],
        ),
        id="re-include",
    ),
]


@mark.parametrize("case", OWN_RULES)
def test_read_directory__own_rules(tmp_path: Path, case: DirectoryCase) -> None:
    """A directory's own ignore-file judges its candidates."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


NESTED = [
    param(
        DirectoryCase(
            ignore_files={"sub": ["/top"]},
            tree=["sub/top", "sub/x/"],
            directory="sub",
            kept=["ignore", "x/"],
            prefixes=["sub/"],
        ),
        id="anchored-below-root",
    ),
    # The root's "/top" only matches the root's own "top".
    param(
        DirectoryCase(
            ignore_files={"": ["/top"]},
            tree=["sub/top", "sub/x"],
            directory="sub",
            kept=["top", "x"],
            prefixes=[""],
        ),
        id="root-anchored-not-below",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["/sub/a"]},
            tree=["sub/a", "sub/b"],
            directory="sub",
            kept=["b"],
            prefixes=[""],
        ),
        id="root-anchored-path",
    ),
    param(
        DirectoryCase(
            ignore_files={"a": ["/b/top"]},
            tree=["a/b/top", "a/b/c"],
            directory="a/b",
            kept=["c"],
            prefixes=["a/"],
        ),
        id="middle-anchored-path",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"], "a": ["*.txt"], "a/b": ["*.md"]},
            tree=["a/b/x.log", "a/b/x.md", "a/b/x.py", "a/b/x.txt"],
            directory="a/b",
            kept=["ignore", "x.py"],
            prefixes=["a/b/", "a/", ""],
        ),
        id="three-files",
    ),
]


@mark.parametrize("case", NESTED)
def test_read_directory__nested(tmp_path: Path, case: DirectoryCase) -> None:
    """Each ignore-file's lines match from its own directory, at any depth below it."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


PRECEDENCE = [
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"], "sub": ["!keep.log"]},
            tree=["sub/a.log", "sub/keep.log"],
            directory="sub",
            kept=["ignore", "keep.log"],
            prefixes=["sub/", ""],
        ),
        id="deeper-re-includes",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*.log", "!a.log"], "sub": ["a.log"]},
            tree=["sub/a.log", "sub/b.log", "sub/c"],
            directory="sub",
            kept=["c", "ignore"],
            prefixes=["sub/", ""],
        ),
        id="deeper-ignores",
    ),
    # The deeper file has no line that matches, so the root's decides.
    param(
        DirectoryCase(
            ignore_files={"": ["*.log"], "sub": ["*.txt"]},
            tree=["sub/a.log", "sub/a.txt", "sub/b"],
            directory="sub",
            kept=["b", "ignore"],
            prefixes=["sub/", ""],
        ),
        id="falls-through",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["!x"], "a": ["x"], "a/b": ["y"]},
            tree=["a/b/x", "a/b/y", "a/b/z"],
            directory="a/b",
            kept=["ignore", "z"],
            prefixes=["a/b/", "a/", ""],
        ),
        id="falls-through-to-middle",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["build/"], "sub": ["!build/"]},
            tree=["sub/build/", "sub/x"],
            directory="sub",
            kept=["build/", "ignore", "x"],
            prefixes=["sub/", ""],
        ),
        id="deeper-re-includes-directory",
    ),
]


@mark.parametrize("case", PRECEDENCE)
def test_read_directory__precedence(tmp_path: Path, case: DirectoryCase) -> None:
    """The deepest ignore-file with a line that matches decides."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


OWN_FILE = [
    param(
        DirectoryCase(
            ignore_files={"": ["ignore", "*.log"]},
            tree=["a.log", "b"],
            directory="",
            kept=["b"],
            prefixes=[""],
        ),
        id="root-drops-itself",
    ),
    param(
        DirectoryCase(
            ignore_files={"sub": ["/ignore", "*.log"]},
            tree=["sub/a.log", "sub/b"],
            directory="sub",
            kept=["b"],
            prefixes=["sub/"],
        ),
        id="drops-itself",
    ),
    param(
        DirectoryCase(
            ignore_files={"sub": ["*", "!keep"]},
            tree=["sub/a", "sub/d/", "sub/keep"],
            directory="sub",
            kept=["keep"],
            prefixes=["sub/"],
        ),
        id="drops-itself-and-more",
    ),
    # Its own file has no line that matches it, so the root's decides.
    param(
        DirectoryCase(
            ignore_files={"": ["ignore"], "sub": ["*.log"]},
            tree=["sub/a.log", "sub/b"],
            directory="sub",
            kept=["b"],
            prefixes=["sub/", ""],
        ),
        id="dropped-from-above",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["ignore"], "sub": ["!ignore"]},
            tree=["sub/a"],
            directory="sub",
            kept=["a", "ignore"],
            prefixes=["sub/", ""],
        ),
        id="re-includes-itself",
    ),
]


@mark.parametrize("case", OWN_FILE)
def test_read_directory__own_file(tmp_path: Path, case: DirectoryCase) -> None:
    """An ignore-file is judged like any other file, and its rules apply either way."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


# The directory itself was judged by the layers above, when its parent was read.
OWN_DIRECTORY = [
    param(
        DirectoryCase(
            ignore_files={"sub": ["sub"]},
            tree=["sub/a", "sub/sub/"],
            directory="sub",
            kept=["a", "ignore"],
            prefixes=["sub/"],
        ),
        id="names-own-directory",
    ),
    param(
        DirectoryCase(
            ignore_files={"a": ["a/"]},
            tree=["a/a/", "a/b"],
            directory="a",
            kept=["b", "ignore"],
            prefixes=["a/"],
        ),
        id="names-own-directory-only",
    ),
]


@mark.parametrize("case", OWN_DIRECTORY)
def test_read_directory__own_directory(tmp_path: Path, case: DirectoryCase) -> None:
    """A directory's ignore-file judges what's inside it, never the directory itself."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


SUBDIRECTORIES = [
    param(
        DirectoryCase(
            ignore_files={"": ["build/"]},
            tree=["build/x", "src/x"],
            directory="",
            kept=["ignore", "src/"],
            prefixes=[""],
        ),
        id="subdirectory",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["build/"]},
            tree=["sub/build/x", "sub/y"],
            directory="sub",
            kept=["y"],
            prefixes=[""],
        ),
        id="subdirectory-below-root",
    ),
    # "build/*" drops what's inside "build", but not "build" itself.
    param(
        DirectoryCase(
            ignore_files={"": ["build/*", "!build/keep"]},
            tree=["build/a", "build/keep"],
            directory="build",
            kept=["keep"],
            prefixes=[""],
        ),
        id="contents",
    ),
]


@mark.parametrize("case", SUBDIRECTORIES)
def test_read_directory__subdirectories(tmp_path: Path, case: DirectoryCase) -> None:
    """A subdirectory is dropped like any other candidate."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


DIRECTORY_ONLY = [
    param(
        DirectoryCase(
            ignore_files={"": ["*.d/"]},
            tree=["f.d", "g.d/"],
            directory="",
            kept=["f.d", "ignore"],
            prefixes=[""],
        ),
        id="directory-only",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["*", "!*/"]},
            tree=["a", "b/"],
            directory="",
            kept=["b/"],
            prefixes=[""],
        ),
        id="negated-directory-only",
    ),
    param(
        DirectoryCase(
            ignore_files={"": ["/sub/y/"]},
            tree=["sub/x", "sub/y/"],
            directory="sub",
            kept=["x"],
            prefixes=[""],
        ),
        id="anchored-directory-only",
    ),
]


@mark.parametrize("case", DIRECTORY_ONLY)
def test_read_directory__directory_only(tmp_path: Path, case: DirectoryCase) -> None:
    """A line ending with "/" only drops directories."""
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


def test_read_directory__order(tmp_path: Path) -> None:
    """Dropping candidates never reorders the rest."""
    case = DirectoryCase(
        ignore_files={"": ["*.log"]},
        # Created in neither the expected order nor its reverse.
        tree=["b.txt", "Z", "ba", "b/", ".a", "B.log", "b_c", "b-c", "x.log"],
        directory="",
        # Uppercase before lowercase, then the byte after "b" decides the ties, with the
        # directory "b" sorting as "b/".
        kept=[".a", "Z", "b-c", "b.txt", "b/", "b_c", "ba", "ignore"],
        prefixes=[""],
    )

    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


@needs_git
@mark.parametrize(
    "case",
    [
        *ABSENT,
        *NOTHING_LEFT,
        *OWN_RULES,
        *NESTED,
        *PRECEDENCE,
        *OWN_FILE,
        *OWN_DIRECTORY,
        *SUBDIRECTORIES,
        *DIRECTORY_ONLY,
    ],
)
def test_read_directory__git(tmp_path: Path, case: DirectoryCase) -> None:
    """Git lists each candidate exactly when it's kept."""
    # Git shows a directory only through what it keeps inside. So if a case kept
    # nothing, Git's listing couldn't show that Git entered the directory at all.
    assert case.kept

    # Every ignore-file is named "ignore". On macOS and Windows, any entry named
    # "Ignore" would be that same file.
    names = [name for path in case.tree for name in path.split("/")]
    assert all(name.lower() != "ignore" for name in names)

    # Each subdirectory gets an ignore-file below, so only the case's directory and the
    # directories above it can have one of the case's own.
    assert all(
        not key or f"{case.directory}/".startswith(f"{key}/")
        for key in case.ignore_files
    )

    skip_if_windows_cannot_create(case.tree)

    write_ignore_files(tmp_path, case.ignore_files)
    make_tree(tmp_path, *case.tree)

    directory = tmp_path / case.directory
    candidates = list_candidates(os.fspath(directory))

    # Git only shows a directory through a file inside it. So each subdirectory gets an
    # ignore-file that keeps itself. A directory is never judged by its own ignore-file,
    # so this can't change whether the subdirectory is kept.
    write_ignore_files(
        directory,
        {name: ["!/ignore"] for name, is_dir in candidates if is_dir},
    )

    listed = git_list_files(tmp_path, "ignore")
    prefix = f"{case.directory}/" if case.directory else ""

    # A file is kept when Git lists it, and a subdirectory when Git lists the
    # ignore-file inside it.
    kept = [
        (name, is_dir)
        for name, is_dir in candidates
        if (f"{prefix}{name}/ignore" if is_dir else prefix + name) in listed
    ]

    assert written(kept) == case.kept


@mark.parametrize(
    "case",
    [
        param(
            DirectoryCase(
                ignore_files={"": ["*.log"]},
                tree=["sub/ignore/", "sub/ignore.txt"],
                directory="sub",
                kept=["ignore.txt", "ignore/"],
                prefixes=[""],
            ),
            id="kept",
        ),
        param(
            DirectoryCase(
                ignore_files={"": ["ignore/"]},
                tree=["sub/ignore/", "sub/ignore.txt"],
                directory="sub",
                kept=["ignore.txt"],
                prefixes=[""],
            ),
            id="dropped",
        ),
    ],
)
def test_read_directory__directory_named_like_ignore_file(
    tmp_path: Path,
    case: DirectoryCase,
) -> None:
    """A directory with the ignore-file's name is a candidate directory, never read."""
    # Reading a directory as an ignore-file would raise. The directory sorts as
    # "ignore/", so after "ignore.txt".
    assert read_case(tmp_path, case) == (case.kept, case.prefixes)


@needs_symlinks
@mark.parametrize(
    ("make", "error"),
    [
        param(
            make_broken_symlink,
            FileNotFoundError,
            id="broken-symlink",
        ),
        # Linux and macOS open a directory but can't read it. Windows can't open it at
        # all.
        param(
            make_symlink_to_directory,
            OSError,
            id="symlink-to-directory",
        ),
        param(
            make_symlink_loop,
            OSError,
            id="symlink-loop",
        ),
    ],
)
def test_read_directory__ignore_file_cannot_be_read(
    tmp_path: Path,
    make: Callable[[Path], None],
    error: type[OSError],
) -> None:
    """An error reading the ignore-file rises unchanged, naming the ignore-file."""
    make(tmp_path / "ignore")
    directory = os.fspath(tmp_path)

    with raises(error) as raised:
        read_directory(directory, "", (), "ignore")

    assert raised.value.filename == os.path.join(directory, "ignore")


def test_read_directory__ignore_file_differently_cased(tmp_path: Path) -> None:
    """A file named like the ignore-file but in another case isn't read."""
    make_tree(tmp_path, "a")
    (tmp_path / "Ignore").write_bytes(b"a\n")

    # macOS and Windows would open "Ignore" if asked for "ignore", and drop "a".
    assert read_directory(os.fspath(tmp_path), "", (), "ignore") == (
        [("Ignore", False), ("a", False)],
        (),
    )


@needs_symlinks
@mark.parametrize(
    ("data", "expect"),
    [
        param(
            b"*.log\n",
            [("b", False), ("ignore", False), ("ignore.target", False)],
            id="rules-apply",
        ),
        param(
            b"ignore\n",
            [("a.log", False), ("b", False), ("ignore.target", False)],
            id="drops-itself",
        ),
    ],
)
def test_read_directory__ignore_file_is_symlink(
    tmp_path: Path,
    data: bytes,
    expect: list[Candidate],
) -> None:
    """A symlinked ignore-file is read through the link, and is still a candidate."""
    path = tmp_path / "ignore"
    make_symlink_to_file(path)
    symlink_target(path).write_bytes(data)
    make_tree(tmp_path, "a.log", "b")

    candidates, layers = read_directory(os.fspath(tmp_path), "", (), "ignore")

    assert candidates == expect
    assert prefixes(layers) == [""]


@needs_fifos
@needs_symlinks
def test_read_directory__ignore_file_is_symlink_to_fifo(tmp_path: Path) -> None:
    """A symlink to a FIFO adds no rules, without waiting for a writer."""
    path = tmp_path / "ignore"
    make_fifo(symlink_target(path))
    path.symlink_to(symlink_target(path))
    make_tree(tmp_path, "a")

    # If the open waits for a writer, the alarm interrupts it, and the test fails rather
    # than hangs.
    with alarm(1, "Waited for the FIFO to be opened for writing"):
        # The FIFO itself isn't a candidate.
        assert read_directory(os.fspath(tmp_path), "", (), "ignore") == (
            [("a", False), ("ignore", False)],
            (),
        )


def test_read_directory__ignore_filename(tmp_path: Path) -> None:
    """The ignore-file is found and read by the name it's given."""
    # No file named "ignore" here, so a name written into the code can't be found.
    make_tree(tmp_path, "a", "b")
    (tmp_path / "rules").write_bytes(b"a\n")

    candidates, layers = read_directory(os.fspath(tmp_path), "", (), "rules")

    assert candidates == [("b", False), ("rules", False)]
    assert prefixes(layers) == [""]


@mark.parametrize(
    ("make", "lines", "expect"),
    [
        param(
            make_symlink_to_directory,
            ["foo/"],
            [("foo", False), ("foo.target", True), ("ignore", False)],
            marks=needs_symlinks,
            id="symlink-directory-only-line",
        ),
        param(
            make_symlink_to_directory,
            ["foo"],
            [("foo.target", True), ("ignore", False)],
            marks=needs_symlinks,
            id="symlink-any-line",
        ),
        # A junction and its target both sort as directories: "foo.target/", "foo/".
        param(
            make_junction,
            ["foo/"],
            [("foo.target", True), ("ignore", False)],
            marks=needs_junctions,
            id="junction-directory-only-line",
        ),
    ],
)
def test_read_directory__link_to_directory(
    tmp_path: Path,
    make: Callable[[Path], None],
    lines: list[str],
    expect: list[Candidate],
) -> None:
    """A line ending with "/" drops a junction, but never a symlink."""
    make(tmp_path / "foo")
    write_ignore_files(tmp_path, {"": lines})

    candidates, _ = read_directory(os.fspath(tmp_path), "", (), "ignore")

    assert candidates == expect


@needs_posix_permissions
def test_read_directory__read_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when permissions deny reading the ignore-file."""
    file = tmp_path / "ignore"
    file.write_bytes(b"a\n")
    directory = os.fspath(tmp_path)

    # Write but not read.
    file.chmod(0o200)

    try:
        with raises(PermissionError) as raised:
            read_directory(directory, "", (), "ignore")

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == os.path.join(directory, "ignore")
    finally:
        # Leave the file readable, as we found it.
        file.chmod(0o600)


@needs_posix_permissions
def test_read_directory__search_is_denied(tmp_path: Path) -> None:
    """`PermissionError` is raised when the ignore-file can't be looked up."""
    path = tmp_path / "sub"
    make_tree(path, "a", "ignore")
    directory = os.fspath(path)

    # Read and write but not search ("execute"), so the directory's names can be listed
    # but nothing inside it can be opened.
    path.chmod(0o600)

    try:
        with raises(PermissionError) as raised:
            read_directory(directory, "sub/", (), "ignore")

        assert raised.value.errno == errno.EACCES
        assert raised.value.filename == os.path.join(directory, "ignore")
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)


@needs_posix_permissions
def test_read_directory__search_is_denied_without_ignore_file(tmp_path: Path) -> None:
    """Without an ignore-file, a directory that can't be searched is read as usual."""
    make_tree(tmp_path, "sub/a", "sub/b/", "sub/c.log", "sub/d/")
    write_ignore_files(tmp_path, {"": ["*.log", "b/"]})
    path = tmp_path / "sub"
    _, layers = read_directory(os.fspath(tmp_path), "", (), "ignore")

    # Read and write but not search ("execute"), so nothing inside the directory can be
    # looked up by its path. Opening the ignore-file would raise, and looking up "b"
    # would fail to find a directory, so "b/" wouldn't drop it.
    path.chmod(0o600)

    try:
        candidates, layers = read_directory(os.fspath(path), "sub/", layers, "ignore")

        assert candidates == [("a", False), ("d", True)]
        assert prefixes(layers) == [""]
    finally:
        # Restore access so pytest can clean up `tmp_path`.
        path.chmod(0o700)
