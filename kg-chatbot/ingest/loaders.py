"""
Utilities for discovering Python files in the codebase.

walk_files(directory) → yields Path for each supported .py file,
                         skipping irrelevant directories.
"""

from pathlib import Path
from typing import Iterator

SKIP_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "coverage",
    ".next",
    "out",
}

SUPPORTED_EXTENSIONS = {".py", ".tf"}


def walk_files(directory: str) -> Iterator[Path]:
    """Recursively traverses directory and yields each supported .py file."""
    root = Path(directory).resolve()
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in SUPPORTED_EXTENSIONS:
            yield path
