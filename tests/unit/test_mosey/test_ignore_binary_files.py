"""Unit tests for the `Mosey.ignore_binary_files` function."""

from pathlib import Path

from pytest import mark, param

from mosey import BINARY_FILE_PATTERNS, Mosey
from tests.file_system_helpers import make_tree, write_ignore_files
from tests.git_oracle import git_list_files
from tests.markers import needs_git

# Every test tree gives each casing its own stem, because macOS and Windows would make
# "a.jpg", "A.JPG" and "a.Jpg" one file.


def test_ignore_binary_files() -> None:
    """Ignoring binary files returns `None` rather than the `Mosey`."""
    assert Mosey().ignore_binary_files() is None


@mark.parametrize(
    "git",
    [
        param(False, id="walk"),
        param(True, marks=needs_git, id="git"),
    ],
)
def test_ignore_binary_files__example(tmp_path: Path, git: bool) -> None:
    """The binary files page's example lists what it says."""
    # The example from the binary files page, with its ignore-file named as the page
    # names it.
    make_tree(
        tmp_path,
        "Mixed.Jpg",
        "SCAN.PDF",
        "archive.tar.gz",
        "docs/logo.svg",
        "docs/manual.pdf",
        "main.py",
        "photos.zip/list.txt",
        "server",
    )

    (tmp_path / ".walkignore").write_bytes(b"!manual.pdf\n")

    if git:
        # `ignore_binary_files` adds each pattern as `add_pattern` would, at weight 0.
        patterns = [(pattern, 0) for pattern in BINARY_FILE_PATTERNS]
        listed = git_list_files(tmp_path, ".walkignore", patterns)
    else:
        # The walker from the page.
        builder = Mosey()
        builder.set_ignore_filename(".walkignore")
        builder.ignore_binary_files()
        walker = builder.build()
        listed = [step.relative_as_posix for step in walker.walk(tmp_path)]

    assert listed == [
        "Mixed.Jpg",
        "docs/logo.svg",
        "docs/manual.pdf",
        "main.py",
        "server",
    ]


@needs_git
def test_ignore_binary_files__git(tmp_path: Path) -> None:
    """Git lists exactly the files that the walk yields."""
    # A file for each extension, like "lower.jpg" for "*.jpg" and "upper.JPG" for
    # "*.JPG", and one for each whole name.
    tree = [
        *(
            f"{'lower' if pattern == pattern.lower() else 'upper'}{pattern[1:]}"
            for pattern in BINARY_FILE_PATTERNS
            if pattern.startswith("*.")
        ),
        *(p for p in BINARY_FILE_PATTERNS if not p.startswith("*.")),
        "main.ts",
        "mixed.Jpg",
        "notes.txt",
    ]

    # On macOS and Windows, two paths that differ only in case would be one file.
    assert len({path.lower() for path in tree}) == len(tree)

    make_tree(tmp_path, *tree)

    builder = Mosey()
    builder.ignore_binary_files()
    walked = [step.relative_as_posix for step in builder.build().walk(tmp_path)]

    assert walked == ["main.ts", "mixed.Jpg", "notes.txt"]

    # Without ignore-files, a pattern's weight changes nothing, in Mosey or in Git. At
    # weight 0, Git reads the patterns from a file, so the command line stays short.
    patterns = [(pattern, 0) for pattern in BINARY_FILE_PATTERNS]
    assert walked == git_list_files(tmp_path, None, patterns)


@mark.parametrize(
    ("steps", "expect"),
    [
        # `None` is a call to `ignore_binary_files`, and a string is a pattern to add.
        param([None, "!*.pdf"], ["report.pdf"], id="lowercase-after"),
        param([None, "!*.pdf", "!*.PDF"], ["SCAN.PDF", "report.pdf"], id="both-after"),
        param(["!*.pdf", "!*.PDF", None], [], id="both-before"),
        param([None, "!*.pdf", "!*.PDF", None], [], id="called-again"),
    ],
)
def test_ignore_binary_files__order(
    tmp_path: Path,
    steps: list[str | None],
    expect: list[str],
) -> None:
    """The patterns take their place among the patterns added around the call."""
    make_tree(tmp_path, "SCAN.PDF", "report.pdf")

    builder = Mosey()

    for step in steps:
        if step is None:
            builder.ignore_binary_files()
        else:
            builder.add_pattern(step)

    walker = builder.build()

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == expect


def test_ignore_binary_files__walk(tmp_path: Path) -> None:
    """A walk skips binary files, and directories named like them, and yields the rest.

    `Mixed.Jpg` is yielded, because its extension is neither lowercase nor uppercase.
    """
    make_tree(
        tmp_path,
        ".DS_Store",
        "Mixed.Jpg",
        "SCAN.JPG",
        "archive.tar.gz",
        "logo.svg",
        "main.ts",
        "notes.txt",
        "photo.jpg",
        "photos.zip/inner.txt",
        "tool.exe",
    )

    builder = Mosey()
    builder.ignore_binary_files()
    walker = builder.build()

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == [
        "Mixed.Jpg",
        "logo.svg",
        "main.ts",
        "notes.txt",
    ]


@mark.parametrize(
    ("arguments", "expect"),
    [
        param({}, ["notes.txt", "report.pdf"], id="default"),
        param({"weight": 0}, ["notes.txt", "report.pdf"], id="0"),
        param({"weight": 1}, ["notes.txt"], id="1"),
    ],
)
def test_ignore_binary_files__weight(
    tmp_path: Path,
    arguments: dict[str, int],
    expect: list[str],
) -> None:
    """The patterns weigh 0 unless given a weight, which decides if ignore-files win."""
    make_tree(tmp_path, "notes.txt", "report.pdf")
    write_ignore_files(tmp_path, {"": ["!report.pdf"]})

    builder = Mosey()
    builder.set_ignore_filename("ignore")
    builder.ignore_binary_files(**arguments)
    walker = builder.build()

    assert [step.relative_as_posix for step in walker.walk(tmp_path)] == expect
