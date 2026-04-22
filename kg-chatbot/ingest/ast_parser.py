"""
AST parser for Python files.

parse_module(path, root) → structured dict with module, imports, classes, functions.
Returns None if the file cannot be parsed (syntax error, unreadable).
"""

import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _unparse(node) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _parse_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict]:
    args = func_node.args
    all_args = args.posonlyargs + args.args
    defaults_offset = len(all_args) - len(args.defaults)

    params = []
    for i, arg in enumerate(all_args):
        if arg.arg in ("self", "cls"):
            continue
        default_idx = i - defaults_offset
        default = _unparse(args.defaults[default_idx]) if default_idx >= 0 else ""
        params.append({
            "name": arg.arg,
            "annotation": _unparse(arg.annotation),
            "default": default,
        })

    if args.vararg:
        params.append({"name": f"*{args.vararg.arg}", "annotation": _unparse(args.vararg.annotation), "default": ""})
    if args.kwarg:
        params.append({"name": f"**{args.kwarg.arg}", "annotation": _unparse(args.kwarg.annotation), "default": ""})

    return params


def _parse_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    return {
        "name": node.name,
        "line": node.lineno,
        "docstring": ast.get_docstring(node) or "",
        "returns": _unparse(node.returns),
        "params": _parse_params(node),
    }


def _parse_class(node: ast.ClassDef) -> dict:
    bases = [_unparse(b) for b in node.bases if _unparse(b)]
    methods = [
        _parse_function(item)
        for item in node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return {
        "name": node.name,
        "line": node.lineno,
        "docstring": ast.get_docstring(node) or "",
        "bases": bases,
        "methods": methods,
    }


def _parse_imports(tree: ast.Module) -> list[str]:
    seen = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen[alias.name] = None
        elif isinstance(node, ast.ImportFrom) and node.module:
            seen[node.module] = None
    return list(seen)


def parse_module(path: Path, root: Path) -> dict | None:
    """Parse a Python file and return structured KG data, or None on failure."""
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            source = path.read_text(encoding="latin-1")
        except Exception:
            logger.warning("Cannot read %s", path)
            return None

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        logger.warning("Syntax error in %s: %s", path, exc)
        return None

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path

    file_path = str(relative).replace("\\", "/")
    module_name = file_path.removesuffix(".py").replace("/", ".")

    classes = [_parse_class(n) for n in tree.body if isinstance(n, ast.ClassDef)]
    functions = [
        _parse_function(n)
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]

    return {
        "module": {"name": module_name, "file_path": file_path},
        "imports": _parse_imports(tree),
        "classes": classes,
        "functions": functions,
    }
