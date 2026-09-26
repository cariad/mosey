---
icon: lucide/ban
---

# Unsupported configurations

Every change to Mosey is tested on Linux, macOS and Windows, with Python 3.11, 3.12, 3.13 and 3.14.

A few rare configurations of those platforms aren't supported. Mosey might still work in them, but it isn't tested in them, and a bug report for these scenarios would need to be exceptionally compelling to be considered for fixing.

## Windows' legacy file system encoding mode

Modern Python on Windows encodes filenames into bytes as UTF-8. Before Python 3.6, though, it used the Windows code page instead.

Setting the `PYTHONLEGACYWINDOWSFSENCODING` environment variable switches Python back to that old behaviour, usually to keep a program written for an older version of Python working.

**Mosey does not support this legacy mode.** In it, Mosey can't promise its [walk order](walk-order.md) for files whose names hold characters that the code page can't represent.

!!! success "Microsoft Windows"

    Windows, Python and Python's installers never switch this mode on by themselves.

    In every other configuration, **Mosey supports Windows as a first-class platform**.
