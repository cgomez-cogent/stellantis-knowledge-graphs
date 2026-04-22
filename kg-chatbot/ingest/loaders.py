"""
Utilidades para descubrir archivos Python del codebase.

walk_files(directory) → genera Path de cada archivo .py soportado,
                         saltando carpetas irrelevantes.
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

SUPPORTED_EXTENSIONS = {".py"}


def walk_files(directory: str) -> Iterator[Path]:
    """Recorre directory recursivamente y yield cada archivo .py soportado."""
    root = Path(directory).resolve()
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in SUPPORTED_EXTENSIONS:
            yield path
