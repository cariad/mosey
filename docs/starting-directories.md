---
icon: lucide/folder-down
---

# Starting directories

A walk can start in a subdirectory and still apply the [ignore-files](ignore-files.md) above it. Pass the subdirectory as [`Walker.walk`][mosey.Walker.walk]'s `start`, relative to the directory you walk, and Mosey yields exactly what a walk of the whole directory would yield within it, without listing anything beside it.

For example, this walk yields only the files within `templates/docs/guides`, and still skips whatever `templates/.walkignore` and `templates/docs/.walkignore` ignore:

```python
from mosey import Mosey

builder = Mosey()
builder.set_ignore_filename(".walkignore")
walker = builder.build()

for step in walker.walk("templates", start="docs/guides"):
    print(step.relative_as_posix)
```

## Rules

- `start` is a path relative to the directory you walk, as a string or a path-like object like a [`Path`][pathlib.Path]. Its default, `"."`, starts in the directory you walk.
- `start` can't be absolute, have a drive, or hold `..`, because it has to stay beneath the directory you walk. Like the directory you walk, it can't be empty either: pass `"."` for that.
- Mosey reads the ignore-files in the directory you walk and in every directory down to `start`, just as a walk of the whole directory would on its way there, then walks `start` as usual.
- Mosey lists the directories above `start`, to read their ignore-files and judge the names on the way down, but walks nothing beside `start`.
- Each step's [`relative_as_posix`][mosey.Step.relative_as_posix] stays relative to the directory you walk, and begins with `start` as a POSIX-style path, then a forward slash. So `relative_as_posix.removeprefix("docs/guides/")` gives a path relative to `start`.
- When an ignore-file or [pattern](default-and-overriding-patterns.md) ignores `start`, or any directory above it, the walk yields nothing, because a walk of the whole directory would never reach it.
- `start` never goes through a [symlink](symlinks.md), because a walk never walks into one. Like the directory you walk, a `start` that doesn't exist, or can't exist because it's beneath a file or a symlink, raises `FileNotFoundError`, and a `start` that's a file or a symlink raises `NotADirectoryError`. Mosey checks before the walk begins.
- Each name in `start` has to be spelled exactly as the file system lists it, even on macOS and Windows, where the file system itself would find `DOCS` for `docs`. Otherwise, it doesn't exist as far as the walk is concerned, and raises `FileNotFoundError`. Mosey never translates names, so they match the paths in each step's `relative_as_posix`.

## Example

!!! success "Microsoft Windows"

    On Windows, `start` can use backslashes or forward slashes, like `docs\guides` or `docs/guides`, but each step's [`relative_as_posix`][mosey.Step.relative_as_posix] begins with `docs/guides/` either way. [`Step.path`][mosey.Step.path] gives you each step's path in Windows' own convention.

    This convention aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files and ignore-files:

```text
templates/
├── .walkignore        ← *.log
├── docs/
│   ├── .walkignore    ← drafts/
│   ├── guides/
│   │   ├── drafts/
│   │   │   └── next.md
│   │   ├── install.md
│   │   └── install.log
│   └── index.md
└── readme.md
```

A walk of `templates` with `start="docs/guides"` yields only this file:

```text
docs/guides/install.md
```

It skips `docs/guides/install.log` because of `templates/.walkignore`, and `docs/guides/drafts/` because of `templates/docs/.walkignore`. It never lists `docs/index.md` or `readme.md`, because they're beside `docs/guides`, not within it.

A walk with `start="docs/guides/drafts"` yields nothing, because a walk of `templates` would never walk into `docs/guides/drafts`.

## Behaviour you might not expect

- **`start` is tidied up like a `Path`.** `"docs//guides/"` and `"./docs/guides"` both start in `docs/guides`, and each step's `relative_as_posix` begins with `docs/guides/`.
- **`start="DOCS/Guides"` doesn't start in `docs/guides`**, even on macOS and Windows, where opening `DOCS/Guides` would work. It raises `FileNotFoundError`, just as `.WALKIGNORE` is never read as `.walkignore`. On macOS, the same goes for a name with an accent that's encoded differently from the one on disk, like `café` typed with a combined `é` and saved with an `e` and a separate accent.
- **Errors about `start` come before the walk, but ignoring comes during it.** A `start` that doesn't exist raises an error even when an ignore-file ignores a directory above it, and a `start` that's ignored raises nothing: the walk just yields nothing.
