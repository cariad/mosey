"""A random tree's files, directories and symlinks while it's being made."""

import random
from posixpath import join

# Names that every operating system can hold. Most come from the first list, so that
# lines often match more than one name.
COMMON = [
    "a",
    "b",
    "ab",
    "a.txt",
    "b.log",
    ".a",
    "x y",
    "keep",
]

RARE = [
    "[a]",
    "#a",
    "!a",
    "Keep",
    "B",
    "z",
]


class Draft:
    """A random tree while it's being made."""

    def __init__(self, rng: random.Random) -> None:
        """Start with an empty root.

        Args:
            rng: The random number generator that makes the tree.
        """
        self.rng = rng
        self.directories = [""]
        self.files: list[str] = []
        self.symlinks: dict[str, str] = {}
        self.lines: dict[str, list[str]] = {}

        # Each directory's names, lower-cased, so that no two differ only in case.
        # Nothing but an ignore-file (or a directory named like it) is named "ignore",
        # in any casing.
        self.taken: dict[str, set[str]] = {"": {"ignore"}}

    def take(self, parent: str, name: str) -> bool:
        """Claim a name in a directory, unless one there differs from it only in case.

        Args:
            parent: The directory's path.
            name: The name.

        Returns:
            `True` if the name was free, otherwise `False`.
        """
        if name.lower() in self.taken[parent]:
            return False

        self.taken[parent].add(name.lower())
        return True

    def add_directory(self, path: str) -> None:
        """Add a directory whose name is already claimed.

        Args:
            path: The directory's path.
        """
        self.directories.append(path)
        self.taken[path] = {"ignore"}

    def beneath(self, holder: str) -> list[str]:
        """Return the paths of the entries beneath a directory, ignore-files included.

        The list is never empty, since a directory with lines holds an ignore-file.

        Args:
            holder: The directory's path.

        Returns:
            The paths.
        """
        entries = [
            *self.files,
            *self.directories[1:],
            *self.symlinks,
            *(join(directory, "ignore") for directory in self.lines),
        ]

        return [path for path in entries if not holder or path.startswith(holder + "/")]

    def name(self) -> str:
        """Return a random name.

        Returns:
            The name.
        """
        return self.rng.choice(COMMON if self.rng.random() < 0.85 else RARE)

    def add_entries(self) -> None:
        """Add 5 to 30 files and directories, up to four directories deep."""
        target = self.rng.randint(5, 30)
        made = 0

        for _ in range(1000):
            if made == target:
                break

            parent = self.rng.choice(self.directories)
            name = self.name()

            if not self.take(parent, name):
                continue

            if parent.count("/") < 3 and self.rng.random() < 0.4:
                self.add_directory(join(parent, name))
            else:
                self.files.append(join(parent, name))

            made += 1

    def add_symlinks(self) -> None:
        """Add a symlink to a file, to a directory, or one of each."""
        kinds = self.rng.choice([["file"], ["directory"], ["file", "directory"]])

        for kind in kinds:
            targets = self.files if kind == "file" else self.directories[1:]

            if not targets:
                continue

            target = self.rng.choice(targets)

            for _ in range(20):
                parent = self.rng.choice(self.directories)
                name = self.name()

                if self.take(parent, name):
                    self.symlinks[join(parent, name)] = target
                    break

    def add_ignore_directory(self) -> None:
        """Add a directory named like the ignore-file, with some files inside."""
        # A directory can't hold both an ignore-file and a directory with its name, so
        # the root, which always has an ignore-file, never holds one.
        parents = [path for path in self.directories[1:] if path.count("/") < 3]

        if not parents or self.rng.random() < 0.3:
            free = [name for name in COMMON if name.lower() not in self.taken[""]]

            if not free:
                return

            parent = self.rng.choice(free)
            self.take("", parent)
            self.add_directory(parent)
        else:
            parent = self.rng.choice(parents)

        path = parent + "/ignore"
        self.add_directory(path)

        for name in self.rng.sample(COMMON, self.rng.randint(0, 3)):
            self.take(path, name)
            self.files.append(f"{path}/{name}")

        if self.rng.random() < 0.3:
            name = self.rng.choice([n for n in COMMON if n not in self.taken[path]])
            self.take(path, name)
            self.add_directory(f"{path}/{name}")
            self.take(f"{path}/{name}", "a")
            self.files.append(f"{path}/{name}/a")
