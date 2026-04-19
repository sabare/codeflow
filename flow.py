from __future__ import annotations

import json
import os
import re
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

from flow_utils import (
    build_flow_steps,
    clip_text,
    compact_tree,
    flow_summary_from_steps,
    flatten_tree,
    normalize_whitespace,
    prompt_flow_steps,
    summarize_source,
    stable_fingerprint,
    tree_signature,
)
from utilities import call_llm


CACHE_PATH = Path(".cache/flow_explanations.json")
PROMPT_VERSION = "flow-path-v1"

_CACHE_LOCK = threading.Lock()
_PENDING_LOCK = threading.Lock()
_PENDING_EXPLANATIONS: set[str] = set()
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flow-explanation")


def build_flow_tree(
    analysis: Dict[str, object],
    root_function: str,
    max_depth: int | None = None,
    include_stdlib: bool = True,
    include_external: bool = True,
    include_builtin: bool = True,
    *,
    async_enrichment: bool = False,
    wait_for_explanation: bool = False,
) -> Dict[str, Any]:
    project_graph = analysis.get("project_graph", {})
    stdlib_calls = analysis.get("stdlib_calls", {})
    external_calls = analysis.get("external_calls", {})
    builtin_calls = analysis.get("builtin_calls", {})
    decorator_calls = analysis.get("decorator_calls", {})
    sources = analysis.get("sources", {})
    depth_limit = None if max_depth is None else max(0, max_depth)

    if not isinstance(project_graph, dict):
        project_graph = {}
    if not isinstance(sources, dict):
        sources = {}

    if root_function not in project_graph:
        return {
            "root": root_function,
            "found": False,
            "message": f"{root_function} was not found in the project graph.",
            "available_functions": sorted(project_graph.keys()),
        }

    def _expand(name: str, depth: int, path: set[str]) -> Dict[str, Any]:
        project_children = _project_children(project_graph.get(name, []))
        source = normalize_whitespace(sources.get(name, ""))

        node: Dict[str, Any] = {
            "name": name,
            "depth": depth,
            "summary": summarize_source(name, source, len(project_children)),
            "children": [],
            "calls": project_children,
            "project_calls": project_children,
            "stdlib_calls": _visible_calls(stdlib_calls.get(name, []), include_stdlib),
            "builtin_calls": _visible_calls(builtin_calls.get(name, []), include_builtin),
            "external_calls": _visible_calls(external_calls.get(name, []), include_external),
            "decorators": _visible_calls(decorator_calls.get(name, []), True),
            "source": str(sources.get(name, "")),
            "expandable": bool(project_children),
            "truncated": False,
            "recursive": False,
            "kind": "function",
        }

        if depth_limit is not None and depth >= depth_limit:
            if project_children:
                node["summary"] = _depth_limit_summary(project_children)
                node["truncated"] = True
            return node

        for child in project_children:
            if child in path:
                node["children"].append(
                    {
                        "name": child,
                        "depth": depth + 1,
                        "summary": "Recursive reference",
                        "children": [],
                        "recursive": True,
                        "expandable": False,
                        "truncated": False,
                        "kind": "function",
                    }
                )
                continue

            node["children"].append(_expand(child, depth + 1, path | {child}))

        return node

    tree = compact_tree(_expand(root_function, 0, {root_function}), sources)
    graph = _build_flow_dag(
        root_function=root_function,
        project_graph=project_graph,
        stdlib_calls=stdlib_calls,
        external_calls=external_calls,
        builtin_calls=builtin_calls,
        decorator_calls=decorator_calls,
        sources=sources,
        include_stdlib=include_stdlib,
        include_external=include_external,
        include_builtin=include_builtin,
    )
    flow_steps = build_flow_steps(tree)
    flow_summary = flow_summary_from_steps(flow_steps)
    if not flow_summary:
        flow_summary = "\n".join(flatten_tree(tree))

    request_fingerprint = _flow_fingerprint(
        root_function=root_function,
        tree=tree,
        max_depth=max_depth,
        include_stdlib=include_stdlib,
        include_external=include_external,
        include_builtin=include_builtin,
    )
    explanation_key = _explanation_cache_key(request_fingerprint)
    cached_entry = _read_flow_cache_entry(explanation_key)

    explanation_status = "unavailable"
    explanation_error = None

    if isinstance(cached_entry, dict):
        cached_status = normalize_whitespace(cached_entry.get("status", ""))
        cached_summary = normalize_whitespace(cached_entry.get("summary", ""))
        cached_error = normalize_whitespace(cached_entry.get("error", ""))
        if cached_status == "ready" and cached_summary:
            flow_summary = cached_summary
            explanation_status = "ready"
        elif cached_status == "error":
            explanation_status = "error"
            explanation_error = cached_error or "LLM explanation failed."

    if wait_for_explanation and _llm_available() and explanation_status != "ready":
        ready_entry = _generate_and_store_explanation(
            explanation_key=explanation_key,
            request_fingerprint=request_fingerprint,
            root_function=root_function,
            root_code=str(sources.get(root_function, "")),
            tree=tree,
            flow_steps=flow_steps,
        )
        if ready_entry and normalize_whitespace(ready_entry.get("status", "")) == "ready":
            flow_summary = normalize_whitespace(ready_entry.get("summary", "")) or flow_summary
            explanation_status = "ready"
            explanation_error = None
        elif ready_entry and normalize_whitespace(ready_entry.get("status", "")) == "error":
            explanation_status = "error"
            explanation_error = normalize_whitespace(ready_entry.get("error", ""))
    elif explanation_status == "unavailable" and async_enrichment and _llm_available():
        _schedule_flow_explanation(
            explanation_key=explanation_key,
            request_fingerprint=request_fingerprint,
            root_function=root_function,
            root_code=str(sources.get(root_function, "")),
            tree=tree,
            flow_steps=flow_steps,
        )
        explanation_status = "pending"

    response: Dict[str, Any] = {
        "root": root_function,
        "max_depth": max_depth,
        "filters": {
            "stdlib": include_stdlib,
            "external": include_external,
            "builtin": include_builtin,
        },
        "found": True,
        "tree": tree,
        "graph": graph,
        "flow_steps": flow_steps,
        "flow_summary": flow_summary,
        "flow_fingerprint": request_fingerprint,
        "flow_explanation_status": explanation_status,
    }

    if explanation_error:
        response["flow_explanation_error"] = explanation_error

    return response


