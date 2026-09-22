"""A directory walker that respects ignore-files.

Mosey is still in early development, so expect `NotImplementedError` to be raised early
and often where functionality is missing. See `ROADMAP.md` for the plan.

Everything public is exported by this package, so import from here rather than from the
submodules.

- `Mosey` walks a directory and yields a `Step` for every matching object.
- `Step` describes a file system object discovered by a walk.
"""

from .mosey_class import Mosey
from .step import Step

__all__ = [
    "Mosey",
    "Step",
]
