# Roadmap

This is a statement of intent, not a promise! Mosey is in early development, and I'm still getting a feel for how far I want to go.

## Goals for v1.0.0

- The walker lazily yields **files only**.

## Goals for beyond v1.0.0

### The walker

- Emit directories and special files (like FIFOs, sockets, devices, etc) too, if configured to.

### The `Step` class

- Implement `__fspath__` in `Step` to make it `os.PathLike`. This'll let developers call, say, `open(step)` instead of `open(step.path)`.