def get_flow_explanation_status(flow_fingerprint: str) -> Dict[str, Any]:
    request_fingerprint = normalize_whitespace(flow_fingerprint)
    if not request_fingerprint:
        return {
            "flow_fingerprint": "",
            "flow_explanation_status": "error",
            "flow_explanation_error": "flow_fingerprint is required.",
        }

    explanation_key = _explanation_cache_key(request_fingerprint)
    cached_entry = _read_flow_cache_entry(explanation_key)
    if isinstance(cached_entry, dict):
        cached_status = normalize_whitespace(cached_entry.get("status", ""))
        cached_summary = normalize_whitespace(cached_entry.get("summary", ""))
        cached_error = normalize_whitespace(cached_entry.get("error", ""))
        if cached_status == "ready" and cached_summary:
            return {
                "flow_fingerprint": request_fingerprint,
                "flow_explanation_status": "ready",
                "flow_summary": cached_summary,
            }
        if cached_status == "error":
            return {
                "flow_fingerprint": request_fingerprint,
                "flow_explanation_status": "error",
                "flow_explanation_error": cached_error or "LLM explanation failed.",
            }

    status = "pending" if _llm_available() else "unavailable"
    return {
        "flow_fingerprint": request_fingerprint,
        "flow_explanation_status": status,
    }


def _project_children(children: object) -> List[str]:
    if not isinstance(children, list):
        return []
    return [normalize_whitespace(child) for child in children if normalize_whitespace(child)]


def _visible_calls(calls: object, enabled: bool) -> List[str]:
    if not enabled or not isinstance(calls, list):
        return []
    return [normalize_whitespace(call) for call in calls if normalize_whitespace(call)]


def _infer_graph_role(name: str, depth: int, child_count: int) -> str:
    normalized = normalize_whitespace(name).lower()
    if depth == 0:
        return "root"
    if depth == 1 and normalized in {"main", "run", "start", "entry", "app", "index", "init", "setup", "bootstrap", "execute"}:
        return "entrypoint"
    if child_count == 0:
        return "helper"
    if name and name[0].isupper():
        return "class"
    return "function"


