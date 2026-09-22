"""Functions for raising exceptions.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import errno
import os
from typing import NoReturn


def raise_file_not_found(path: str, cause: OSError | None = None) -> NoReturn:
    """Raise `FileNotFoundError`.

    Args:
        path: Path to the file that doesn't exist.
        cause: The exception that led to this one, if any, to keep in the traceback.

    Raises:
        FileNotFoundError: Always.
    """
    raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), path) from cause
