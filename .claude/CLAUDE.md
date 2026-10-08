# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

Mosey is a zero-dependency Python library (3.11 and later) that walks a directory and lazily yields a `Step` for every file, in a deterministic order, leaving out whatever the caller's ignore-files and patterns ignore.

## Commands

Everything runs through `uv` (its version is pinned in `pyproject.toml`) and `just`:

- `just local` runs the local equivalents of CI's checks: markdown, docs, lint, typing, test and actions. CI also runs the tests on Linux, macOS and Windows with Python 3.11 to 3.14, and requires 100% coverage across those runs combined.
- `just fix` fixes formatting and lint with `ruff`, and Markdown with `rumdl`.
- `just test` runs the whole suite with coverage, in about five seconds.
- `just docs` builds the site strictly, and `just start-docs` serves it (so does the `docs` configuration in `.claude/launch.json`). Build with `uv run zensical build --clean` when checking links, because the cache can repeat the previous build's warnings.

To run part of the suite, pass `--no-cov` straight after `pytest`:

```bash
uv run pytest --no-cov tests/unit/test_rules.py
uv run pytest --no-cov "tests/unit/test_step.py::test_root"
uv run pytest --no-cov -k random_trees
```

`addopts = "--cov"` takes an optional value, so in `uv run pytest tests/unit/test_rules.py` the path becomes the coverage source: the whole suite runs, then coverage fails at 0%. And any partial run with coverage fails the 90% `fail_under`.

The tests need a UTF-8 file system encoding (`tests/conftest.py` stops the run otherwise; set `PYTHONUTF8=1`), and Git 2.32 or later for the comparisons with Git, which skip locally without it and fail in CI.

## Architecture

- **Public surface.** `Mosey` (`mosey_class.py`), `Walker` (`walker.py`) and `Step` (`step.py`), all exported from `mosey/__init__.py`. `Mosey` is the only class users create. `Walker` and `Step` are protocols for annotations: `Mosey.build` returns a `MoseyWalker` (`mosey_walker.py`), which yields a `MoseyStep` (`mosey_step.py`) for every file, and neither class is exported. Protocol members hold their docstring then `...`, which pyright needs and coverage skips. The code annotates with the protocols, so pyright checks that each class still matches its protocol. Every other module is internal, but named without a leading underscore so linters hold it to public standards. Never name a module after the package: inside `mosey/mosey.py`, the docs' scoped cross-references resolve `mosey` to the module itself, and the strict build fails.
- **Builder and walker.** `Mosey` is the only class users create or change. Its methods check their arguments before storing anything, and return `None` rather than chaining. A `set_*` method replaces one value, an `add_*` method adds to a list, and a bare verb switches a behaviour on. `build()` turns every setting into a value that can't change, compiling anything once, and passes it to `MoseyWalker` by keyword, with no default, so pyright catches a setting that isn't passed. A walker never holds the builder or any of its lists, never changes, and trusts its arguments. There's no `Mosey.walk`.
- **The walk.** `MoseyWalker.walk()` validates the root and raises straight away, then returns the `_iterate` generator. `_iterate` keeps its own stack of directories instead of recursing. Each frame holds the directory's path, its POSIX-style prefix relative to the root, an iterator over its remaining candidates, and its layers: its ignore-files' and those above it, deepest first, then the light patterns'. The loop `break`s out of a frame to descend into a subdirectory, and the frame's iterator resumes when it's back on top.
- **Listing and order.** `directories.list_candidates` reads a whole directory with `os.scandir`, closes it, and returns `Candidate` tuples of `(name, is_dir)`. Symlinks are files and are never followed, Windows junctions are directories, and anything else (FIFOs, sockets, devices) is left out. `paths.sort_key` sorts them by the name encoded with the file system encoding, plus `/` for a directory, so the paths the walk yields come out in ascending byte order overall.
- **Ignore-files.** When the walker has an ignore-file name (from `Mosey.set_ignore_filename`) or any patterns, `directories.read_directory` takes over from `list_candidates`. With an ignore-file name, it finds the ignore-file in the listing by its exact name, then:
    1. `ignore_files.read_ignore_file` reads the raw bytes with `os.open`, non-blocking so that a FIFO can't hang the walk.
    2. `ignore_files.split_ignore_file` removes a UTF-8 byte order mark, decodes with the file system encoding and `surrogateescape`, splits on `\n`, and drops one trailing `\r`, empty lines, comments, and any line holding a zero byte.
    3. `rules.compile_rules` parses each line into a `Pattern` tuple with `patterns.parse_pattern`. Plain globs go into dicts, and the rest go through `globs.translate_glob` into regular expressions, joined into one per matcher. Each ignore-file gets a matcher for files and another for directories.
    4. `rules.is_ignored` judges each candidate against the `Layers`: the heavy patterns' layer, then one per ignore-file from this directory up to the root, deepest first, then the light patterns' layer. The first layer with a matching line decides, and within it the last matching line. A directory's own ignore-file judges everything inside it, but never the directory itself, and nothing judges the walked directory.
