"""Pytest markers for unit tests."""

import os
import sys

from pytest import mark

from tests.file_system_helpers import can_make_symlinks

needs_posix_permissions = mark.skipif(
    # Not every build of Python has `os.geteuid`, so we need to check for it.
    #
    # Two specific examples:
    #
    # - The WebAssembly build. That's fine; our `hasattr` check will catch that.
    # - The Windows build. The `hasattr` check will catch that too, *but* that's not
    #   enough to satisfy Pyright in a Windows development environment. We include the
    #   `sys.platform == "win32"` check to shortcircuit Pyright outta there.
    #
    # If anyone wants to lint this package in a WebAssembly development environment...
    # we'll cross that bridge when we come to it.
    sys.platform == "win32" or not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="`chmod` can't deny access on Windows, on WebAssembly, or to the root user",
)
"""Skips a test that relies on `chmod` to deny access.

Such a test can't be set up:

- On Windows, where `chmod` can only toggle the read-only flag
- On Python builds for WebAssembly, which have no user IDs and so no permissions to
  deny.
- As the root user, who bypasses permission checks.
"""

needs_symlinks = mark.skipif(
    # GitHub Actions' Windows runners *should* be able to create symlinks, so let's fail
    # rather than skip if that configuration changes.
    not can_make_symlinks() and not os.environ.get("CI"),
    reason="Windows needs admin rights or Developer Mode to create symlinks",
)
"""Skips a test that relies on creating symlinks, unless running in CI."""
