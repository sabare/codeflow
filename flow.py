from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from utilities import call_llm


def build_flow_tree(analysis: Dict[str, object], root_function: str, max_depth: int = 2) -> Dict[str, Any]:
    project_graph = analysis.get("project_graph", {})
    stdlib_calls = analysis.get("stdlib_calls", {})
    external_calls = analysis.get("external_calls", {})
    builtin_calls = analysis.get("builtin_calls", {})
    decorator_calls = analysis.get("decorator_calls", {})
    sources = analysis.get("sources", {})
    summary_cache: Dict[str, str] = {}

    if root_function not in project_graph:
        return {
            "root": root_function,
            "found": False,
            "message": f"{root_function} was not found in the project graph.",
            "available_functions": sorted(project_graph.keys()),
        }

    def get_summary(name: str) -> str:
        if name in summary_cache:
            return summary_cache[name]

        code = sources.get(name, "")
        if code:
            summary = summarize_function(code)
            if summary:
                summary_cache[name] = summary
                return summary

        children = list(project_graph.get(name, []))
        summary_cache[name] = f"Calls {', '.join(children[:3])}." if children else "No project calls detected."
        return summary_cache[name]

    def expand(name: str, depth: int, path: Set[str]) -> Dict[str, Any]:
        project_children = list(project_graph.get(name, []))
        node = {
            "name": name,
            "depth": depth,
            "summary": get_summary(name),
            "children": [],
            "project_calls": project_children,
            "stdlib_calls": list(stdlib_calls.get(name, [])),
            "builtin_calls": list(builtin_calls.get(name, [])),
            "external_calls": list(external_calls.get(name, [])),
            "decorators": list(decorator_calls.get(name, [])),
            "expandable": bool(project_children),
            "truncated": depth >= max_depth and bool(project_children),
        }

        if depth >= max_depth:
            return node

        for child in project_children:
            if child in path:
                node["children"].append(
                    {
                        "name": child,
                        "depth": depth + 1,
                        "children": [],
                        "recursive": True,
                        "expandable": False,
                        "truncated": False,
                    }
                )
                continue

            node["children"].append(expand(child, depth + 1, path | {child}))

        return node

    tree = expand(root_function, 0, {root_function})
    flow_summary = summarize_flow(sources.get(root_function, ""), tree)
    if not flow_summary:
        flow_summary = "\n".join(_flatten_call_tree(tree))

    return {
        "root": root_function,
        "max_depth": max_depth,
        "found": True,
        "tree": tree,
        "flow_summary": flow_summary,
    }


def _flatten_call_tree(call_tree: Dict[str, Any], depth: int = 0) -> List[str]:
    name = str(call_tree.get("name", ""))
    summary = str(call_tree.get("summary", "")).strip()
    if name and summary:
        line = f"{'  ' * depth}- {name}: {summary}"
    elif name:
        line = f"{'  ' * depth}- {name}"
    else:
        line = f"{'  ' * depth}- <unknown>"
    lines = [line]
    for child in call_tree.get("children", []) or []:
        if isinstance(child, dict):
            lines.extend(_flatten_call_tree(child, depth + 1))
    return lines


def summarize_function(code: str) -> str:
    prompt = f"""Summarize what this function does in one sentence.
Focus on purpose, not implementation details.
Keep it under 20 words.
Return one clean line only.

Function code:
{code}
"""
    summary = call_llm(prompt).strip()
    summary = " ".join(summary.split())
    words = summary.split()
    if len(words) > 20:
        summary = " ".join(words[:20])
    return summary


def summarize_flow(root_code: str, call_tree: dict) -> str:
    flattened_tree = "\n".join(_flatten_call_tree(call_tree))
    prompt = f"""Explain this execution flow in concise numbered steps.
Use function names from the call tree.
Group related calls when it makes the flow clearer.
Keep the output readable and brief.
Return only the numbered explanation.

Root function code:
{root_code}

Call tree:
{flattened_tree}
"""
    flow = call_llm(prompt).strip()
    if not flow:
        return flattened_tree
    flow = re.sub(r"\n{3,}", "\n\n", flow)
    return flow
