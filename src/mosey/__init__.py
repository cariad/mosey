"""mosey — a directory walker that respects ignore-files."""

from .step import Step

__all__ = [
    "Step",
]


# TODO: This function is intentionally not covered by any tests to check if CI detects
# TODO: <100% coverage and prevents the change being merged.
# TODO:
# TODO: Delete this function after we observe CI fail.
def temporary_uncovered_function() -> str:
    """Return a greeting."""
    return "Hello!"
