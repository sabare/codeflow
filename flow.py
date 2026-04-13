from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Set

from utilities import call_llm


CACHE_PATH = Path(".cache/function_summaries.json")


def build_flow_tree(
    analysis: Dict[str, object],
    root_function: str,
    max_depth: int | None = None,
    include_stdlib: bool = True,
    include_external: bool = True,
    include_builtin: bool = True,
) -> Dict[str, Any]:
    project_graph = analysis.get("project_graph", {})
    stdlib_calls = analysis.get("stdlib_calls", {})
    external_calls = analysis.get("external_calls", {})
    builtin_calls = analysis.get("builtin_calls", {})
    decorator_calls = analysis.get("decorator_calls", {})
    sources = analysis.get("sources", {})
    depth_limit = None if max_depth is None else max(0, max_depth)

    if root_function not in project_graph:
        return {
            "root": root_function,
            "found": False,
            "message": f"{root_function} was not found in the project graph.",
            "available_functions": sorted(project_graph.keys()),
        }

    def _visible_calls(calls: object, enabled: bool) -> List[str]:
        if not enabled or not isinstance(calls, list):
            return []
        return [str(call) for call in calls if str(call)]

    def _depth_summary(name: str, project_children: List[str]) -> str:
        if project_children:
            return f"Calls {len(project_children)} project functions. Depth limit reached."
        return _fallback_summary(project_children)

    def expand(name: str, depth: int, path: Set[str]) -> Dict[str, Any]:
        project_children = list(project_graph.get(name, []))
        node = {
            "name": name,
            "depth": depth,
            "summary": _fallback_summary(project_children),
            "children": [],
            "project_calls": project_children,
            "stdlib_calls": _visible_calls(stdlib_calls.get(name, []), include_stdlib),
            "builtin_calls": _visible_calls(builtin_calls.get(name, []), include_builtin),
            "external_calls": _visible_calls(external_calls.get(name, []), include_external),
            "decorators": list(decorator_calls.get(name, [])),
            "source": str(sources.get(name, "")),
            "expandable": bool(project_children),
            "truncated": False,
        }

        if depth_limit is not None and depth >= depth_limit:
            if project_children:
                node["summary"] = _depth_summary(name, project_children)
                node["truncated"] = True
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
    reachable_names = _collect_tree_names(tree)
    batched_summaries = summarize_functions(
        {
            name: str(sources.get(name, ""))
            for name in sorted(reachable_names)
            if isinstance(sources.get(name, ""), str) and str(sources.get(name, "")).strip()
        }
    )
    if batched_summaries:
        _apply_summaries(tree, batched_summaries)

    flow_summary = summarize_flow(sources.get(root_function, ""), tree)
    if not flow_summary:
        flow_summary = "\n".join(_flatten_call_tree(tree))

    return {
        "root": root_function,
        "max_depth": max_depth,
        "filters": {
            "stdlib": include_stdlib,
            "external": include_external,
            "builtin": include_builtin,
        },
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


def _fallback_summary(children: List[str]) -> str:
    if children:
        return f"Calls {len(children)} project functions."
    return "Calls 0 project functions."


def summarize_functions(codes_by_name: Dict[str, str]) -> Dict[str, str]:
    if not codes_by_name:
        return {}

    cache = _load_summary_cache()
    summaries: Dict[str, str] = {}
    to_summarize: Dict[str, str] = {}

    for name, code in sorted(codes_by_name.items()):
        cleaned_code = code.strip()
        if not cleaned_code:
            continue
        fingerprint = _fingerprint(cleaned_code)
        cached_entry = cache.get(name)
        if (
            isinstance(cached_entry, dict)
            and cached_entry.get("fingerprint") == fingerprint
            and isinstance(cached_entry.get("summary"), str)
            and cached_entry["summary"].strip()
        ):
            summaries[name] = " ".join(cached_entry["summary"].split())
            continue

        to_summarize[name] = cleaned_code

    if not to_summarize:
        return summaries

    payload = [
        {"name": name, "code": code}
        for name, code in sorted(to_summarize.items())
        if code.strip()
    ]
    if not payload:
        return summaries

    prompt = f"""Summarize each function in one short sentence.
Return strict JSON only in the format:
{{"function_name": "summary", "...": "..."}}

Summaries should focus on purpose, not implementation details.
Keep each summary under 20 words.

Functions:
{json.dumps(payload, indent=2)}
"""
    response = call_llm(prompt).strip()
    if not response:
        return summaries

    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return summaries

    if not isinstance(parsed, dict):
        return summaries

    updated_cache = dict(cache)
    for name, summary in parsed.items():
        if not isinstance(name, str) or not isinstance(summary, str):
            continue
        cleaned = " ".join(summary.split())
        if cleaned:
            words = cleaned.split()
            if len(words) > 20:
                cleaned = " ".join(words[:20])
            summaries[name] = cleaned
            updated_cache[name] = {
                "summary": cleaned,
                "fingerprint": _fingerprint(to_summarize.get(name, "")),
            }

    _save_summary_cache(updated_cache)

    return summaries


def _fingerprint(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()


def _load_summary_cache() -> Dict[str, Dict[str, str]]:
    try:
        if not CACHE_PATH.exists():
            return {}
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(parsed, dict):
        return {}

    cache: Dict[str, Dict[str, str]] = {}
    for name, entry in parsed.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        summary = entry.get("summary")
        fingerprint = entry.get("fingerprint")
        if isinstance(summary, str) and isinstance(fingerprint, str):
            cache[name] = {"summary": summary, "fingerprint": fingerprint}
    return cache


def _save_summary_cache(cache: Dict[str, Dict[str, str]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, sort_keys=True)
    except OSError:
        pass


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


def _collect_tree_names(node: Dict[str, Any]) -> Set[str]:
    names = {str(node.get("name", ""))}
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            names.update(_collect_tree_names(child))
    return {name for name in names if name}


def _apply_summaries(node: Dict[str, Any], summaries: Dict[str, str]) -> None:
    name = str(node.get("name", ""))
    if name in summaries:
        node["summary"] = summaries[name]
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            _apply_summaries(child, summaries)
