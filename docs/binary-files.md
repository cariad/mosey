---
icon: lucide/binary
---

# Binary files

A walker can skip binary files, like images, archives and documents. [`Mosey.ignore_binary_files`][mosey.Mosey.ignore_binary_files] adds patterns for the most common binary formats, like `*.pdf` and `*.zip`, and for `.DS_Store`.

For example, this walker skips every file whose name ends with `.pdf` or `.PDF`, `.zip` or `.ZIP`, and so on:

```python
from mosey import Mosey

builder = Mosey()
builder.ignore_binary_files()
walker = builder.build()
```

Your program can read every pattern in [`BINARY_FILE_PATTERNS`][mosey.BINARY_FILE_PATTERNS], and they're all [listed below](#formats).

## Rules

- Mosey judges each file by its name, never by what's inside it.
- Each extension matches in all-lowercase and all-uppercase, so `*.jpg` and `*.JPG` match `photo.jpg` and `SCAN.JPG`, but not `Mixed.Jpg`.
- A whole name, like `.DS_Store`, only matches in exactly that case.
- [`Mosey.ignore_binary_files`][mosey.Mosey.ignore_binary_files] adds every pattern exactly as [`Mosey.add_pattern`][mosey.Mosey.add_pattern] would, at the point you call it, so they follow the rules for [default and overriding patterns](default-and-overriding-patterns.md).
- The patterns weigh 0 unless you give them another weight, so an ignore-file can re-include a binary file. Give them a weight of 1 or more to overrule every ignore-file.

## Example

!!! success "Microsoft Windows"

    Windows usually ignores case in filenames, but patterns don't, which is why `Mixed.Jpg` is yielded below. To catch every casing of an extension, add a pattern like `*.[Jj][Pp][Gg]` with [`Mosey.add_pattern`][mosey.Mosey.add_pattern].

    These conventions aside, **Mosey supports Windows as a first-class platform**. Every code change is tested on Linux, macOS, *and* Windows, for compatibility and feature parity.

Take a directory with these files, subdirectories and ignore-file:

```text
root/
├── .walkignore
├── Mixed.Jpg
├── SCAN.PDF
├── archive.tar.gz
├── docs/
│   ├── logo.svg
│   └── manual.pdf
├── main.py
├── photos.zip/
│   └── list.txt
└── server
```

The `.walkignore` ignore-file holds this line:

```text title="root/.walkignore"
!manual.pdf
```

A walker that reads that ignore-file, and ignores binary files:

```python
builder = Mosey()
builder.set_ignore_filename(".walkignore")
builder.ignore_binary_files()
walker = builder.build()
```

...yields these files when it walks the `root` directory, in the usual [walk order](walk-order.md):

```text
Mixed.Jpg
docs/logo.svg
docs/manual.pdf
main.py
server
```

Why?

| Path                  | Result      | Why                                                                            |
| -                     | -           | -                                                                              |
| `.walkignore`         | Ignored     | It's an ignore-file, and nothing re-includes it.                               |
| `Mixed.Jpg`           | Yielded     | `*.jpg` and `*.JPG` don't match `.Jpg`.                                        |
| `SCAN.PDF`            | Ignored     | `*.PDF` matches it.                                                            |
| `archive.tar.gz`      | Ignored     | `*.gz` matches it.                                                             |
| `docs/`               | Walked      | Nothing matches it.                                                            |
| `docs/logo.svg`       | Yielded     | SVG images are text, so there's no `*.svg`.                                    |
| `docs/manual.pdf`     | Yielded     | `*.pdf` matches it, but it weighs 0, so the root's `!manual.pdf` overrules it. |
| `main.py`             | Yielded     | Nothing matches it.                                                            |
| `photos.zip/`         | Ignored     | `*.zip` matches directories too.                                               |
| `photos.zip/list.txt` | Not reached | Mosey never walks into `photos.zip`.                                           |
| `server`              | Yielded     | Nothing matches its name, so it's yielded even if it's a program.              |

## Behaviour you might not expect

- **Mosey never looks inside a file.** A program named `server` is yielded, and a text file named `notes.pdf` is skipped.
- **A directory named like a binary file is skipped too**, like it would be by any pattern without a `/` at the end. Mosey never walks into a directory named `photos.zip`.
- **The list is short on purpose.** Add other formats yourself, like `add_pattern("*.psd")` and `add_pattern("*.PSD")`.
- **To re-include a format, re-include both casings.** After `ignore_binary_files()`, at the same weight, add `!*.pdf` and `!*.PDF`, or `!*.[Pp][Dd][Ff]`. An ignore-file needs the same.
- **Calling `ignore_binary_files` again adds the patterns again**, so they overrule any `!` patterns of the same weight that you added between the two calls.
- **The patterns can change in any release**, as formats are added. For a set that never changes, add your own copy of the patterns with `add_pattern`.

## Formats

| Group           | Extensions                                                                                                  |
| -               | -                                                                                                           |
| Archives        | `7z`, `bz2`, `gz`, `rar`, `tar`, `tgz`, `xz`, `zip`, `zst`                                                  |
| Documents       | `doc`, `docx`, `epub`, `odp`, `ods`, `odt`, `pdf`, `ppt`, `pptx`, `xls`, `xlsx`                             |
| Images          | `avif`, `bmp`, `gif`, `heic`, `ico`, `jpeg`, `jpg`, `png`, `tif`, `tiff`, `webp`                            |
| Audio and video | `aac`, `avi`, `flac`, `m4a`, `m4v`, `mkv`, `mov`, `mp3`, `mp4`, `mpeg`, `mpg`, `ogg`, `opus`, `wav`, `webm` |
| Applications    | `exe`                                                                                                       |

The patterns also match `.DS_Store`, the file that macOS's Finder writes into folders.
