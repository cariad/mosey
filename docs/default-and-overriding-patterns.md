---
icon: lucide/code
---

# Default and overriding patterns

A walker can judge files and directories by patterns that your code adds, as well as or instead of [ignore-files](ignore-files.md). You write each pattern exactly like a line of an ignore-file, and its weight decides whether it's one of your program's defaults, which the ignore-files can overrule, or it overrides them.

For example, this walker skips every file whose name ends with `.pdf`, unless an ignore-file re-includes it, and every directory named `secrets`, whatever the ignore-files say:

```python
from mosey import Mosey

builder = Mosey()
builder.set_ignore_filename(".walkignore")
builder.add_pattern("*.pdf")
builder.add_pattern("secrets/", weight=1)
walker = builder.build()
```

## Rules

### Writing patterns

- A pattern means exactly what the same line would mean in an ignore-file in the directory you walk, following the ignore-files' rules for [writing patterns](ignore-files.md#writing-patterns) and [matching names and paths](ignore-files.md#matching-names-and-paths).
- A `/` at the start or in the middle ties a pattern to the directory you walk, so `/todo.txt` only matches the `todo.txt` in that directory.
- Patterns apply even when the walker reads no ignore-files.

### Weights

- [`Mosey.add_pattern`][mosey.Mosey.add_pattern] gives a pattern a weight of 0, unless you give it another weight.
- A pattern weighing 1 or more overrules every ignore-file.
- An ignore-file overrules the patterns weighing 0 or less, for everything inside its directory.
- Between patterns, the heavier wins, and at equal weights, the last one added wins.
- Mosey never walks into an ignored directory, so nothing inside it can be re-included, not even by a pattern weighing 1 or more.

### Refused patterns

- [`Mosey.add_pattern`][mosey.Mosey.add_pattern] raises `ValueError` for a pattern that an ignore-file would read differently, that's [broken](ignore-files.md#behaviour-you-might-not-expect), or that holds a backslash that escapes nothing.

| Pattern                        | Why                                                                     | Write instead              |
| -                              | -                                                                       | -                          |
| `#notes`                       | An ignore-file would read it as a comment.                              | `\#notes`                  |
| `build\out`                    | A backslash escapes nothing before a character that a glob doesn't use. | `build/out`                |
| `./todo.txt`                   | No path has a `.` or `..` segment.                                      | `/todo.txt`                |
| `docs//todo.txt`               | No path has an empty segment.                                           | `docs/todo.txt`            |
| `[abc.txt`                     | Nothing closes the `[`.                                                 | `\[abc.txt`                |
| `[[:letter:]]`                 | `[:letter:]` isn't a class.                                             | `[[:alpha:]]`              |
| `notes\`                       | A backslash at the end escapes nothing.                                 | `notes/`                   |
| `!`, `/` or an empty pattern   | There's nothing to match.                                               |                            |
| A line break                   | No line of an ignore-file can hold one.                                 |                            |
| A null character               | No name can hold one.                                                   |                            |
| A carriage return at the end   | An ignore-file removes one from the end of each line.                   | `[[:cntrl:]]` in its place |
| A byte order mark at the start | An ignore-file removes one from its start.                              |                            |

## Example

!!! success "Microsoft Windows"

    Windows conventionally separates path segments with backslashes, like `docs\guide.pdf`.

    Patterns **always separate path segments with forward slashes, on every operating system**, and a backslash in a pattern is always an escape. On Windows, `os.path.join` and `str(Path(...))` build paths with backslashes, so join a pattern's segments with forward slashes, or build it with [`PurePath.as_posix()`][pathlib.PurePath.as_posix].

    Mosey refuses a pattern with a backslash that escapes nothing, which catches most Windows paths, like `docs\guide.pdf` and `node_modules\@types`. A backslash only escapes `\`, `*`, `?`, `[`, `]`, `!`, `#`, a space, `-` or `^`.

    The paths in this example are each file's [`Step.relative_as_posix`][mosey.Step.relative_as_posix] — its path relative to the walked directory, with forward slashes.

    Windows usually ignores case in filenames, but patterns don't, so `*.pdf` doesn't match `REPORT.PDF`. Write `*.[Pp][Dd][Ff]` to match both.

    These conventions aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files, subdirectories and ignore-files:

```text
root/
├── .walkignore
├── backup.iso
├── docs/
│   ├── .walkignore
│   ├── guide.pdf
│   └── install.iso
├── manual.pdf
├── readme.md
└── report.pdf
```

The `.walkignore` ignore-files hold these lines:

```text title="root/.walkignore"
!manual.pdf
```

```text title="root/docs/.walkignore"
!*.iso
```

A walker that reads those ignore-files, and adds two patterns:

```python
builder = Mosey()
builder.set_ignore_filename(".walkignore")
builder.add_pattern("*.pdf")
builder.add_pattern("*.iso", weight=1)
walker = builder.build()
```

...yields these files when it walks the `root` directory, in the usual [walk order](walk-order.md):

```text
.walkignore
docs/.walkignore
manual.pdf
readme.md
```

Why?

| Path               | Result  | Why                                                                                                    |
| -                  | -       | -                                                                                                      |
| `.walkignore`      | Yielded | Nothing matches it.                                                                                    |
| `backup.iso`       | Ignored | `*.iso` matches it.                                                                                    |
| `docs/`            | Walked  | Nothing matches it.                                                                                    |
| `docs/.walkignore` | Yielded | Nothing matches it.                                                                                    |
| `docs/guide.pdf`   | Ignored | `*.pdf` matches it.                                                                                    |
| `docs/install.iso` | Ignored | `docs/.walkignore`'s `!*.iso` matches it, but `*.iso` weighs 1, so it overrules every ignore-file. |
| `manual.pdf`       | Yielded | `*.pdf` matches it, but it weighs 0, so the root's `!manual.pdf` overrules it.                         |
| `readme.md`        | Yielded | Nothing matches it.                                                                                    |
| `report.pdf`       | Ignored | `*.pdf` matches it.                                                                                    |

## Behaviour you might not expect

- **An ignore-file can undo a pattern weighing 0 or less.** If you add `secrets/` with its usual weight of 0, an ignore-file holding `!secrets/` re-includes those directories. If no ignore-file should undo a pattern, give it a weight of 1.
- **A pattern is never an absolute path.** `/home/me/build` means `home/me/build` inside the directory you walk, not the directory at that path. Give a pattern relative to the directory you walk.
- **Patterns are tied to whichever directory you walk.** A walker that walks two directories ties `/todo.txt` to each in turn, so it skips the `todo.txt` in each one.
- **Patterns never judge the directory you walk.** Walking a directory named `build` with the pattern `build/` still walks it, and only skips the `build` directories inside it.
- **A broken line in an ignore-file matches nothing, but adding the same pattern raises.** An ignore-file's `[abc.txt` is just skipped, while [`Mosey.add_pattern`][mosey.Mosey.add_pattern] raises `ValueError` for it.
