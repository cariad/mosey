---
icon: lucide/eye-off
---

# Ignore-files

An ignore-file tells Mosey what to skip. It's a plain text file with one pattern on each line, and any directory can have one. When the walk reaches a directory, Mosey reads its ignore-file, then skips the files and directories that the patterns match.

For example, with this ignore-file in the directory you walk, Mosey skips every directory named `build`, and every file whose name ends with `.log`:

```text title=".walkignore"
build/
*.log
```

## Rules

### Finding ignore-files

- Mosey reads the ignore-file in the directory you walk, and in every directory beneath it, but never in a directory above it.
- Ignore-files are files too, so Mosey yields them unless a pattern ignores them.
- An ignore-file's patterns still apply when a pattern ignores the ignore-file itself.

### Writing patterns

- Each line describes one pattern.
- Empty lines are skipped.
- A line starting with `#` is a comment, and is skipped.
- `*` matches any run of characters in a name, even none.
- `?` matches one character, even one that takes several bytes, like `é`.
- `[abc]` matches one character from a set, and `[a-z]` matches one character from a range.
- `**/` matches any number of directories, even none.
- `\` escapes the character after it, so the line `\#notes` matches `#notes` instead of being a comment.
- `*`, `?` and `[...]` never match a `/`.

### Matching names and paths

- A pattern with no `/`, like `*.log`, matches a name at any depth.
- A `/` at the start or in the middle ties the pattern to its ignore-file's directory.
    - `/todo.txt` only matches the `todo.txt` beside the ignore-file.
    - `docs/*.md` matches `docs/guide.md`, but not `api/docs/guide.md`.
- A `/` at the end means the pattern only matches directories, so `build/` matches directories named `build`, at any depth.
- Matching is case-sensitive on every operating system.
- Names are matched exactly as the file system reports them, so `café` spelled with one `é` character doesn't match `café` spelled with an `e` and a combining accent.

### Deciding

- The nearest ignore-file with a matching line decides, and, within it, the last matching line wins.
- A line starting with `!` re-includes what it matches.
- Mosey never walks into an ignored directory, so nothing inside it is yielded or read, and nothing inside it can be re-included.
- [Default and overriding patterns](default-and-overriding-patterns.md), which your program adds, can be overruled by the ignore-files, or can overrule them.

## Example

!!! success "Microsoft Windows"

    Windows conventionally separates path segments with backslashes, like `docs\notes.txt`.

    Mosey's ignore-files **always separate path segments with forward slashes, on every operating system**. A backslash in a pattern is always an escape, never a separator, so the pattern `docs\notes.txt` matches files named `docsnotes.txt`, and not `notes.txt` inside `docs`.

    The paths in this example are each file's [`Step.relative_as_posix`][mosey.Step.relative_as_posix] — its path relative to the walked directory, with forward slashes.

    Windows usually ignores case in filenames, but patterns don't, so `*.log` doesn't match `DEBUG.LOG`.

    These conventions aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files, subdirectories and ignore-files:

```text
root/
├── .walkignore
├── build/
│   ├── .walkignore
│   └── app.log
├── debug.log
├── readme.md
├── todo.txt
└── tools/
    ├── .walkignore
    ├── build
    ├── debug.log
    ├── keep.log
    └── todo.txt
```

The `.walkignore` ignore-files hold these lines:

```text title="root/.walkignore"
*.log
build/
/todo.txt
```

```text title="root/build/.walkignore"
!app.log
```

```text title="root/tools/.walkignore"
!keep.log
```

Walking the `root` directory with a walker whose ignore-file name is `.walkignore` (set with [`Mosey.set_ignore_filename`][mosey.Mosey.set_ignore_filename]) yields these files, in the usual [walk order](walk-order.md):

```text
.walkignore
readme.md
tools/.walkignore
tools/build
tools/keep.log
tools/todo.txt
```

Why?

| Path                  | Result      | Why                                                                                          |
| -                     | -           | -                                                                                            |
| `.walkignore`         | Yielded     | No line matches it.                                                                          |
| `build/`              | Ignored     | `build/` matches directories named `build`.                                                  |
| `build/.walkignore`   | Not reached | Mosey never walks into `build`, so it never reads this ignore-file.                          |
| `build/app.log`       | Not reached | Mosey never walks into `build`.                                                              |
| `debug.log`           | Ignored     | `*.log` matches it.                                                                          |
| `readme.md`           | Yielded     | No line matches it.                                                                          |
| `todo.txt`            | Ignored     | `/todo.txt` matches it.                                                                      |
| `tools/`              | Walked      | No line matches it.                                                                          |
| `tools/.walkignore`   | Yielded     | No line matches it.                                                                          |
| `tools/build`         | Yielded     | `build/` only matches directories, and this is a file.                                       |
| `tools/debug.log`     | Ignored     | `*.log` has no `/`, so it matches a name at any depth.                                       |
| `tools/keep.log`      | Yielded     | `*.log` matches it, but `tools/.walkignore` is nearer, and its `!keep.log` re-includes it.   |
| `tools/todo.txt`      | Yielded     | `/todo.txt` starts with a `/`, so it only matches the `todo.txt` beside its own ignore-file. |

## Behaviour you might not expect

