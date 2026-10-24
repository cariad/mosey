# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

Mosey is a zero-dependency Python library (3.11 and later) that walks a directory and lazily yields a `Step` for every file, in a deterministic order, leaving out its ignore-files (by default), its symlinks (when asked), and whatever the caller's ignore-files and patterns ignore.

## Commands

Everything runs through `uv` (its version is pinned in `pyproject.toml`) and `just`:

- `just local` runs the local equivalents of CI's checks: markdown, docs, lint, typing, test and actions. CI also runs the tests on Linux, macOS and Windows with Python 3.11 to 3.15, and requires 100% coverage across those runs combined.
- Build the docs with `uv run zensical build --clean` when checking links, because the cache can repeat the previous build's warnings.

To run part of the suite, pass `--no-cov` straight after `pytest`:

```bash
uv run pytest --no-cov tests/unit/test_rules.py
uv run pytest --no-cov "tests/unit/test_step.py::test_root"
uv run pytest --no-cov -k random_trees
```

`addopts = "--cov"` takes an optional value, so in `uv run pytest tests/unit/test_rules.py` the path becomes the coverage source: the whole suite runs, then coverage fails at 0%. And any partial run with coverage fails the 90% `fail_under`.

The tests need a UTF-8 file system encoding (`tests/conftest.py` stops the run otherwise; set `PYTHONUTF8=1`), and Git 2.32 or later for the comparisons with Git, which skip locally without it and fail in CI.

## Architecture

- **Public surface.** `Mosey` (`mosey_class.py`), `Walker` (`walker.py`), `Step` (`step.py`) and `BINARY_FILE_PATTERNS` (`binary_files.py`), all exported from `mosey/__init__.py`. `Mosey` is the only class users create. `Walker` and `Step` are protocols for annotations: `Mosey.build` returns a `MoseyWalker` (`mosey_walker.py`), which yields a `MoseyStep` (`mosey_step.py`) for every file, and neither class is exported. Protocol members hold their docstring then `...`, which pyright needs and coverage skips. The code annotates with the protocols, so pyright checks that each class still matches its protocol. Every other module is internal, but named without a leading underscore so linters hold it to public standards. Never name a module after the package: inside `mosey/mosey.py`, the docs' scoped cross-references resolve `mosey` to the module itself, and the strict build fails.
- **Builder and walker.** `Mosey` is the only class users create or change. Its methods check their arguments before storing anything, and return `None` rather than chaining. A `set_*` method replaces one setting (`set_ignore_filename` replaces the name and its `ignore` flag together), an `add_*` method adds to a list, and a bare verb switches a behaviour on. `ignore_binary_files` is the exception: it adds every pattern in `BINARY_FILE_PATTERNS` as `add_pattern` would, so where it's called among the `add_pattern` calls matters. `build()` turns every setting into a value that can't change, compiling anything once, and passes it to `MoseyWalker` by keyword, with no default, so pyright catches a setting that isn't passed. A walker never holds the builder or any of its lists, never changes, and trusts its arguments. There's no `Mosey.walk`.
- **The hot path.** Data on the per-entry path is plain tuples rather than named tuples or classes, `MoseyStep` uses `__slots__` and plain attributes, and nothing there validates its arguments. Many `# NOTE:` comments record benchmarks, on Python 3.11 to 3.14, of alternatives that were measured and rejected. Read the `NOTE:` before suggesting a different shape there, and measure before changing one.

## Code style

- Functions in a module, and methods in a class, are in alphabetical order. A module-level constant goes at the top of the module, straight after the imports. A test's table of cases is the exception: it goes above the first test that uses it. Some older code predates this rule: leave it in its order unless you're asked to change it, and put a new function where it sorts between its neighbours.

## Docs and releases

- The site is built by Zensical with mkdocstrings (`zensical.toml`, `strict = true`). The API reference comes from Google-style docstrings, so a docstring change can break the build. Autorefs like ``[`Step`][mosey.Step]`` are validated by the build; hand-written `#fragment` links to mkdocstrings anchors aren't.
- Behaviour rules are written once, on the docs pages. Docstrings and comments link to the page (for example, "documented at <https://cariad.github.io/mosey/walk-order/>") rather than restating its rules.
- `rumdl` lints every Markdown file in the repository, this one included.
- The version comes from Git tags through hatch-vcs, so there's no version in `pyproject.toml` to bump, and `uv version` doesn't work. A `vX.Y.Z` tag on `main`'s latest commit runs `.github/workflows/release.yml`, which publishes to PyPI by trusted publishing; renaming that workflow breaks publishing.

## Walk order, ignore-files and patterns

Mosey's walk order is documented once, in `docs/walk-order.md` (published at <https://cariad.github.io/mosey/walk-order/>), its ignore-file behaviour once, in `docs/ignore-files.md` (published at <https://cariad.github.io/mosey/ignore-files/>), its default and overriding patterns once, in `docs/default-and-overriding-patterns.md` (published at <https://cariad.github.io/mosey/default-and-overriding-patterns/>), its binary files once, in `docs/binary-files.md` (published at <https://cariad.github.io/mosey/binary-files/>), and its symlinks once, in `docs/symlinks.md` (published at <https://cariad.github.io/mosey/symlinks/>).

## Unsupported configurations

Mosey supports Linux, macOS and Windows only. Never suggest accommodations for other platforms or for unusual builds of Python, such as WebAssembly.

`docs/unsupported.md` (published at <https://cariad.github.io/mosey/unsupported/>) lists the rare configurations that Mosey doesn't support. During reviews, never recommend code, tests or documentation that accommodate them, and don't flag code that only misbehaves in them. At the moment, that's:

- Windows' legacy file system encoding mode (the `PYTHONLEGACYWINDOWSFSENCODING` environment variable, or `sys._enablelegacywindowsfsencoding()`).
