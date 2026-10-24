---
icon: lucide/file-symlink
---

# Symlinks

Mosey yields a symlink as a file, whatever it points to, and never walks into one, as described in [walk order](walk-order.md#behaviour-you-might-not-expect). [`Step.is_symlink`][mosey.Step.is_symlink] tells you whether a step is a symlink, and [`Mosey.ignore_symlinks`][mosey.Mosey.ignore_symlinks] leaves them out of the walk altogether.

For example, this walker never yields a symlink:

```python
from mosey import Mosey

builder = Mosey()
builder.ignore_symlinks()
walker = builder.build()
```

## Rules

- [`Step.is_symlink`][mosey.Step.is_symlink] is `True` for a symlink, whatever it points to, even if its target doesn't exist.
- It describes the file itself, as it was when the walk read its directory, never what it points to.
- When a walker ignores symlinks, it never yields one, and no line in an [ignore-file](ignore-files.md) or [pattern](default-and-overriding-patterns.md) of any weight can re-include one.
- Ignoring symlinks changes what's yielded, not where the walk goes:
    - When the directory you walk is itself a symlink to a directory, Mosey still walks it.
    - Mosey still reads a symlinked [ignore-file](ignore-files.md) through the link, but never yields it.

## Example

!!! success "Microsoft Windows"

    On Windows, a junction (what `mklink /J` makes) isn't a symlink. Mosey walks into a junction like any other directory, even when it ignores symlinks, and a file inside one is a symlink only if it's one itself.

    These conventions aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files, subdirectories and symlinks:

```text
root/
├── current -> releases/v2/
├── missing -> nowhere.txt
├── notes.txt
├── readme.md -> notes.txt
└── releases/
    └── v2/
        └── app.py
```

Nothing named `nowhere.txt` exists, so `missing` is a broken symlink.

A walker that doesn't ignore symlinks yields every file, symlinks included, in the usual [walk order](walk-order.md):

| Path                 | `is_symlink` | Why                                                                              |
| -                    | -            | -                                                                                |
| `current`            | `True`       | It's a symlink to a directory, so it's yielded as a file, and never walked into. |
| `missing`            | `True`       | A broken symlink is yielded like any other.                                      |
| `notes.txt`          | `False`      | It's a file.                                                                     |
| `readme.md`          | `True`       | It's a symlink to a file.                                                        |
| `releases/v2/app.py` | `False`      | It's a file, reached through the `releases` directory, not `current`.            |

The walker above, which ignores symlinks, yields only these files:

```text
notes.txt
releases/v2/app.py
```

## Behaviour you might not expect

- **A symlinked ignore-file that can't be read still stops the walk**, even when the walker ignores symlinks, because Mosey still reads it. For example, a broken symlink named like the ignore-file raises an `OSError`, as described in [ignore-files](ignore-files.md#behaviour-you-might-not-expect).
- **Only symlinks are ignored.** A hard link is a file like any other, and so is a macOS Finder alias, so Mosey yields them both, with `is_symlink` set to `False`.
