#!/usr/bin/env python3
"""
Bump the Filefy package version.

This script is the single entry point for changing the project version.
It updates two files in lock-step so that the value reported by
``filefy --version`` and the value PyPI sees are always identical:

1. ``filefy/_version.py`` (read by setuptools at build time and by the
   package at runtime).
2. ``filefy/config/details.json`` (the human-readable metadata file).

Usage:
    python scripts/bump_version.py patch        # 1.2.3 -> 1.2.4
    python scripts/bump_version.py minor        # 1.2.3 -> 1.3.0
    python scripts/bump_version.py major        # 1.2.3 -> 2.0.0
    python scripts/bump_version.py set 1.5.0    # explicit version

The new version is printed on stdout (no trailing newline noise) so it
can be captured by CI workflows, e.g.:

    NEW_VERSION="$(python scripts/bump_version.py patch)"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO_ROOT / "filefy" / "_version.py"
DETAILS_FILE = REPO_ROOT / "filefy" / "config" / "details.json"

VERSION_RE = re.compile(r'^__version__\s*=\s*"(?P<version>[^"]+)"\s*$', re.MULTILINE)
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def read_current_version() -> str:
    """Return the current version recorded in ``filefy/_version.py``."""
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit(
            f"Unable to find __version__ assignment in {VERSION_FILE}"
        )
    return match.group("version")


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a strict ``MAJOR.MINOR.PATCH`` semantic version string."""
    match = SEMVER_RE.match(version)
    if not match:
        raise SystemExit(
            f"Version '{version}' is not a valid MAJOR.MINOR.PATCH string"
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump(current: str, part: str) -> str:
    """Return a new version string with the given ``part`` incremented."""
    major, minor, patch = parse_semver(current)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"Unknown bump part: {part}")


def write_version_file(new_version: str) -> None:
    """Persist ``new_version`` into ``filefy/_version.py``."""
    text = VERSION_FILE.read_text(encoding="utf-8")
    new_text, count = VERSION_RE.subn(
        f'__version__ = "{new_version}"', text, count=1
    )
    if count != 1:
        raise SystemExit(f"Failed to update {VERSION_FILE}")
    VERSION_FILE.write_text(new_text, encoding="utf-8")


def write_details_file(new_version: str) -> None:
    """Persist ``new_version`` into ``filefy/config/details.json``."""
    if not DETAILS_FILE.exists():
        return
    data = json.loads(DETAILS_FILE.read_text(encoding="utf-8"))
    data["version"] = new_version
    DETAILS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump the Filefy version.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("major", help="Bump the major version (X.0.0).")
    sub.add_parser("minor", help="Bump the minor version (x.Y.0).")
    sub.add_parser("patch", help="Bump the patch version (x.y.Z).")
    sub.add_parser("show", help="Print the current version and exit.")

    set_parser = sub.add_parser("set", help="Set the version explicitly.")
    set_parser.add_argument("version", help="New version (MAJOR.MINOR.PATCH).")

    args = parser.parse_args(argv)
    current = read_current_version()

    if args.command == "show":
        print(current)
        return 0

    if args.command == "set":
        # Validate format up-front
        parse_semver(args.version)
        new_version = args.version
    else:
        new_version = bump(current, args.command)

    if new_version == current:
        # No change: still succeed but print the same version.
        print(current)
        return 0

    write_version_file(new_version)
    write_details_file(new_version)
    print(new_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
