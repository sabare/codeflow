from __future__ import annotations

import ast
import json
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Sequence


def normalize_whitespace(value: Any) -> str:
    return " ".join(str(value or "").split())


def clip_text(value: Any, limit: int) -> str:
    text = normalize_whitespace(value)
    if limit < 0:
        return text
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3].rstrip()}..."


def extract_docstring(source: str) -> str | None:
    cleaned = str(source or "").strip()
    if not cleaned:
        return None

    try:
        parsed = ast.parse(cleaned)
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

    return normalize_whitespace(docstring)


def stable_fingerprint(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def merge_unique(values: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    merged: List[str] = []
    for value in values:
        item = normalize_whitespace(value)
        if not item or item in seen:
            continue
        seen.add(item)
        merged.append(item)
    return merged


def _simple_name(value: str) -> str:
    cleaned = normalize_whitespace(value).replace(".", " ").replace("_", " ")
    return cleaned.strip()


def _source_line_count(source: str) -> int:
    return len([line for line in str(source or "").splitlines() if line.strip()])


def _top_level_return_node(source: str) -> ast.Return | None:
    try:
        parsed = ast.parse(str(source or ""))
    except SyntaxError:
        return None

    if not parsed.body:
        return None

    first_node = parsed.body[0]
    body = getattr(first_node, "body", None)
    if not isinstance(body, list):
        return None

    non_empty = [stmt for stmt in body if not isinstance(stmt, ast.Expr)]
    if len(non_empty) != 1:
        return None

    statement = non_empty[0]
    if isinstance(statement, ast.Return):
        return statement
    return None


def _looks_like_getter(name: str, source: str) -> bool:
    lowered = normalize_whitespace(name).lower()
    if lowered.startswith(("get_", "is_", "has_")):
        return True
    if lowered.endswith(("_getter", "_value", "_values", "_data", "_state", "_name", "_id")):
        return True

    return_node = _top_level_return_node(source)
    if return_node is None or return_node.value is None:
        return False

    return isinstance(return_node.value, (ast.Attribute, ast.Subscript, ast.Name))


def _looks_like_wrapper(source: str) -> bool:
    return_node = _top_level_return_node(source)
    if return_node is None or return_node.value is None:
        return False

    value = return_node.value
    if isinstance(value, ast.Call):
        return True

    if isinstance(value, ast.Name) and value.id in {"self", "cls"}:
        return True

    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        return value.attr not in {"append", "extend", "update"}

    return False


def classify_collapse_reason(name: str, source: str, child_count: int, depth: int = 0) -> str | None:
    if depth <= 0:
        return None

    cleaned_source = str(source or "").strip()
    if not cleaned_source:
        if child_count == 0 and normalize_whitespace(name).lower().endswith(("_helper", "_helpers", "_util", "_utils")):
            return "trivial helper"
        return None

    line_count = _source_line_count(cleaned_source)
    lowered_name = normalize_whitespace(name).lower()

    if child_count == 0:
        if _looks_like_getter(name, cleaned_source):
            return "getter"
        if _looks_like_wrapper(cleaned_source):
            return "pass-through wrapper"
        if line_count <= 6 and any(token in lowered_name for token in ("helper", "util", "utils", "wrapper")):
            return "utility leaf"
        if line_count <= 4 and lowered_name.startswith(("get_", "is_", "has_", "to_")):
            return "utility leaf"
        return None

    if child_count == 1 and _looks_like_wrapper(cleaned_source) and line_count <= 8:
        return "pass-through wrapper"

    return None


def summarize_source(name: str, source: str, child_count: int) -> str:
    docstring = extract_docstring(source)
    if docstring:
        return clip_text(docstring, 120)

    lowered_name = normalize_whitespace(name).replace(".", " ").replace("_", " ").strip()
    if not lowered_name:
        lowered_name = "Untitled"

    if child_count > 0:
        return f"Calls {child_count} project function{'s' if child_count != 1 else ''}."

    if lowered_name.startswith(("get ", "is ", "has ", "to ")):
        return f"Returns {lowered_name[4:].strip()}."

    return f"{_simple_name(name) or 'Function'} helper."


def _merge_cluster_members(cluster_nodes: Sequence[Dict[str, Any]], depth: int) -> Dict[str, Any]:
    members = merge_unique(
        member
        for node in cluster_nodes
        for member in (
            node.get("collapsed_members", []) if isinstance(node.get("collapsed_members", []), list) else []
        )
    )
    if not members:
        members = merge_unique(str(node.get("name", "")) for node in cluster_nodes)

    reasons = merge_unique(
        reason
        for node in cluster_nodes
        for reason in (
            [str(node.get("collapse_reason", ""))] if str(node.get("collapse_reason", "")).strip() else []
        )
    )
    children: List[Dict[str, Any]] = []
    for node in cluster_nodes:
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                children.append(child)

    collapsed_count = sum(int(node.get("collapsed_count", 1) or 1) for node in cluster_nodes)
    if collapsed_count <= 0:
        collapsed_count = len(members) or len(cluster_nodes)

    summary_bits = []
    if reasons:
        summary_bits.append(", ".join(reasons[:2]))
    if len(members) == 1:
        summary = f"Collapsed {members[0]}."
    elif len(members) <= 3:
        summary = f"Collapsed {len(members)} helper functions: {', '.join(members)}."
    else:
        summary = f"Collapsed {collapsed_count} helper functions."

    if summary_bits and len(members) > 1:
        summary = f"{summary.rstrip('.')} ({summary_bits[0]})."

    project_calls = merge_unique(
        call
        for node in cluster_nodes
        for call in (
            node.get("project_calls", []) if isinstance(node.get("project_calls", []), list) else []
        )
    )
    if not project_calls:
        project_calls = members

    calls = merge_unique(
        call for node in cluster_nodes for call in (node.get("calls", []) if isinstance(node.get("calls", []), list) else [])
    )
    if not calls:
        calls = project_calls

    stdlib_calls = merge_unique(
        call
        for node in cluster_nodes
        for call in (
            node.get("stdlib_calls", []) if isinstance(node.get("stdlib_calls", []), list) else []
        )
    )
    external_calls = merge_unique(
        call
        for node in cluster_nodes
        for call in (
            node.get("external_calls", []) if isinstance(node.get("external_calls", []), list) else []
        )
    )
    builtin_calls = merge_unique(
        call
        for node in cluster_nodes
        for call in (
            node.get("builtin_calls", []) if isinstance(node.get("builtin_calls", []), list) else []
        )
    )
    decorators = merge_unique(
        call
        for node in cluster_nodes
        for call in (
            node.get("decorators", []) if isinstance(node.get("decorators", []), list) else []
        )
    )

    merged = {
        "name": "Helper cluster" if len(cluster_nodes) > 1 else str(cluster_nodes[0].get("name", "Helper cluster")),
        "summary": summary,
        "kind": "cluster",
        "cluster_type": "helper",
        "collapsed_count": collapsed_count,
        "collapse_reason": ", ".join(reasons[:3]) if reasons else "helper cluster",
        "collapsed_members": members,
        "children": children,
        "expandable": bool(children),
        "recursive": False,
        "truncated": False,
        "depth": depth,
        "project_calls": project_calls,
        "calls": calls,
        "stdlib_calls": stdlib_calls,
        "external_calls": external_calls,
        "builtin_calls": builtin_calls,
        "decorators": decorators,
        "raw": {
            "source": "",
            "collapsed_members": members,
        },
    }
    return merged


def compact_tree(node: Dict[str, Any], source_lookup: Dict[str, str] | None = None, depth: int = 0) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}

    current: Dict[str, Any] = dict(node)
    name = normalize_whitespace(current.get("name", "")) or "Untitled"
    current["name"] = name

    source = normalize_whitespace(current.get("source", ""))
    if not source and source_lookup:
        source = normalize_whitespace(source_lookup.get(name, ""))
    if source:
        current["source"] = source

    is_placeholder = bool(current.get("recursive") or current.get("truncated"))
    raw_children = [child for child in current.get("children", []) or [] if isinstance(child, dict)]
    compacted_children = [compact_tree(child, source_lookup, depth + 1) for child in raw_children]
    compacted_children = [child for child in compacted_children if child]

    cluster_children = [child for child in compacted_children if child.get("kind") == "cluster"]
    visible_children = [child for child in compacted_children if child.get("kind") != "cluster"]

    if cluster_children:
        merged_cluster = _merge_cluster_members(cluster_children, depth + 1)
        insert_index = next(
            (index for index, child in enumerate(compacted_children) if child.get("kind") == "cluster"),
            len(visible_children),
        )
        visible_children.insert(insert_index, merged_cluster)

    child_count = len([child for child in visible_children if isinstance(child, dict)])
    current["children"] = visible_children
    current["expandable"] = child_count > 0
    current["kind"] = current.get("kind") or "function"
    if is_placeholder and normalize_whitespace(current.get("summary", "")):
        current["summary"] = normalize_whitespace(current.get("summary", ""))
    else:
        current["summary"] = summarize_source(name, source, child_count)

    collapse_reason = None if is_placeholder else classify_collapse_reason(name, source, child_count, depth)
    if collapse_reason:
        cluster_node = {
            "name": name,
            "summary": f"Collapsed {collapse_reason}.",
            "kind": "cluster",
            "cluster_type": "helper",
            "collapsed_count": 1,
            "collapse_reason": collapse_reason,
            "collapsed_members": [name],
            "children": visible_children,
            "expandable": bool(visible_children),
            "recursive": False,
            "truncated": False,
            "source": source,
            "depth": current.get("depth", depth),
            "project_calls": merge_unique(current.get("project_calls", [])) or [name],
            "calls": merge_unique(current.get("calls", [])) or [name],
            "stdlib_calls": merge_unique(current.get("stdlib_calls", [])),
            "external_calls": merge_unique(current.get("external_calls", [])),
            "builtin_calls": merge_unique(current.get("builtin_calls", [])),
            "decorators": merge_unique(current.get("decorators", [])),
            "raw": current,
        }
        return cluster_node

    return current


def _visible_label(node: Dict[str, Any]) -> str:
    name = normalize_whitespace(node.get("name", "")) or "Untitled"
    kind = normalize_whitespace(node.get("kind", "function"))
    if kind == "cluster":
        collapsed_count = int(node.get("collapsed_count", 1) or 1)
        label = f"{name} ({collapsed_count})"
    else:
        label = name
    return label


def flatten_tree(node: Dict[str, Any], depth: int = 0) -> List[str]:
    if not isinstance(node, dict):
        return []

    lines: List[str] = []
    prefix = "  " * depth + "- "
    label = _visible_label(node)
    summary = normalize_whitespace(node.get("summary", ""))
    if summary:
        line = f"{prefix}{label}: {summary}"
    else:
        line = f"{prefix}{label}"
    lines.append(line)

    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            lines.extend(flatten_tree(child, depth + 1))

    return lines


def _node_metrics(node: Dict[str, Any]) -> tuple[int, int, int]:
    if not isinstance(node, dict):
        return (0, 0, 0)

    kind = normalize_whitespace(node.get("kind", "function"))
    collapsed_count = int(node.get("collapsed_count", 0) or 0)
    children = [child for child in node.get("children", []) or [] if isinstance(child, dict)]

    if not children:
        depth = 1
        weight = 0 if kind == "cluster" else 1
        return depth, weight, -collapsed_count

    child_metrics = [_node_metrics(child) for child in children]
    max_depth = max(metric[0] for metric in child_metrics)
    weight = (0 if kind == "cluster" else 1) + sum(metric[1] for metric in child_metrics)
    return max_depth + 1, weight, -collapsed_count


def dominant_child(children: Sequence[Dict[str, Any]]) -> Dict[str, Any] | None:
    ranked: List[tuple[tuple[int, int, int, int, str], Dict[str, Any]]] = []
    for index, child in enumerate(children):
        if not isinstance(child, dict):
            continue
        depth, weight, collapse_penalty = _node_metrics(child)
        non_cluster_bias = 1 if normalize_whitespace(child.get("kind", "function")) != "cluster" else 0
        name = normalize_whitespace(child.get("name", "")).lower()
        ranked.append(((non_cluster_bias, depth, weight, collapse_penalty, -index, name), child))

    if not ranked:
        return None

    ranked.sort(reverse=True)
    return ranked[0][1]


def _step_summary(node: Dict[str, Any], is_root: bool = False) -> str:
    kind = normalize_whitespace(node.get("kind", "function"))
    name = normalize_whitespace(node.get("name", "")) or "Untitled"
    summary = normalize_whitespace(node.get("summary", ""))
    collapse_reason = normalize_whitespace(node.get("collapse_reason", ""))
    collapsed_count = int(node.get("collapsed_count", 0) or 0)

    generic_summaries = {"", "Calls 0 project functions."}

    if kind == "cluster":
        if collapsed_count > 1:
            if collapse_reason:
                return f"Collapsed {collapsed_count} helper functions ({collapse_reason})."
            return f"Collapsed {collapsed_count} helper functions."
        if collapse_reason:
            return f"Collapsed {collapse_reason}."
        return f"Collapsed helper cluster {name}."

    if summary and summary not in generic_summaries and not summary.startswith("Calls "):
        return summary

    display_name = _simple_name(name)
    if is_root:
        return f"Start at {display_name}."
    if display_name:
        return display_name
    return "Continue execution."


def build_flow_steps(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    current = tree if isinstance(tree, dict) else None
    depth = 0

    while isinstance(current, dict):
        steps.append(
            {
                "name": normalize_whitespace(current.get("name", "")) or "Untitled",
                "kind": normalize_whitespace(current.get("kind", "function")),
                "summary": _step_summary(current, is_root=depth == 0),
                "collapsed_count": int(current.get("collapsed_count", 0) or 0),
                "collapse_reason": normalize_whitespace(current.get("collapse_reason", "")),
                "depth": depth,
            }
        )
        next_child = dominant_child([child for child in current.get("children", []) or [] if isinstance(child, dict)])
        if next_child is None:
            break
        current = next_child
        depth += 1

    return steps


def flow_summary_from_steps(steps: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for index, step in enumerate(steps, start=1):
        summary = normalize_whitespace(step.get("summary", ""))
        if not summary:
            summary = "Continue execution."
        if summary.endswith("."):
            sentence = summary
        else:
            sentence = f"{summary}."
        lines.append(f"{index}. {sentence}")
    return "\n".join(lines)


def tree_signature(node: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(node, dict):
        return {}

    children = [tree_signature(child) for child in node.get("children", []) or [] if isinstance(child, dict)]
    signature = {
        "name": normalize_whitespace(node.get("name", "")),
        "kind": normalize_whitespace(node.get("kind", "function")),
        "summary": normalize_whitespace(node.get("summary", "")),
        "collapse_reason": normalize_whitespace(node.get("collapse_reason", "")),
        "collapsed_count": int(node.get("collapsed_count", 0) or 0),
        "recursive": bool(node.get("recursive", False)),
        "truncated": bool(node.get("truncated", False)),
        "source_hash": sha256(normalize_whitespace(node.get("source", "")).encode("utf-8")).hexdigest(),
        "children": children,
    }
    return signature


def prompt_flow_steps(steps: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for index, step in enumerate(steps, start=1):
        name = normalize_whitespace(step.get("name", ""))
        summary = normalize_whitespace(step.get("summary", ""))
        if summary.endswith("."):
            summary_text = summary
        elif summary:
            summary_text = f"{summary}."
        else:
            summary_text = "Continue execution."
        lines.append(f"{index}. {name}: {summary_text}")
    return "\n".join(lines)