def _build_flow_dag(
    *,
    root_function: str,
    project_graph: Dict[str, Any],
    stdlib_calls: Dict[str, Any],
    external_calls: Dict[str, Any],
    builtin_calls: Dict[str, Any],
    decorator_calls: Dict[str, Any],
    sources: Dict[str, Any],
    include_stdlib: bool,
    include_external: bool,
    include_builtin: bool,
) -> Dict[str, Any]:
    visited: Set[str] = set()
    discovery_order: List[str] = []
    edge_pairs: Set[tuple[str, str]] = set()
    queue = deque([root_function])

    while queue:
        current = normalize_whitespace(queue.popleft())
        if not current or current in visited:
            continue
        visited.add(current)
        discovery_order.append(current)

        children = sorted(set(_project_children(project_graph.get(current, []))))
        for child in children:
            edge_pairs.add((current, child))
            if child not in visited and child not in queue:
                queue.append(child)

    if root_function not in visited:
        visited.add(root_function)
        discovery_order.insert(0, root_function)

    depth_by_node: Dict[str, int] = {root_function: 0}
    bfs_queue = deque([root_function])
    outgoing_map: Dict[str, List[str]] = {}
    for source, target in edge_pairs:
        outgoing_map.setdefault(source, []).append(target)
    for source in outgoing_map:
        outgoing_map[source] = sorted(set(outgoing_map[source]))

    while bfs_queue:
        current = bfs_queue.popleft()
        current_depth = depth_by_node.get(current, 0)
        for child in outgoing_map.get(current, []):
            next_depth = current_depth + 1
            if child not in depth_by_node or next_depth < depth_by_node[child]:
                depth_by_node[child] = next_depth
                bfs_queue.append(child)

    for name in discovery_order:
        if name not in depth_by_node:
            depth_by_node[name] = max(depth_by_node.values(), default=0) + 1

    nodes: List[Dict[str, Any]] = []
    for name in discovery_order:
        children = outgoing_map.get(name, [])
        source = str(sources.get(name, ""))
        depth = depth_by_node.get(name, 0)
        nodes.append(
            {
                "id": name,
                "name": name,
                "summary": summarize_source(name, source, len(children)),
                "kind": "function",
                "depth": depth,
                "role": _infer_graph_role(name, depth, len(children)),
                "calls": children,
                "project_calls": children,
                "stdlib_calls": _visible_calls(stdlib_calls.get(name, []), include_stdlib),
                "external_calls": _visible_calls(external_calls.get(name, []), include_external),
                "builtin_calls": _visible_calls(builtin_calls.get(name, []), include_builtin),
                "decorators": _visible_calls(decorator_calls.get(name, []), True),
                "collapsed_members": [],
                "collapsed_count": 0,
                "collapse_reason": "",
                "recursive": False,
                "truncated": False,
                "source": source,
                "child_count": len(children),
            }
        )

    edges = [
        {"id": f"{source}->{target}", "source": source, "target": target}
        for source, target in sorted(edge_pairs, key=lambda pair: (depth_by_node.get(pair[0], 0), pair[0], pair[1]))
    ]

    return {
        "root": root_function,
        "nodes": nodes,
        "edges": edges,
    }


def _depth_limit_summary(project_children: Sequence[str]) -> str:
    if project_children:
        return f"Calls {len(project_children)} project functions. Depth limit reached."
    return "Depth limit reached."


def _humanize_name(name: str) -> str:
    cleaned = normalize_whitespace(name).replace(".", " ").replace("_", " ").strip()
    return cleaned or "Function"


def _flow_fingerprint(
    root_function: str,
    tree: Dict[str, Any],
    max_depth: int | None,
    include_stdlib: bool,
    include_external: bool,
    include_builtin: bool,
) -> str:
    payload = {
        "root_function": normalize_whitespace(root_function),
        "max_depth": max_depth,
        "filters": {
            "stdlib": include_stdlib,
            "external": include_external,
            "builtin": include_builtin,
        },
        "tree": tree_signature(tree),
        "schema": 1,
    }
    return stable_fingerprint(payload)


def _explanation_cache_key(request_fingerprint: str) -> str:
    model = normalize_whitespace(os.getenv("OPENAI_MODEL", "gpt-5-nano"))
    payload = {
        "request_fingerprint": request_fingerprint,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "schema": 1,
    }
    return stable_fingerprint(payload)


def _llm_available() -> bool:
    return bool(normalize_whitespace(os.getenv("OPENAI_API_KEY", "")))


def _read_flow_cache_entry(cache_key: str) -> Dict[str, Any] | None:
    with _CACHE_LOCK:
        cache = _load_flow_cache()
    entry = cache.get(cache_key)
    if not isinstance(entry, dict):
        return None

    normalized = {
        "status": normalize_whitespace(entry.get("status", "")),
        "summary": normalize_whitespace(entry.get("summary", "")),
        "error": normalize_whitespace(entry.get("error", "")),
        "request_fingerprint": normalize_whitespace(entry.get("request_fingerprint", "")),
        "model": normalize_whitespace(entry.get("model", "")),
        "prompt_version": normalize_whitespace(entry.get("prompt_version", "")),
        "updated_at": normalize_whitespace(entry.get("updated_at", "")),
    }
    if normalized["status"] == "ready" and not normalized["summary"]:
        return None
    return normalized


