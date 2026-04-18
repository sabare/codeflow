from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flow_utils import compact_tree, summarize_source


logger = logging.getLogger("code-analysis-visualizer")


try:
    from analysis import build_analysis as _raw_build_analysis
except Exception:  # pragma: no cover - fallback for missing analyzer imports
    _raw_build_analysis = None


def build_analysis(path: Path) -> Dict[str, Any]:
    logger.info("build_analysis started for path=%s", path)
    if _raw_build_analysis is None:
        logger.info("Using mock analysis because the real analyzer import is unavailable")
        return _mock_analysis()

    try:
        raw = _raw_build_analysis(path)
    except Exception as exc:
        logger.exception("Using mock analysis because the real analyzer raised: %s", exc)
        return _mock_analysis()

    if not isinstance(raw, dict):
        logger.warning("Using mock analysis because the real analyzer returned %s instead of dict", type(raw).__name__)
        return _mock_analysis()

    if isinstance(raw.get("tree"), dict):
        logger.info("Raw analyzer already returned a tree for path=%s", path)
        return raw

    raw = dict(raw)
    raw["tree"] = _build_tree(path, raw)
    logger.info("Built flow tree for path=%s", path)
    return raw


def _build_tree(path: Path, analysis: Dict[str, Any]) -> Dict[str, Any]:
    project_graph = analysis.get("project_graph")
    sources = analysis.get("sources")
    definitions = analysis.get("definitions")

    if not isinstance(project_graph, dict):
        project_graph = {}
    if not isinstance(sources, dict):
        sources = {}
    if not isinstance(definitions, dict):
        definitions = {}

    function_names: Set[str] = set()
    raw_functions = definitions.get("functions", [])
    if isinstance(raw_functions, list):
        function_names.update(str(name) for name in raw_functions)
    function_names.update(str(name) for name in project_graph.keys())

    if not function_names:
        return {
            "name": _display_name(path),
            "summary": "No Python functions were found.",
            "children": [],
        }

    incoming_counts: Dict[str, int] = {name: 0 for name in function_names}
    for callees in project_graph.values():
        if not isinstance(callees, list):
            continue
        for callee in callees:
            callee_name = str(callee)
            incoming_counts.setdefault(callee_name, 0)
            incoming_counts[callee_name] += 1
            function_names.add(callee_name)

    roots = [name for name in sorted(function_names) if incoming_counts.get(name, 0) == 0]
    if not roots:
        roots = sorted(function_names)

    def summarize(name: str) -> str:
        source = sources.get(name, "")
        child_count = len(project_graph.get(name, [])) if isinstance(project_graph.get(name, []), list) else 0
        if isinstance(source, str):
            return summarize_source(name, source, child_count)
        return summarize_source(name, "", child_count)

    def expand(name: str, path_stack: Set[str]) -> Dict[str, Any]:
        raw_children = project_graph.get(name, [])
        children = sorted({str(child) for child in raw_children if str(child)})

        node: Dict[str, Any] = {
            "name": name,
            "summary": summarize(name),
            "children": [],
            "kind": "function",
            "source": str(sources.get(name, "")),
        }

        for child in children:
            if child in path_stack:
                node["children"].append(
                    {
                        "name": child,
                        "summary": "Recursive reference",
                        "children": [],
                    }
                )
                continue

            if child not in function_names:
                node["children"].append(
                    {
                        "name": child,
                        "summary": "Referenced call",
                        "children": [],
                    }
                )
                continue

            node["children"].append(expand(child, path_stack | {child}))

        return node

    tree = {
        "name": _display_name(path),
        "summary": f"{len(roots)} entry point(s), {len(function_names)} analyzed symbol(s)",
        "children": [expand(root, {root}) for root in roots],
        "kind": "root",
    }

    compacted = compact_tree(tree, sources)
    compacted["name"] = _display_name(path)
    compacted["summary"] = f"{len(roots)} entry point(s), {len(function_names)} analyzed symbol(s)"
    compacted["kind"] = "root"
    return compacted


def _display_name(path: Path) -> str:
    resolved = path.resolve()
    return resolved.name or str(resolved)


def _extract_docstring(source: str) -> str | None:
    try:
        parsed = ast.parse(source)
    except SyntaxError:
        return None

    if not parsed.body:
        return None

    first_node = parsed.body[0]
    if isinstance(first_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        docstring = ast.get_docstring(first_node)
    else:
        docstring = ast.get_docstring(parsed)

    if not docstring:
        return None

    return " ".join(docstring.strip().split())


def browse_directory(path: Path) -> Dict[str, Any]:
    resolved = path.expanduser().resolve()
    logger.info("Browsing directory resolved=%s", resolved)
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"{resolved} is not a valid directory")

    directories = []
    files = []

    for child in sorted(resolved.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.is_dir():
            directories.append({"name": child.name, "path": str(child)})
        elif child.is_file() and child.suffix == ".py":
            files.append({"name": child.name, "path": str(child)})

    return {
        "path": str(resolved),
        "parent": str(resolved.parent) if resolved.parent != resolved else None,
        "directories": directories,
        "files": files,
    }


def list_functions_in_file(path: Path) -> Dict[str, Any]:
    resolved = path.expanduser().resolve()
    logger.info("Listing functions in file resolved=%s", resolved)
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"{resolved} is not a valid file")

    source = resolved.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(resolved))
    collector = _FunctionCollector()
    collector.visit(tree)

    return {
        "path": str(resolved),
        "functions": sorted(collector.function_names),
    }


def _mock_analysis() -> Dict[str, Any]:
    return {
        "tree": {
            "name": "build_analysis",
            "summary": "Root function",
            "children": [
                {
                    "name": "collect_module_bindings",
                    "summary": "Collect bindings",
                    "children": [],
                },
                {
                    "name": "CallGraphCollector",
                    "summary": "Analyzes calls",
                    "children": [],
                },
            ],
        }
    }


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_names: Set[str] = set()
        self.scope: List[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_names.add(_qualified_name(self.scope, node.name))
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_names.add(_qualified_name(self.scope, node.name))
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()


def _qualified_name(scope: List[str], name: str) -> str:
    if not scope:
        return name
    return ".".join([*scope, name])
