"""Pytest markers for unit tests."""

import os
import sys

from pytest import mark

from tests.file_system_helpers import symlinks_allowed
from tests.git_oracle import MINIMUM_VERSION, has_git

needs_fifos = mark.skipif(
    not hasattr(os, "mkfifo"),
    reason="FIFOs can't be created on this platform",
)
"""Skips a test that relies on creating FIFOs (named pipes).

Windows has no `os.mkfifo`.
"""

needs_git = mark.skipif(
    # GitHub Actions' runners all have Git, so let's fail rather than skip if that
    # changes.
    not has_git() and not os.environ.get("CI"),
    reason=f"Git {MINIMUM_VERSION[0]}.{MINIMUM_VERSION[1]} or later isn't installed",
)
"""Skips a test that compares with Git, unless running in CI."""

needs_junctions = mark.skipif(
    sys.platform != "win32",
    reason="Only Windows has junctions",
)
"""Skips a test that relies on creating junctions, which only Windows has."""

needs_posix_permissions = mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="`chmod` can't deny access on Windows or to the root user",
)
"""Skips a test that relies on `chmod` to deny access.

Such a test can't be set up:

- On Windows, where `chmod` can only toggle the read-only flag.
- As the root user, who bypasses permission checks.
"""

needs_symlinks = mark.skipif(
    # GitHub Actions' Windows runners *should* be able to create symlinks, so let's fail
    # rather than skip if that configuration changes.
    not symlinks_allowed(),
    reason="Windows needs admin rights or Developer Mode to create symlinks",
)
"""Skips a test that relies on creating symlinks, unless running in CI."""