- **Default and overriding patterns.** `Mosey.add_pattern` checks each pattern with `patterns.check_pattern`, which refuses anything an ignore-file would read differently, anything that can never match, and a backslash that escapes nothing (most likely a Windows path). `build()` sorts the patterns by weight, keeping the order they were added within a weight, then `rules.compile_root_layers` compiles those weighing 1 or more into the heavy layer, and the rest into the light layer, each with the prefix `""`. The walk's layers start with the light layer, so every ignore-file's goes in front of it. `read_directory` puts the heavy layer in front of them all for judging, but never returns it, so it never lands in a frame.
- **The hot path.** Data on the per-entry path is plain tuples rather than named tuples or classes, `MoseyStep` uses `__slots__` and plain attributes, and nothing there validates its arguments. Many `# NOTE:` comments record benchmarks, on Python 3.11 to 3.14, of alternatives that were measured and rejected. Read the `NOTE:` before suggesting a different shape there, and measure before changing one.

## Code style

- Functions in a module, and methods in a class, are in alphabetical order. A module-level constant, like a test's table of cases, goes above the first function that uses it. Some older code predates this rule: leave it in its order unless you're asked to change it, and put a new function where it sorts between its neighbours.

## Tests

- `tests/unit/` mirrors `src/mosey/`, so `tests/unit/test_mosey/` tests the builder and `tests/unit/test_mosey_walker/` tests the walk. A module's tests start as one file, and become a directory with one file per function once they grow, like `tests/unit/test_globs/`.
- **Git is a test oracle only**, never the reason for any of Mosey's behaviour. `tests/git_oracle.py` lists files with `git ls-files` in an environment that keeps the user's own Git settings out, and the repository's config sets `core.ignorecase` and `core.precomposeunicode` to `false`. `git_list_files` gives patterns weighing 1 or more to Git's `--exclude`, which overrules every ignore-file, and the rest to one `--exclude-from` file, which every ignore-file overrules. Get expected results by running `git`, and never copy Git's source or its test tables (like `t3070-wildmatch.sh`), which are GPL. Each known difference from Git is a named constant giving the reason, like `ONE_BYTE` in `tests/git_oracle.py`, and the rows it affects record it in a `divergence` field.
- `tests/random_trees/` makes random trees that are the same on every operating system, and `test_walk__random_trees` compares 300 of them with Git, seeded per operating system and Python version. `test_walk__random_trees_with_patterns` compares 100 more with patterns of random weights, running Git once per tree, because patterns are tied to the root Git is given. A failure prints the `random_tree(...)` call that rebuilds the tree anywhere.
- `tests/file_system_helpers.py` builds trees (`make_tree`, the `make_*` helpers, and `write_ignore_files`, which always names the ignore-file `ignore`) and walks them (`relative_paths`). `relative_paths` and `git_list_files` take the same `(root, ignore_filename, patterns)` arguments, so a test can be parametrized over both. `build_walker` builds a walker through the public `Mosey`, so walk tests never construct a `MoseyWalker` directly, and a new setting only changes the helper. The markers in `tests/markers.py` skip tests that need a missing platform feature, but in CI, missing symlinks or Git fail instead.
- **Coverage.** A local run needs 90%. CI combines coverage from Linux, macOS and Windows on Python 3.11 to 3.14, and requires 100% with branch coverage. A line that only one operating system reaches needs a real test on that operating system, skipped elsewhere, never a mock.

## Docs and releases

- The site is built by Zensical with mkdocstrings (`zensical.toml`, `strict = true`). The API reference comes from Google-style docstrings, so a docstring change can break the build. Autorefs like ``[`Step`][mosey.Step]`` are validated by the build; hand-written `#fragment` links to mkdocstrings anchors aren't.
- Behaviour rules are written once, on the docs pages. Docstrings and comments link to the page (for example, "documented at <https://cariad.github.io/mosey/walk-order/>") rather than restating its rules.
- `rumdl` lints every Markdown file in the repository, this one included.
- The version comes from Git tags through hatch-vcs, so there's no version in `pyproject.toml` to bump, and `uv version` doesn't work. A `vX.Y.Z` tag on `main`'s latest commit runs `.github/workflows/release.yml`, which publishes to PyPI by trusted publishing; renaming that workflow breaks publishing.

## Walk order, ignore-files and patterns

Mosey's walk order is documented once, in `docs/walk-order.md` (published at <https://cariad.github.io/mosey/walk-order/>), its ignore-file behaviour once, in `docs/ignore-files.md` (published at <https://cariad.github.io/mosey/ignore-files/>), and its default and overriding patterns once, in `docs/default-and-overriding-patterns.md` (published at <https://cariad.github.io/mosey/default-and-overriding-patterns/>).

## Unsupported configurations

Mosey supports Linux, macOS and Windows only. Never suggest accommodations for other platforms or for unusual builds of Python, such as WebAssembly.

`docs/unsupported.md` (published at <https://cariad.github.io/mosey/unsupported/>) lists the rare configurations that Mosey doesn't support. During reviews, never recommend code, tests or documentation that accommodate them, and don't flag code that only misbehaves in them. At the moment, that's:

- Windows' legacy file system encoding mode (the `PYTHONLEGACYWINDOWSFSENCODING` environment variable, or `sys._enablelegacywindowsfsencoding()`).
