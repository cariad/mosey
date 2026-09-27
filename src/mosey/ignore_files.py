"""Functions for working with ignore-files.

These are internal helpers for the `mosey` package. Nothing here is explicitly exported
by the package, and signatures can change without notice.
"""

import errno
import os
import stat
import sys
from typing import Final

from .paths import FS_ENCODING

UTF8_BOM: Final[bytes] = b"\xef\xbb\xbf"
"""UTF-8 byte order mark."""


def read_ignore_file(path: str) -> bytes | None:
    """Return an ignore-file's contents.

    Symlinks aren't followed, so a symlink returns `None` regardless of what it points
    to, as does a directory or anything else that isn't a regular file.

    Args:
        path: Path to the ignore-file.

    Returns:
        The ignore-file's contents, or `None` if it isn't a regular file.

    Raises:
        OSError: When the file can't be read, say because it doesn't exist or
            permissions deny reading it.
    """
    # NOTE: We open and read with `os` functions rather than `open` because `open` does
    # NOTE: work we don't need: it builds two file objects, and makes system calls of
    # NOTE: its own, such as another `fstat`. This way is 19-23% faster on Python 3.11
    # NOTE: to 3.14 on arm64 macOS: 9-10 microseconds rather than 12 for a 96-line file.
    if sys.platform == "win32":
        # Windows can't refuse to open a symlink the way Linux and macOS can (below), so
        # we look before we open. `lstat` describes the symlink itself rather than what
        # it points to.
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None

        # `O_BINARY` reads the bytes exactly as they are, like on Linux and macOS.
        fd = os.open(path, os.O_RDONLY | os.O_BINARY)
    else:
        try:
            # `O_NOFOLLOW` refuses to open a symlink.
            #
            # `O_NONBLOCK` is for FIFOs. A walk only asks us to read what its listing
            # called a file or a symlink, but if a FIFO takes the file's place before we
            # open it, a normal open would wait forever for something to open it for
            # writing. With this flag, the open returns straight away and the check
            # below turns the FIFO away.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as error:
            # Linux and macOS both report a refused symlink as a loop of symlinks.
            if error.errno == errno.ELOOP:
                return None
            raise

    try:
        info = os.fstat(fd)

        # On Linux and macOS, this is where we find out that we opened a directory or a
        # FIFO rather than a regular file. Windows checked before opening.
        if not stat.S_ISREG(info.st_mode):
            return None

        chunks: list[bytes] = []

        while chunk := os.read(fd, info.st_size):
            chunks.append(chunk)

        return b"".join(chunks)

    except OSError as error:
        # `fstat` and `read` work on the open file rather than its path, so their errors
        # never say which file failed.
        error.filename = path
        raise

    finally:
        os.close(fd)


def split_ignore_file(data: bytes) -> list[str]:
    """Return an ignore-file's contents split into individual patterns.

    Args:
        data: The ignore-file's contents.

    Returns:
        The ignore-file's patterns.
    """
    # Some tools (mostly on Windows, hence why this might look unfamiliar) start UTF-8
    # files with a byte order mark to indicate the file's encoding. If we kept it, it
    # would decode to an invisible character stuck to the start of the first line, and a
    # pattern there would look fine but never match. So, let's obliterate it.
    #
    # We remove it from the bytes, before decoding, because what it decodes to depends
    # on the file system encoding we decode with below. Only UTF-8 turns it into that
    # invisible U+FEFF; Latin-1, say, turns it into three unrelated characters. Removing
    # the bytes catches it whatever the encoding is.
    data = data.removeprefix(UTF8_BOM)

    # We had to make a decision here between:
    #
    # - Decoding the whole file before splitting it into lines.
    # - Splitting the file into lines then decoding each line.
    #
    # The latter is slower (39-70% longer on Python 3.11 to 3.14 on arm64 macOS: 6-9
    # microseconds rather than 5-6 for a 96-line file) but protects us from a file
    # system encoding using a newline or carriage return byte as part of another
    # character; because decoding would hide that byte inside the character and we'd
    # miss it. But who would do that? Call me naive, but I'll sleep well tonight
    # preferring the faster and simpler approach over pre-empting this silliness.
    #
    # We decode the file with the same encoding that the file system uses so that a
    # filename in a pattern will byte-wise match the same filename in a directory
    # listing.
    #
    # We don't use the file system's error handler, though. On Windows, that's
    # "surrogatepass", which raises for almost any byte that isn't valid UTF-8, and an
    # ignore-file can hold any bytes at all. So we use "surrogateescape", which decodes
    # every byte.
    text = data.decode(FS_ENCODING, "surrogateescape")

    result: list[str] = []

    for line in text.split("\n"):
        # Windows-style line endings are "\r\n", so splitting at each "\n" leaves a
        # carriage return at the end of every line.
        #
        # We only remove one, and only from the very end of the line, because that's
        # the only carriage return that belongs to the line ending. Wait -- there could
        # be other carriage returns that we want to keep? You bet! Filenames can contain
        # carriage returns on Linux and macOS, so leave those be. macOS even makes them
        # itself: Finder creates a hidden file named "Icon" plus a carriage return in
        # every folder that has a custom icon.
        line = line.removesuffix("\r")

        # Empty lines and comments can't match anything, so we drop them. Only a "#" at
        # the start of a line makes a comment: " #a" and "\#a" are patterns to keep.
        #
        # NOTE: `line[0]` is safe because we know `line` isn't empty.
        #
        # NOTE: `startswith("#")` makes this function 31-43% slower on Python 3.11 and
        # NOTE: 3.12 on arm64 macOS, about 2% faster on 3.13, and 2-5% slower on 3.14.
        if line and line[0] != "#":
            result.append(line)

    # No filename can contain a zero byte, so a line holding one is broken, and we drop
    # it so that it can never match anything. The usual culprit is Windows PowerShell
    # 5.1: appending a line to an existing file with `echo "*.log" >> ...` writes it in
    # UTF-16, which puts a zero byte after every character, the newline included. That
    # last zero byte lands at the start of the next line, so a line that another tool
    # adds after it is dropped too. And if the file didn't end with a newline, the text
    # joins the file's last line, so that line is dropped as well.
    #
    # Zero bytes are rare, so we check the file's bytes once rather than every line.
    if 0 in data:
        result = [line for line in result if "\x00" not in line]

    return result
