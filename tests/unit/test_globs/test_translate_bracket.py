"""Unit tests for the `translate_bracket` function."""

from pytest import mark, param

from mosey.globs import translate_bracket

# Each glob in these tables starts with its bracket expression, so the expression's
# members start at index 1. Each expected value is the regular expression, and the index
# just after the expression's closing "]".

SETS = [
    param(
        "[ab]",
        ("[ab]", 4),
        id="set",
    ),
    # The glob carries on after the "]".
    param(
        "[ab]c",
        ("[ab]", 4),
        id="text-after",
    ),
    param(
        "[a]]",
        ("[a]", 3),
        id="close-after",
    ),
    # A "]" first in the set is a member, not the end.
    param(
        "[]a]",
        ("[\\]a]", 4),
        id="close-first",
    ),
    param(
        "[]]",
        ("[\\]]", 3),
        id="close-alone",
    ),
    # Characters that mean something in a regular expression are escaped.
    param(
        "[.^$]",
        ("[\\.\\^\\$]", 5),
        id="regular-expression-characters",
    ),
    param(
        "[*?]",
        ("[\\*\\?]", 4),
        id="wildcards",
    ),
    # A "[" that doesn't start a class is a member.
    param(
        "[[]",
        ("[\\[]", 3),
        id="open-bracket",
    ),
]


@mark.parametrize(("glob", "expect"), SETS)
def test_translate_bracket__sets(glob: str, expect: tuple[str, int]) -> None:
    """A bracket expression becomes a set of its members."""
    assert translate_bracket(glob, 1) == expect


NEGATION = [
    # A negated set never matches "/".
    param(
        "[!ab]",
        ("[^/ab]", 5),
        id="exclamation-mark",
    ),
    param(
        "[^ab]",
        ("[^/ab]", 5),
        id="caret",
    ),
    # Only a "!" or "^" straight after the "[" negates.
    param(
        "[a!]",
        ("[a!]", 4),
        id="exclamation-mark-later",
    ),
    param(
        "[!!]",
        ("[^/!]", 4),
        id="exclamation-mark-after-exclamation-mark",
    ),
    param(
        "[!^]",
        ("[^/\\^]", 4),
        id="caret-after-exclamation-mark",
    ),
    param(
        "[\\!a]",
        ("[!a]", 5),
        id="escaped-exclamation-mark",
    ),
    param(
        "[!]a]",
        ("[^/\\]a]", 5),
        id="close-first",
    ),
]


@mark.parametrize(("glob", "expect"), NEGATION)
def test_translate_bracket__negation(glob: str, expect: tuple[str, int]) -> None:
    """A "!" or "^" straight after the "[" negates the set."""
    assert translate_bracket(glob, 1) == expect


ESCAPES = [
    param(
        "[\\]]",
        ("[\\]]", 4),
        id="close",
    ),
    param(
        "[\\\\]",
        ("[\\\\]", 4),
        id="backslash",
    ),
    # A backslash never starts a regular expression's escape, so "\d" is the letter "d"
    # and not any digit.
    param(
        "[\\d]",
        ("[d]", 4),
        id="letter",
    ),
    param(
        "[\\-]",
        ("[\\-]", 4),
        id="dash",
    ),
]


@mark.parametrize(("glob", "expect"), ESCAPES)
def test_translate_bracket__escapes(glob: str, expect: tuple[str, int]) -> None:
    """A backslash makes the character after it a member."""
    assert translate_bracket(glob, 1) == expect


RANGES = [
    param(
        "[a-c]",
        ("[a-c]", 5),
        id="range",
    ),
    param(
        "[\\a-\\c]",
        ("[a-c]", 7),
        id="escaped-ends",
    ),
    param(
        "[A-\\]]",
        ("[A-\\]]", 6),
        id="escaped-close-end",
    ),
    param(
        "[a\\-c]",
        ("[a\\-c]", 6),
        id="escaped-dash",
    ),
    param(
        "[a-c[:digit:]]",
        ("[a-c0-9]", 14),
        id="range-then-class",
    ),
    # A "-" first or last in the set is a member.
    param(
        "[-a]",
        ("[\\-a]", 4),
        id="dash-first",
    ),
    param(
        "[a-]",
        ("[a\\-]", 4),
        id="dash-last",
    ),
    param(
        "[-[:digit:]]",
        ("[\\-0-9]", 12),
        id="dash-before-class",
    ),
    # So is a "-" straight after a range or a class.
    param(
        "[a-c-e]",
        ("[a-c\\-e]", 7),
        id="dash-after-range",
    ),
    param(
        "[[:digit:]-z]",
        ("[0-9\\-z]", 13),
        id="dash-after-class",
    ),
    # Like any other member, such a "-" can start a range. These ranges hold "/", so
    # they're guarded.
    param(
        "[--0]",
        ("(?!/)[\\--0]", 5),
        id="range-from-dash",
    ),
    param(
        "[a-c--e]",
        ("(?!/)[a-c\\--e]", 8),
        id="range-from-dash-after-range",
    ),
    param(
        "[]-a]",
        ("[\\]-a]", 5),
        id="range-from-close",
    ),
    # A range whose ends are the wrong way round is only its first character.
    param(
        "[y-a]",
        ("[y]", 5),
        id="backwards",
    ),
    param(
        "[y-ab]",
        ("[yb]", 6),
        id="backwards-then-member",
    ),
    param(
        "[a-\\]]",
        ("[a]", 6),
        id="backwards-to-escaped-close",
    ),
    # The character after a "-" always ends the range, even a "[". So this is "a" (from
    # a backwards range), ":", "d", "i", "g" and "t", and the last "]" is after the set.
    param(
        "[a-[:digit:]]",
        ("[a:digit:]", 12),
        id="range-to-open-bracket",
    ),
]


