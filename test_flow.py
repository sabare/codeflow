from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import flow
from backend.analyzer import _build_tree


def _sample_analysis(project_graph: dict[str, list[str]], sources: dict[str, str]) -> dict[str, object]:
    keys = sorted(project_graph.keys())
    return {
        "project_graph": project_graph,
        "stdlib_calls": {name: [] for name in keys},
        "external_calls": {name: [] for name in keys},
        "builtin_calls": {name: [] for name in keys},
        "decorator_calls": {name: [] for name in keys},
        "sources": sources,
    }


def _sample_project_analysis(project_graph: dict[str, list[str]], sources: dict[str, str]) -> dict[str, object]:
    names = sorted(project_graph.keys())
    return {
        "project_graph": project_graph,
        "sources": sources,
        "definitions": {
            "functions": names,
            "classes": [],
        },
    }


def _walk_nodes(node: dict[str, object]) -> list[dict[str, object]]:
    nodes = [node]
    for child in node.get("children", []) or []:
        if isinstance(child, dict):
            nodes.extend(_walk_nodes(child))
    return nodes


class FlowAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.cache_path = Path(self.tempdir.name) / "flow_explanations.json"
        self.cache_patcher = mock.patch.object(flow, "CACHE_PATH", self.cache_path)
        self.cache_patcher.start()
        self.addCleanup(self.cache_patcher.stop)
        flow._PENDING_EXPLANATIONS.clear()
        self.addCleanup(flow._PENDING_EXPLANATIONS.clear)

    def _login_analysis(self) -> dict[str, object]:
        project_graph = {
            "login": ["validate", "query_user", "render"],
            "validate": ["get_user_id"],
            "get_user_id": [],
            "query_user": [],
            "render": [],
        }
        sources = {
            "login": "def login(request):\n    return validate(request)",
            "validate": "def validate(request):\n    return request.user",
            "get_user_id": "def get_user_id(user):\n    return user.id",
            "query_user": "def query_user(user_id):\n    return user_id",
            "render": "def render(user):\n    return user",
        }
        return _sample_analysis(project_graph, sources)

    def _recursive_analysis(self) -> dict[str, object]:
        project_graph = {
            "root": ["helper"],
            "helper": ["root"],
        }
        sources = {
            "root": "def root():\n    return helper()",
            "helper": "def helper():\n    return root()",
        }
        return _sample_analysis(project_graph, sources)

    def test_fast_pass_returns_deterministic_flow_without_llm(self) -> None:
        analysis = self._login_analysis()

        with mock.patch.object(flow, "call_llm") as llm_mock:
            result = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=False,
                wait_for_explanation=False,
            )

        self.assertFalse(llm_mock.called)
        self.assertEqual(result["flow_explanation_status"], "unavailable")
        self.assertTrue(result["flow_fingerprint"])
        self.assertGreaterEqual(len(result["flow_steps"]), 2)
        self.assertTrue(str(result["flow_steps"][0]["summary"]).startswith("Start at"))

    def test_async_pass_schedules_background_job_and_reports_pending(self) -> None:
        analysis = self._login_analysis()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}, clear=False):
            with mock.patch.object(flow, "_schedule_flow_explanation") as schedule_mock:
                result = flow.build_flow_tree(
                    analysis,
                    "login",
                    async_enrichment=True,
                    wait_for_explanation=False,
                )

        self.assertEqual(result["flow_explanation_status"], "pending")
        self.assertTrue(result["flow_fingerprint"])
        schedule_mock.assert_called_once()

    def test_cached_explanation_is_returned_when_ready(self) -> None:
        analysis = self._login_analysis()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}, clear=False):
            baseline = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=False,
                wait_for_explanation=False,
            )
            explanation_key = flow._explanation_cache_key(baseline["flow_fingerprint"])

            with mock.patch.object(flow, "call_llm", return_value="1. Login.\n2. Validate.\n3. Query user.\n4. Render.\n"):
                entry = flow._generate_and_store_explanation(
                    explanation_key=explanation_key,
                    request_fingerprint=baseline["flow_fingerprint"],
                    root_function="login",
                    root_code=str(analysis["sources"]["login"]),
                    tree=baseline["tree"],
                    flow_steps=baseline["flow_steps"],
                )

            self.assertEqual(entry["status"], "ready")

            ready = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=True,
                wait_for_explanation=False,
            )

        self.assertEqual(ready["flow_explanation_status"], "ready")
        self.assertIn("Login", ready["flow_summary"])

    def test_cache_invalidation_changes_fingerprint_and_skips_ready_cache(self) -> None:
        analysis = self._login_analysis()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}, clear=False):
            baseline = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=False,
                wait_for_explanation=False,
            )
            explanation_key = flow._explanation_cache_key(baseline["flow_fingerprint"])

            with mock.patch.object(flow, "call_llm", return_value="1. Login.\n2. Validate.\n3. Query user.\n4. Render.\n"):
                flow._generate_and_store_explanation(
                    explanation_key=explanation_key,
                    request_fingerprint=baseline["flow_fingerprint"],
                    root_function="login",
                    root_code=str(analysis["sources"]["login"]),
                    tree=baseline["tree"],
                    flow_steps=baseline["flow_steps"],
                )

            with mock.patch.object(flow, "_schedule_flow_explanation") as schedule_mock:
                changed = flow.build_flow_tree(
                    analysis,
                    "login",
                    include_builtin=False,
                    async_enrichment=True,
                    wait_for_explanation=False,
                )

        self.assertNotEqual(baseline["flow_fingerprint"], changed["flow_fingerprint"])
        self.assertEqual(changed["flow_explanation_status"], "pending")
        schedule_mock.assert_called_once()

    def test_error_state_is_reported_when_llm_fails(self) -> None:
        analysis = self._login_analysis()

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key", "OPENAI_MODEL": "test-model"}, clear=False):
            baseline = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=False,
                wait_for_explanation=False,
            )
            explanation_key = flow._explanation_cache_key(baseline["flow_fingerprint"])

            with mock.patch.object(flow, "call_llm", side_effect=RuntimeError("boom")):
                entry = flow._generate_and_store_explanation(
                    explanation_key=explanation_key,
                    request_fingerprint=baseline["flow_fingerprint"],
                    root_function="login",
                    root_code=str(analysis["sources"]["login"]),
                    tree=baseline["tree"],
                    flow_steps=baseline["flow_steps"],
                )

            self.assertEqual(entry["status"], "error")

            failed = flow.build_flow_tree(
                analysis,
                "login",
                async_enrichment=True,
                wait_for_explanation=False,
            )

        self.assertEqual(failed["flow_explanation_status"], "error")
        self.assertIn("boom", failed["flow_explanation_error"])

    def test_helper_clusters_are_created_in_flow_tree(self) -> None:
        analysis = self._login_analysis()
        result = flow.build_flow_tree(
            analysis,
            "login",
            async_enrichment=False,
            wait_for_explanation=False,
        )

        nodes = _walk_nodes(result["tree"])
        clusters = [node for node in nodes if node.get("kind") == "cluster" or int(node.get("collapsed_count", 0) or 0) > 0]
        self.assertTrue(clusters)
        self.assertTrue(any("helper" in str(node.get("collapse_reason", "")).lower() or int(node.get("collapsed_count", 0) or 0) > 0 for node in clusters))

    def test_recursive_and_depth_limited_flows_remain_sensible(self) -> None:
        analysis = self._recursive_analysis()

        recursive = flow.build_flow_tree(
            analysis,
            "root",
            max_depth=3,
            async_enrichment=False,
            wait_for_explanation=False,
        )
        recursive_nodes = _walk_nodes(recursive["tree"])
        self.assertTrue(any(bool(node.get("recursive")) for node in recursive_nodes))

        truncated = flow.build_flow_tree(
            analysis,
            "root",
            max_depth=1,
            async_enrichment=False,
            wait_for_explanation=False,
        )
        truncated_nodes = _walk_nodes(truncated["tree"])
        self.assertTrue(any(bool(node.get("truncated")) for node in truncated_nodes))

    def test_flow_response_contains_deduplicated_dag(self) -> None:
        project_graph = {
            "root": ["prepare", "execute"],
            "prepare": ["shared_helper"],
            "execute": ["shared_helper"],
            "shared_helper": [],
        }
        sources = {
            "root": "def root():\n    return execute()",
            "prepare": "def prepare():\n    return shared_helper()",
            "execute": "def execute():\n    return shared_helper()",
            "shared_helper": "def shared_helper():\n    return 1",
        }
        analysis = _sample_analysis(project_graph, sources)

        result = flow.build_flow_tree(
            analysis,
            "root",
            async_enrichment=False,
            wait_for_explanation=False,
        )

        graph = result.get("graph", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        node_ids = {str(node.get("id", "")) for node in nodes}
        edge_pairs = {(str(edge.get("source", "")), str(edge.get("target", ""))) for edge in edges}

        self.assertEqual(node_ids, {"root", "prepare", "execute", "shared_helper"})
        self.assertEqual(
            edge_pairs,
            {
                ("root", "prepare"),
                ("root", "execute"),
                ("prepare", "shared_helper"),
                ("execute", "shared_helper"),
            },
        )

    def test_project_overview_tree_compacts_helpers(self) -> None:
        project_graph = {
            "login": ["validate", "query_user"],
            "validate": ["get_user_id"],
            "get_user_id": [],
            "query_user": [],
        }
        sources = {
            "login": "def login(request):\n    return validate(request)",
            "validate": "def validate(request):\n    return request.user",
            "get_user_id": "def get_user_id(user):\n    return user.id",
            "query_user": "def query_user(user_id):\n    return user_id",
        }

        tree = _build_tree(Path("/tmp/project"), _sample_project_analysis(project_graph, sources))
        nodes = _walk_nodes(tree)

        self.assertEqual(tree["kind"], "root")
        self.assertTrue(any(node.get("kind") == "cluster" or int(node.get("collapsed_count", 0) or 0) > 0 for node in nodes))


if __name__ == "__main__":
    unittest.main()
