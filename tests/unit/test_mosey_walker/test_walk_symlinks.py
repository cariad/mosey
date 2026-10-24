"""Unit tests for the `MoseyWalker.walk` function with symlinks."""

from pathlib import Path

from pytest import mark, param

from mosey import Mosey, Walker
from tests.file_system_helpers import (
    build_walker,
    make_broken_symlink,
    make_junction,
    make_symlink_to_directory,
    make_symlink_to_file,
    make_tree,
    relative_paths,
    symlink_target,
    write_ignore_files,
)
from tests.markers import needs_junctions, needs_symlinks


def flagged(walker: Walker, root: Path) -> list[tuple[str, bool]]:
    """Walk a directory and return every step's relative path and symlink flag.

    Args:
        walker: The walker to walk with.
        root: Path to the directory to walk.

    Returns:
        The relative path of every step, and whether it's a symlink.
    """
    return [(step.relative_as_posix, step.is_symlink) for step in walker.walk(root)]


@needs_symlinks
@mark.parametrize(
    ("ignore_filename", "patterns", "expect"),
    [
        # Without a name or patterns, the walk judges nothing.
        param(
            None,
            [],
            ["a.log", "b", "dlink.target/x", "link.target", "sub/c", "sub/link.target"],
            id="judging-nothing",
        ),
        param(
            "ignore",
            [],
            ["a.log", "b", "dlink.target/x", "link.target", "sub/c", "sub/link.target"],
            id="ignore-filename",
        ),
        param(
            None,
            [("*.log", 0)],
            ["b", "dlink.target/x", "link.target", "sub/c", "sub/link.target"],
            id="patterns",
        ),
    ],
)
def test_walk__ignore_symlinks(
    tmp_path: Path,
    ignore_filename: str | None,
    patterns: list[tuple[str, int]],
    expect: list[str],
) -> None:
    """When symlinks are ignored, none is yielded, in the root or beneath it."""
    make_symlink_to_directory(tmp_path / "dlink")
    make_tree(tmp_path, "a.log", "b", "dlink.target/x", "sub/c")
    make_broken_symlink(tmp_path / "broken")
    make_symlink_to_file(tmp_path / "link")
    make_symlink_to_file(tmp_path / "sub" / "link")

    walker = build_walker(
        ignore_filename,
        patterns,
        ignore_symlinks=True,
    )

    walked = flagged(walker, tmp_path)

    assert walked == [(path, False) for path in expect]


@needs_symlinks
def test_walk__ignore_symlinks_cannot_be_re_included(tmp_path: Path) -> None:
    """When symlinks are ignored, no line or pattern of any weight re-includes one."""
    make_tree(tmp_path, "a")
    make_symlink_to_file(tmp_path / "link")
    write_ignore_files(tmp_path, {"": ["!link"]})

    walked = relative_paths(
        tmp_path,
        "ignore",
        [("!link", 1)],
        ignore_symlinks=True,
    )

    assert walked == ["a", "link.target"]


@needs_symlinks
@mark.parametrize(
    ("ignore_ignore_files", "patterns"),
    [
        param(True, [], id="left-out"),
        param(False, [], id="yielded"),
        param(True, [("!ignore", 1)], id="re-included"),
    ],
)
def test_walk__ignore_symlinks_ignore_file(
    tmp_path: Path,
    ignore_ignore_files: bool,
    patterns: list[tuple[str, int]],
) -> None:
    """When symlinks are ignored, a symlinked ignore-file is read, but never yielded.

    It's never yielded however the ignore-files are set to be left out or yielded, and
    whatever re-includes it.
    """
    path = tmp_path / "sub" / "ignore"
    make_tree(tmp_path, "a.log", "sub/b.log", "sub/c")
    make_symlink_to_file(path)
    symlink_target(path).write_bytes(b"*.log\n!ignore\n")

    walked = relative_paths(
        tmp_path,
        "ignore",
        patterns,
        ignore_ignore_files,
        ignore_symlinks=True,
    )

    assert walked == ["a.log", "sub/c", "sub/ignore.target"]


@needs_junctions
def test_walk__ignore_symlinks_junction(tmp_path: Path) -> None:
    """When symlinks are ignored, a junction is still walked, and isn't a symlink."""
    make_junction(tmp_path / "link")
    make_tree(tmp_path, "link.target/x")

    walker = build_walker(ignore_symlinks=True)

    # A junction and its target both sort as directories: "link.target/", "link/".
    walked = flagged(walker, tmp_path)

    expect = [("link.target/x", False), ("link/x", False)]

    assert walked == expect


@needs_symlinks
def test_walk__ignore_symlinks_root_is_symlink(tmp_path: Path) -> None:
    """When symlinks are ignored, a symlinked root is still walked."""
    root = tmp_path / "root"
    make_symlink_to_directory(root)
    make_tree(symlink_target(root), "a")
    make_symlink_to_file(symlink_target(root) / "link")

    builder = Mosey()
    builder.ignore_symlinks()

    # The steps describe what's inside the root, and none of them is a symlink.
    walked = flagged(builder.build(), root)

    expect = [("a", False), ("link.target", False)]

    assert walked == expect


@needs_symlinks
def test_walk__is_symlink(tmp_path: Path) -> None:
    """Each step says whether it's a symlink, whatever the symlink points to."""
    make_symlink_to_directory(tmp_path / "dlink")
    make_tree(tmp_path, "a", "dlink.target/x")
    make_broken_symlink(tmp_path / "broken")
    make_symlink_to_file(tmp_path / "link")

    walked = flagged(Mosey().build(), tmp_path)

    expect = [
        ("a", False),
        ("broken", True),
        ("dlink", True),
        ("dlink.target/x", False),
        ("link", True),
        ("link.target", False),
    ]

    assert walked == expect
