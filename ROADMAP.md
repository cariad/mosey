# Roadmap

This is a statement of intent, not a promise! Mosey is in early development, and I'm still getting a feel for how far I want to go.

## Goals for v1.0.0

- The walker lazily yields **files only**.

## Goals for beyond v1.0.0

### The walker

- Emit directories and special files (like FIFOs, sockets, devices, etc) too, if configured to. A directory's path will end in `/`, so the walk order stays ascending.

### The `Step` class

- Implement `__fspath__` in `Step` to make it `os.PathLike`. This'll let developers call, say, `open(step)` instead of `open(step.path)`.

## Notes to self

Things to remember when ignore-files arrive:

- Patterns will match names exactly as the file system reports them, so a pattern spelled with a composed accent won't match a name reported with a decomposed one.
- A symlink to a directory is a file, so a directory-only pattern like `foo/` won't match it. Think about that.
- A line holding a zero byte is dropped, so it never matches anything. Windows PowerShell 5.1 writes lines like that when `>>` appends to an existing file, and leaves a zero byte at the start of the next line too. And if the file didn't end with a newline, the text joins the file's last line, so that line is dropped as well. Say so on the ignore-files page.
