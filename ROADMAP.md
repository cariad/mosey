# Roadmap

This is a statement of intent, not a promise! Mosey is in early development, and I'm still getting a feel for how far I want to go.

## Goals for v1.0.0

- The walker lazily yields **files only**.

## Goals for beyond v1.0.0

### The walker

- Emit directories and special files (like FIFOs, sockets, devices, etc) too, if configured to. A directory's path will end in `/`, so the walk order stays ascending.

### The `Step` class

- Implement `__fspath__` in `Step` to make it `os.PathLike`. This'll let developers call, say, `open(step)` instead of `open(step.path)`.

### Ignore-files

- Take patterns from the caller, as well as from ignore-files.
- Read ignore-files in the directories above the root, if configured to.
- Explain why a path was ignored: which ignore-file, and which line of it.
