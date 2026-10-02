"""Timeouts for unit tests that could hang."""

import signal
import sys
from collections.abc import Generator
from contextlib import contextmanager
from types import FrameType


@contextmanager
def alarm(seconds: float, message: str) -> Generator[None]:
    """Raise `TimeoutError` if a block takes longer than `seconds`.

    The alarm interrupts whatever the block is waiting on, even a regular expression
    match, so a test fails rather than hangs. Windows has no alarm signal, so a test
    that uses this must be skipped there.

    Args:
        seconds: How long the block may take.
        message: The message for the `TimeoutError`.

    Raises:
        TimeoutError: When the block takes longer than `seconds`.
    """
    # `signal.setitimer` doesn't exist on Windows. This assertion convinces Pyright that
    # we won't call it when we're running on Windows.
    assert sys.platform != "win32"

    def interrupt(signum: int, frame: FrameType | None) -> None:
        raise TimeoutError(message)

    previous = signal.signal(signal.SIGALRM, interrupt)
    signal.setitimer(signal.ITIMER_REAL, seconds)

    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