@mark.parametrize(("glob", "expect"), RANGES)
def test_translate_bracket__ranges(glob: str, expect: tuple[str, int]) -> None:
    """A "-" between two members makes a range."""
    assert translate_bracket(glob, 1) == expect


CLASSES = [
    param(
        "[[:digit:]]",
        ("[0-9]", 11),
        id="class",
    ),
    param(
        "[![:digit:]]",
        ("[^/0-9]", 12),
        id="negated-class",
    ),
    param(
        "[[:alpha:][:digit:]]",
        ("[A-Za-z0-9]", 20),
        id="two-classes",
    ),
    # A class needs a second ":" before its "]", so this is the set "[" and ":".
    param(
        "[[:]",
        ("[\\[:]", 4),
        id="needs-two-colons",
    ),
    # And it needs a ":" straight after the "[", so this is the set "[", "a" and ":".
    param(
        "[[a:]",
        ("[\\[a:]", 5),
        id="needs-colon-first",
    ),
    # The next "]" after "[:" is escaped, so there's no class. This is the set "[", ":",
    # "a", "]" and "b", and the last "]" is after the set.
    param(
        "[[:a\\]b:]]",
        ("[\\[:a\\]b:]", 9),
        id="ends-at-escaped-close",
    ),
    param(
        "[\\[:digit:]]",
        ("[\\[:digit:]", 11),
        id="escaped-open-bracket",
    ),
    # Only "[:" starts a class, so this is the set "[", "=" and "a", and the last "]" is
    # after the set.
    param(
        "[[=a=]]",
        ("[\\[=a=]", 6),
        id="equals-signs",
    ),
]


@mark.parametrize(("glob", "expect"), CLASSES)
def test_translate_bracket__classes(glob: str, expect: tuple[str, int]) -> None:
    """A class adds its members to the set."""
    assert translate_bracket(glob, 1) == expect


SLASHES = [
    # A set that holds "/" is guarded, so it never matches one.
    param(
        "[/]",
        ("(?!/)[/]", 3),
        id="slash",
    ),
    param(
        "[a/]",
        ("(?!/)[a/]", 4),
        id="slash-and-member",
    ),
    param(
        "[.-0]",
        ("(?!/)[\\.-0]", 5),
        id="range-across-slash",
    ),
    # A negated set already leaves "/" out.
    param(
        "[!/]",
        ("[^//]", 4),
        id="negated",
    ),
]


@mark.parametrize(("glob", "expect"), SLASHES)
def test_translate_bracket__slashes(glob: str, expect: tuple[str, int]) -> None:
    """A bracket expression never matches "/", even when it holds one."""
    assert translate_bracket(glob, 1) == expect


MALFORMED = [
    param("[", id="nothing-after-open"),
    param("[a", id="unclosed"),
    # A "]" first in the set is a member, so nothing closes these.
    param("[]", id="empty"),
    param("[!]", id="empty-negated"),
    param("[^]", id="empty-negated-with-caret"),
    # A backslash at the very end has nothing to escape.
    param("[a\\", id="trailing-backslash"),
    param("[a-\\", id="trailing-backslash-in-range"),
    # The class's "]" doesn't close the set.
    param("[[:alpha:]", id="class-left-open"),
    param("[[:alpha:", id="class-never-closed"),
    # An unknown class breaks the glob, even though a "]" closes the set.
    param("[[:foo:]]", id="unknown-class"),
    param("[[:ALPHA:]]", id="class-in-wrong-case"),
    param("[[::]]", id="class-without-a-name"),
    param("[[:alpha\\:]]", id="backslash-in-class-name"),
    param("[a[:foo:]]", id="unknown-class-beside-member"),
    param("[![:foo:]]", id="negated-unknown-class"),
]


@mark.parametrize("glob", MALFORMED)
def test_translate_bracket__malformed(glob: str) -> None:
    """An unclosed set, or an unknown class, gives `None`."""
    assert translate_bracket(glob, 1) is None


POSITIONS = [
    param(
        "a[bc]d",
        2,
        ("[bc]", 5),
        id="after-text",
    ),
    param(
        "[a][b]",
        4,
        ("[b]", 6),
        id="second-expression",
    ),
    param(
        "x[]y]z",
        2,
        ("[\\]y]", 5),
        id="close-first",
    ),
    param(
        "x[!]y]z",
        2,
        ("[^/\\]y]", 6),
        id="negated-close-first",
    ),
    param(
        "x[[:digit:]]y",
        2,
        ("[0-9]", 12),
        id="class",
    ),
    param(
        "x[[:]y",
        2,
        ("[\\[:]", 5),
        id="not-a-class",
    ),
    param(
        "x[y",
        2,
        None,
        id="unclosed",
    ),
]


@mark.parametrize(("glob", "start", "expect"), POSITIONS)
def test_translate_bracket__positions(
    glob: str,
    start: int,
    expect: tuple[str, int] | None,
) -> None:
    """A bracket expression can start anywhere in the glob."""
    assert translate_bracket(glob, start) == expect
