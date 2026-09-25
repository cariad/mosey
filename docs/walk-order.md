---
icon: lucide/list-ordered
---

# Walk order

## Summary

Mosey walks the same directory in the same order every time, according to these rules:

- **Mosey yields paths in ascending byte order.** Mosey encodes each path into bytes, then compares those bytes from left to right. The first byte that differs decides the order; lowest first, so paths are yielded in ascending order. If one path runs out of bytes before the other, the shorter path comes first.

- **Mosey walks depth-first.** If the walk reaches a subdirectory, it yields everything inside it before moving on to the next entry of the directory it was in.

## Example

!!! success "Microsoft Windows"

    Windows conventionally separates path segments with back-slashes, like `documents\readme.md`.

    The paths in these examples are each file's [`Step.relative_as_posix`][mosey.Step.relative_as_posix]: its path relative to the walked directory, with forward-slashes on every operating system — Windows included. This is the path that Mosey orders on.

    When you need a path in Windows' own convention, [`Step.path`][mosey.Step.path] gives you one.

    This convention aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files and subdirectories:

```text
root/
├── .a
├── Z
├── a
├── b/
│   └── x
├── b-c
├── b.txt
├── b_c
├── ba/
│   └── z
├── cafz
└── café
```

Mosey yields the files in this order:

```text
.a
Z
a
b-c
b.txt
b/x
b_c
ba/z
cafz
café
```

`.a` comes first because its first byte, `.` (`0x2e`), is lower than every other path's first byte, then `Z` comes before `a` because uppercase letters have lower byte values than lowercase ones: `Z` is `0x5a` and `a` is `0x61`.

| Path | 1st character | 1st byte |
| -    | -             | -        |
| `.a` | `.`           | `0x2e`   |
| `Z`  | `Z`           | `0x5a`   |
| `a`  | `a`           | `0x61`   |

!!! info "Dotfiles aren't special"

    Mosey never skips a name beginning with `.`, and never sorts it differently; it's sorted by its bytes like everything else.

The five paths starting with `b` share the same first byte, so their second byte decides their order:

| Path    | 2nd character | 2nd byte |
| -       | -             | -        |
| `b-c`   | `-`           | `0x2d`   |
| `b.txt` | `.`           | `0x2e`   |
| `b/x`   | `/`           | `0x2f`   |
| `b_c`   | `_`           | `0x5f`   |
| `ba/z`  | `a`           | `0x61`   |

!!! note "Why did Mosey yield `b.txt` before `b/x`?"

    If you looked only at the root directory, then you might expect Mosey to walk into the `b` directory before yielding `b.txt`, because `b` is shorter.

    However, **Mosey orders *paths*, not *names*.**

    In this example, the path being compared is `b/x`, not `b`. Every path beneath `b` begins with `b/`, so its second byte is `/` (`0x2f`) whatever the directory contains, and that's higher than the `.` (`0x2e`) in `b.txt`, so `b.txt` comes first.

    Critically, **the whole list stays in byte order**, even when it looks odd within the context of a single directory.

Finally, characters outside the ASCII set work the same way. In UTF-8, `é` is two bytes, `0xc3` then `0xa9`, and `z` is one byte, `0x7a`, so `cafz` comes before `café`:

| Path   | 4th character | 4th byte |
| -      | -             | -        |
| `cafz` | `z`           | `0x7a`   |
| `café` | `é`           | `0xc3`   |

## Behaviour you might not expect

- **The order isn't always alphabetical.** Mosey never asks your locale how letters should be ordered; only the byte value is considered. That's why `Z` came before `a`, and `café` after `cafz`.
- **Only files are yielded.** Directories themselves aren't yielded; only the files inside them. FIFOs, sockets, devices, and so on, are neither yielded nor walked into.
- **Symlinks are always files.** A symlink found during a walk is treated as a file, whatever it points to, even if the target doesn't exist, so the walk never descends into it. Only the root is different: the directory you ask Mosey to walk can itself be a symlink to a directory.
- **Windows junctions are directories.** On Windows, junctions (a kind of directory link that isn't a symlink) are treated as directories, and walks will descend into them.
- **Nothing is skipped by name.** Mosey has no knowledge of any tool's special directories, so it never skips an entry because of what it's called — not even `.git`.
- **Each directory is read when the walk reaches it.** The root is read when you ask for the first step, and each subdirectory is read when the walk gets to it. If the tree changes during a walk, directories that the walk hasn't reached yet will accommodate the change, and directories that it's already read won't be re-walked. A subdirectory that's discovered but then deleted by the time the walk reaches it will raise `FileNotFoundError`.
