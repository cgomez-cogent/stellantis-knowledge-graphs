"""
Parser for Terraform (.tf) files.

parse_tf_file(path, root) → structured dict with file, resources, modules,
                             variables, outputs, data_sources, providers.
Returns None if the file cannot be read.
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Matches block headers, e.g.:
#   resource "aws_s3_bucket" "my_bucket" {
#   variable "name" {
#   provider "aws" {
_BLOCK_HEADER = re.compile(
    r'^(\w+)\s+"([^"]+)"(?:\s+"([^"]+)")?\s*\{',
    re.MULTILINE,
)


def _extract_body(source: str, open_brace: int) -> str:
    """Return content between matched braces, starting at open_brace position."""
    depth = 0
    i = open_brace
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : i]
        i += 1
    return source[open_brace + 1 :]


def _attr(body: str, key: str) -> str:
    """Extract the first value of a simple attribute inside a block body."""
    m = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', body, re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(rf'^\s*{key}\s*=\s*([^"\n{{][^\n]*)', body, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return ""


def parse_tf_file(path: Path, root: Path) -> dict | None:
    """Parse a .tf file and return structured KG data, or None on failure."""
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            source = path.read_text(encoding="latin-1")
        except Exception:
            logger.warning("Cannot read %s", path)
            return None
    except Exception:
        logger.warning("Cannot read %s", path)
        return None

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path

    file_path = str(relative).replace("\\", "/")

    resources: list[dict] = []
    modules: list[dict] = []
    variables: list[dict] = []
    outputs: list[dict] = []
    data_sources: list[dict] = []
    providers: list[dict] = []

    for match in _BLOCK_HEADER.finditer(source):
        block_type = match.group(1)
        label1 = match.group(2)
        label2 = match.group(3)

        # The regex ends with \{ so the opening brace is the last matched char.
        open_brace = match.end() - 1
        body = _extract_body(source, open_brace)

        if block_type == "resource":
            resources.append({
                "type": label1,
                "name": label2 or "",
                "description": _attr(body, "description"),
            })
        elif block_type == "module":
            modules.append({
                "name": label1,
                "source": _attr(body, "source"),
                "version": _attr(body, "version"),
            })
        elif block_type == "variable":
            variables.append({
                "name": label1,
                "var_type": _attr(body, "type"),
                "default": _attr(body, "default"),
                "description": _attr(body, "description"),
            })
        elif block_type == "output":
            outputs.append({
                "name": label1,
                "value": _attr(body, "value"),
                "description": _attr(body, "description"),
            })
        elif block_type == "data":
            data_sources.append({
                "type": label1,
                "name": label2 or "",
                "description": _attr(body, "description"),
            })
        elif block_type == "provider":
            providers.append({
                "type": label1,
            })

    return {
        "file": {"name": file_path, "file_path": file_path},
        "resources": resources,
        "modules": modules,
        "variables": variables,
        "outputs": outputs,
        "data_sources": data_sources,
        "providers": providers,
    }
