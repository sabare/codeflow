from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, List, Set

from constants import IGNORED_DIRS, STDLIB_MODULES


def iter_python_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        yield path


def module_name_for(root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else file_path.stem


def get_qualified_name(scope: List[str], name: str) -> str:
    if not scope:
        return name
    return ".".join([*scope, name])


def get_dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = get_dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return get_dotted_name(node.value)
    if isinstance(node, ast.Call):
        return get_dotted_name(node.func)
    return None


def iter_target_names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for element in node.elts:
            yield from iter_target_names(element)


def is_stdlib_module(module_name: str) -> bool:
    return module_name.split(".", 1)[0] in STDLIB_MODULES


def is_project_module(module_name: str, project_roots: Set[str]) -> bool:
    return module_name.split(".", 1)[0] in project_roots
