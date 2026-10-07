"""A directory walker that respects ignore-files.

Everything public is exported by this package, so import from here rather than from the
submodules.

- `Mosey` describes a walk, and builds a `Walker` to take it.
- `Walker` walks a directory and yields a `Step` for every file that isn't ignored.
- `Step` describes a file system object discovered by a walk.

`Mosey` is the only class you create. `Walker` and `Step` are protocols: the types to
annotate the walkers and steps that Mosey creates for you.
"""

from .mosey_class import Mosey
from .step import Step
from .walker import Walker

__all__ = [
    "Mosey",
    "Step",
    "Walker",
]