- **Only a `#` at the very start of a line makes a comment.** `*.log # logs` is one pattern, so it doesn't match `debug.log`.
- **Spaces at the end of a line are removed, but not at the start.** To keep a space at the end, escape it with `\`. A tab at the end is kept.
- **Names starting with `.` aren't special.** `*` matches `.hidden`.
- **`build/` doesn't match symlinks.** Mosey treats every symlink as a file, even one that points to a directory. On Windows, a junction is a directory, so `build/` matches it.
- **`build/*` isn't the same as `build/`.** `build/*` doesn't ignore `build` itself, so a later `!build/keep.txt` can re-include `build/keep.txt`. But its `/` in the middle ties it to its ignore-file's directory, so use `**/build/*` and `!**/build/keep.txt` to reach every `build`.
- **`docs/**` doesn't match `docs` itself**, only everything inside it.
- **A nearer ignore-file beats a `!` further up.** If the root's ignore-file holds `*.log` then `!keep.log`, and `sub/.walkignore` holds `*.log`, then `sub/keep.log` is ignored.
- **A broken line matches nothing, and the rest of the file still applies.** That's a line with a `[` that nothing closes, like `[abc.txt` (which doesn't even match a file named `[abc.txt`), an unknown class, like `[[:letter:]]`, or a path that would need tidying up, like `./todo.txt` or `docs//todo.txt`.
- **The filename must match exactly.** A file named `.WALKIGNORE` isn't read as `.walkignore`, even on macOS and Windows. A directory named `.walkignore` is walked like any other directory.
- **A symlinked ignore-file is read through the link.** The symlink itself is still yielded, like any other symlink.
- **An ignore-file is read once per walk**, when the walk reaches its directory, so editing it after that makes no difference until the next walk.
- **An ignore-file that can't be read stops the walk.** The walk raises an `OSError` naming it, for example when permissions deny reading it, or it's a broken symlink.
- **A directory that can be listed but not searched stops the walk if it holds the ignore-file.** On Linux and macOS, that's a directory with read but not execute permission. Without an ignore-file name, Mosey would yield its files; with one, the walk raises `PermissionError`.
- **Save ignore-files as UTF-8.** Mosey reads them in the same encoding as filenames, which is UTF-8 on macOS, Windows and almost every Linux system. A UTF-8 byte order mark is fine, and so are Windows line endings.
- **An ignore-file saved as UTF-16 ignores nothing.** Mosey drops every line holding a zero byte, and UTF-16 puts one beside every ASCII character. Windows PowerShell 5.1's `>` writes UTF-16, so `echo "*.log" > .walkignore` ignores nothing. Its `>>` appends a line that Mosey drops, along with the line after it, and the file's last line too if it didn't end with a line break. PowerShell 7 writes UTF-8.

## Pattern reference

### Brackets

| Pattern           | Matches              | Doesn't match     |
| -                 | -                    | -                 |
| `[abc].txt`       | `a.txt`, `c.txt`     | `d.txt`, `ab.txt` |
| `[a-c].txt`       | `b.txt`              | `d.txt`, `B.txt`  |
| `[!a-c].txt`      | `d.txt`, `é.txt`     | `a.txt`           |
| `[]a].txt`        | `].txt`, `a.txt`     | `b.txt`           |
| `[a-].txt`        | `a.txt`, `-.txt`     | `b.txt`           |
| `[y-a].txt`       | `y.txt`              | `a.txt`, `b.txt`  |
| `[[:digit:]].txt` | `1.txt`              | `a.txt`           |

- A `!` or `^` straight after the `[` negates the set.
- A `]` straight after the `[` (or after the `!` or `^`) is a member, not the end.
- A `-` between two members makes a range, and a range written backwards only matches its first character.
- `\` makes the character after it a member, so `[\]]` matches `]`.
- Any other `!`, `^`, `-`, `[`, `*` or `?` inside a set is just a member.

A class, like `[:digit:]`, adds a group of ASCII characters to a set, so `[[:digit:]_]` matches one digit or an underscore. A class's name must be one of these, in lowercase, or the whole line matches nothing:

| Class        | Members                                              |
| -            | -                                                    |
| `[:alnum:]`  | `0`-`9`, `A`-`Z` and `a`-`z`                         |
| `[:alpha:]`  | `A`-`Z` and `a`-`z`                                  |
| `[:blank:]`  | Space and tab                                        |
| `[:cntrl:]`  | The control characters, `0x00` to `0x1f`, and `0x7f` |
| `[:digit:]`  | `0`-`9`                                              |
| `[:graph:]`  | The visible characters, `!` to `~`                   |
| `[:lower:]`  | `a`-`z`                                              |
| `[:print:]`  | Space and the visible characters, `!` to `~`         |
| `[:punct:]`  | The visible characters that aren't letters or digits |
| `[:space:]`  | Space, tab, line feed and carriage return            |
| `[:upper:]`  | `A`-`Z`                                              |
| `[:xdigit:]` | `0`-`9`, `A`-`F` and `a`-`f`                         |

### Double asterisks

| Pattern        | Matches                                     | Doesn't match         |
| -              | -                                           | -                     |
| `**/logs`      | `logs`, `a/logs`, `a/b/logs`                | `catalogs`            |
| `docs/**/*.md` | `docs/a.md`, `docs/x/a.md`, `docs/x/y/a.md` | `a.md`, `x/docs/a.md` |
| `docs/**`      | `docs/a.md`, `docs/x/a.md`                  | `docs/`, `docs`       |
| `docs**/a.md`  | `docs/a.md`, `docs2/a.md`                   | `docs/x/a.md`         |

- `**` only crosses directories when it's a whole path segment, between `/`s or the ends of the pattern.
- Any other run of `*`, like the one in `docs**`, matches the same as a single `*`.
- `***` or a longer run matches the same as `**`.
- A `/` beside a `**` counts whether it's written `/` or `\/`.

### Re-including

| Line        | Means                                  |
| -           | -                                      |
| `!keep.log` | Re-include `keep.log`                  |
| `!!notes`   | Re-include `!notes`                    |
| `\!notes`   | Ignore `!notes`                        |
| `/!notes`   | Ignore `!notes` beside the ignore-file |
