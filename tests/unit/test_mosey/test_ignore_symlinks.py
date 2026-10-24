"""Unit tests for the `Mosey.ignore_symlinks` function."""

from pathlib import Path

from pytest import mark, param

from mosey import Mosey
from tests.file_system_helpers import make_symlink_to_file, make_tree
from tests.git_oracle import git_list_files
from tests.markers import needs_git, needs_symlinks


def test_ignore_symlinks() -> None:
    """Ignoring symlinks returns `None` rather than the `Mosey`."""
    result = Mosey().ignore_symlinks()

    assert result is None


@needs_symlinks
@mark.parametrize(
    "git",
    [
        param(False, id="walk"),
        param(True, marks=needs_git, id="git"),
    ],
)
def test_ignore_symlinks__example(tmp_path: Path, git: bool) -> None:
    """The symlinks page's example lists what it says."""
    # The example from the symlinks page.
    make_tree(tmp_path, "notes.txt", "releases/v2/app.py")

    (tmp_path / "current").symlink_to(
        Path("releases", "v2"),
        target_is_directory=True,
    )

    (tmp_path / "missing").symlink_to("nowhere.txt")
    (tmp_path / "readme.md").symlink_to("notes.txt")

    if git:
        # Git can't say which files are symlinks, so this only checks the paths.
        everything = git_list_files(tmp_path, None)
        ignoring = git_list_files(tmp_path, None, (), True, True)
    else:
        steps = list(Mosey().build().walk(tmp_path))
        everything = [step.relative_as_posix for step in steps]

        # The page shows which of these are symlinks.
        are_symlinks = [step.is_symlink for step in steps]

        expect_symlinks = [
            True,
            True,
            False,
            True,
            False,
        ]

        assert are_symlinks == expect_symlinks

        # The walker from the page.
        builder = Mosey()
        builder.ignore_symlinks()
        walker = builder.build()
        ignoring = [step.relative_as_posix for step in walker.walk(tmp_path)]

    assert everything == [
        "current",
        "missing",
        "notes.txt",
        "readme.md",
        "releases/v2/app.py",
    ]

    assert ignoring == [
        "notes.txt",
        "releases/v2/app.py",
    ]


@needs_symlinks
def test_ignore_symlinks__twice(tmp_path: Path) -> None:
    """Ignoring symlinks again changes nothing."""
    make_tree(tmp_path, "a")
    make_symlink_to_file(tmp_path / "link")

    builder = Mosey()
    builder.ignore_symlinks()
    builder.ignore_symlinks()
    walker = builder.build()

    relative_paths = [step.relative_as_posix for step in walker.walk(tmp_path)]

    expect = [
        "a",
        "link.target",
    ]

    assert relative_paths == expect