def _load_flow_cache() -> Dict[str, Dict[str, Any]]:
    try:
        if not CACHE_PATH.exists():
            return {}
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(parsed, dict):
        return {}

    if isinstance(parsed.get("entries"), dict):
        parsed = parsed["entries"]

    cache: Dict[str, Dict[str, Any]] = {}
    for key, entry in parsed.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        cache[key] = {
            "status": normalize_whitespace(entry.get("status", "")),
            "summary": normalize_whitespace(entry.get("summary", "")),
            "error": normalize_whitespace(entry.get("error", "")),
            "request_fingerprint": normalize_whitespace(entry.get("request_fingerprint", "")),
            "model": normalize_whitespace(entry.get("model", "")),
            "prompt_version": normalize_whitespace(entry.get("prompt_version", "")),
            "updated_at": normalize_whitespace(entry.get("updated_at", "")),
        }
    return cache


def _save_flow_cache(cache: Dict[str, Dict[str, Any]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "entries": cache,
        }
        with CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except OSError:
        pass


def _write_flow_cache_entry(cache_key: str, entry: Dict[str, Any]) -> None:
    with _CACHE_LOCK:
        cache = _load_flow_cache()
        cache[cache_key] = entry
        _save_flow_cache(cache)


def _schedule_flow_explanation(
    *,
    explanation_key: str,
    request_fingerprint: str,
    root_function: str,
    root_code: str,
    tree: Dict[str, Any],
    flow_steps: Sequence[Dict[str, Any]],
) -> None:
    with _PENDING_LOCK:
        if explanation_key in _PENDING_EXPLANATIONS:
            return
        _PENDING_EXPLANATIONS.add(explanation_key)

    _EXECUTOR.submit(
        _run_flow_explanation_job,
        explanation_key,
        request_fingerprint,
        root_function,
        root_code,
        tree,
        list(flow_steps),
    )


def _is_flow_pending(explanation_key: str) -> bool:
    with _PENDING_LOCK:
        return explanation_key in _PENDING_EXPLANATIONS


def _run_flow_explanation_job(
    explanation_key: str,
    request_fingerprint: str,
    root_function: str,
    root_code: str,
    tree: Dict[str, Any],
    flow_steps: Sequence[Dict[str, Any]],
) -> None:
    try:
        entry = _generate_flow_explanation(
            request_fingerprint=request_fingerprint,
            root_function=root_function,
            root_code=root_code,
            tree=tree,
            flow_steps=flow_steps,
        )
        _write_flow_cache_entry(explanation_key, entry)
    finally:
        with _PENDING_LOCK:
            _PENDING_EXPLANATIONS.discard(explanation_key)


def _generate_and_store_explanation(
    *,
    explanation_key: str,
    request_fingerprint: str,
    root_function: str,
    root_code: str,
    tree: Dict[str, Any],
    flow_steps: Sequence[Dict[str, Any]],
) -> Dict[str, Any] | None:
    entry = _generate_flow_explanation(
        request_fingerprint=request_fingerprint,
        root_function=root_function,
        root_code=root_code,
        tree=tree,
        flow_steps=flow_steps,
    )
    if entry:
        _write_flow_cache_entry(explanation_key, entry)
    return entry


def _generate_flow_explanation(
    *,
    request_fingerprint: str,
    root_function: str,
    root_code: str,
    tree: Dict[str, Any],
    flow_steps: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    if not _llm_available():
        return {
            "status": "error",
            "summary": "",
            "error": "OpenAI API key is not configured.",
            "request_fingerprint": request_fingerprint,
            "model": normalize_whitespace(os.getenv("OPENAI_MODEL", "gpt-5-nano")),
            "prompt_version": PROMPT_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    prompt = _build_flow_prompt(root_function, root_code, flow_steps, tree)
    try:
        response = call_llm(prompt).strip()
    except Exception as exc:  # pragma: no cover - defensive API guard
        response = ""
        error = normalize_whitespace(exc)
    else:
        error = ""

    cleaned = re.sub(r"\n{3,}", "\n\n", response).strip()
    model = normalize_whitespace(os.getenv("OPENAI_MODEL", "gpt-5-nano"))

    if not cleaned:
        return {
            "status": "error",
            "summary": "",
            "error": error or "LLM returned no explanation.",
            "request_fingerprint": request_fingerprint,
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "status": "ready",
        "summary": cleaned,
        "error": "",
        "request_fingerprint": request_fingerprint,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_flow_prompt(
    root_function: str,
    root_code: str,
    flow_steps: Sequence[Dict[str, Any]],
    tree: Dict[str, Any],
) -> str:
    step_text = prompt_flow_steps(flow_steps)
    tree_text = "\n".join(flatten_tree(tree))
    code_text = clip_text(root_code, 8000)
    return f"""Explain this execution flow in concise numbered steps.
Focus on the dominant path and keep the explanation readable.
Mention collapsed helper clusters only when they matter to the story.
Return only the explanation.

Root function:
{root_function}

Flow steps:
{step_text}

Compact tree:
{tree_text}

Root function code:
{code_text}
"""
