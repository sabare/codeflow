from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

from bindings import ScopeBindings
from definitions import DefinitionCollector, ImportCollector
from resolution import Resolver, bind_assignment
from utils import iter_python_files, module_name_for, get_qualified_name


class CallGraphCollector(ast.NodeVisitor):
    def __init__(
        self,
        definitions: Set[str],
        class_names: Set[str],
        class_methods: Dict[str, Set[str]],
        class_bases: Dict[str, List[str]],
        imports: Dict[str, str],
        project_roots: Set[str],
        module_bindings: ScopeBindings,
    ) -> None:
        self.resolver = Resolver(definitions, class_names, class_methods, class_bases, imports, project_roots)
        self.bindings_stack: List[ScopeBindings] = [module_bindings.clone()]
        self.project_calls: Dict[str, Set[str]] = {}
        self.stdlib_calls: Dict[str, Set[str]] = {}
        self.external_calls: Dict[str, Set[str]] = {}
        self.builtin_calls: Dict[str, Set[str]] = {}
        self.decorator_calls: Dict[str, Set[str]] = {}
        self.lambda_functions: Set[str] = set()
        self.scope: List[str] = []
        self.class_scope: List[str] = []
        self.current_function: str | None = None

    @property
    def bindings(self) -> ScopeBindings:
        return self.bindings_stack[-1]

    def _push_function_scope(self) -> None:
        self.bindings_stack.append(self.bindings.clone())

    def _pop_function_scope(self) -> None:
        self.bindings_stack.pop()

    def _record_callable(self, category: str, name: str) -> None:
        if category == "project":
            self.project_calls.setdefault(self.current_function or "", set()).add(name)
        elif category == "stdlib":
            self.stdlib_calls.setdefault(self.current_function or "", set()).add(name)
        elif category == "external":
            self.external_calls.setdefault(self.current_function or "", set()).add(name)
        elif category == "builtin":
            self.builtin_calls.setdefault(self.current_function or "", set()).add(name)

    def _start_function(self, node: ast.AST, body: List[ast.stmt]) -> None:
        qualified_name = get_qualified_name(self.scope, node.name)
        self.project_calls.setdefault(qualified_name, set())
        self.stdlib_calls.setdefault(qualified_name, set())
        self.external_calls.setdefault(qualified_name, set())
        self.builtin_calls.setdefault(qualified_name, set())
        self.decorator_calls.setdefault(qualified_name, set())

        previous_function = self.current_function
        self.current_function = qualified_name

        for decorator in node.decorator_list:
            for category, name in self.resolver.resolve_callable_references(
                decorator,
                self.bindings,
                self.scope,
                self.class_scope,
            ):
                self.decorator_calls[qualified_name].add(name)
                if self.current_function is not None:
                    self._record_callable(category, name)

        self._push_function_scope()
        self.scope.append(node.name)
        for stmt in body:
            self.visit(stmt)
        self.scope.pop()
        self._pop_function_scope()
        self.current_function = previous_function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._start_function(node, node.body)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._start_function(node, node.body)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = get_qualified_name(self.scope, node.name)
        self.decorator_calls.setdefault(qualified_name, set())

        previous_function = self.current_function
        for decorator in node.decorator_list:
            for category, name in self.resolver.resolve_callable_references(
                decorator,
                self.bindings,
                self.scope,
                self.class_scope,
            ):
                self.decorator_calls[qualified_name].add(name)
                if self.current_function is not None:
                    self._record_callable(category, name)

        self.class_scope.append(qualified_name)
        self.scope.append(node.name)
        self.current_function = None
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()
        self.class_scope.pop()
        self.current_function = previous_function

    def visit_Assign(self, node: ast.Assign) -> None:
        if self.current_function:
            self.visit(node.value)
            bind_assignment(
                node.targets,
                node.value,
                self.bindings,
                self.resolver,
                self.scope,
                self.class_scope,
                self.lambda_functions,
            )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self.current_function and node.value is not None:
            self.visit(node.value)
            bind_assignment(
                [node.target],
                node.value,
                self.bindings,
                self.resolver,
                self.scope,
                self.class_scope,
                self.lambda_functions,
            )

    def visit_Call(self, node: ast.Call) -> None:
        if not self.current_function:
            self.generic_visit(node)
            return

        for category, name in self.resolver.resolve_callable_references(
            node.func,
            self.bindings,
            self.scope,
            self.class_scope,
        ):
            self._record_callable(category, name)

        self.generic_visit(node)


def collect_module_bindings(tree: ast.AST, resolver: Resolver, lambda_functions: Set[str]) -> ScopeBindings:
    bindings = ScopeBindings()
    for stmt in getattr(tree, "body", []):
        if isinstance(stmt, ast.Assign):
            bind_assignment(stmt.targets, stmt.value, bindings, resolver, [], [], lambda_functions)
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            bind_assignment([stmt.target], stmt.value, bindings, resolver, [], [], lambda_functions)
    return bindings


def build_analysis(root: Path) -> Dict[str, object]:
    definitions: Set[str] = set()
    class_names: Set[str] = set()
    class_methods: Dict[str, Set[str]] = {}
    class_bases: Dict[str, List[str]] = {}
    lambda_functions: Set[str] = set()
    project_roots: Set[str] = set()
    trees: List[Tuple[ast.AST, Dict[str, str], ScopeBindings]] = []
    function_sources: Dict[str, str] = {}

    for file_path in iter_python_files(root):
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (OSError, SyntaxError):
            continue

        definition_collector = DefinitionCollector(source)
        definition_collector.visit(tree)
        definitions.update(definition_collector.function_names)
        class_names.update(definition_collector.class_names)
        for class_name, methods in definition_collector.class_methods.items():
            class_methods.setdefault(class_name, set()).update(methods)
        for class_name, bases in definition_collector.class_bases.items():
            class_bases[class_name] = list(bases)
        function_sources.update(definition_collector.function_sources)

        import_collector = ImportCollector()
        import_collector.visit(tree)

        project_roots.add(module_name_for(root, file_path).split(".", 1)[0])
        resolver = Resolver(definitions, class_names, class_methods, class_bases, import_collector.imports, project_roots)
        module_bindings = collect_module_bindings(tree, resolver, lambda_functions)
        trees.append((tree, import_collector.imports, module_bindings))

    project_graph: Dict[str, Set[str]] = {name: set() for name in definitions}
    stdlib_calls: Dict[str, Set[str]] = {name: set() for name in definitions}
    external_calls: Dict[str, Set[str]] = {name: set() for name in definitions}
    builtin_calls: Dict[str, Set[str]] = {name: set() for name in definitions}
    decorator_calls: Dict[str, Set[str]] = {name: set() for name in definitions}

    for tree, imports, module_bindings in trees:
        collector = CallGraphCollector(
            definitions,
            class_names,
            class_methods,
            class_bases,
            imports,
            project_roots,
            module_bindings,
        )
        collector.visit(tree)

        for func_name, calls in collector.project_calls.items():
            project_graph.setdefault(func_name, set()).update(calls)
        for func_name, calls in collector.stdlib_calls.items():
            stdlib_calls.setdefault(func_name, set()).update(calls)
        for func_name, calls in collector.external_calls.items():
            external_calls.setdefault(func_name, set()).update(calls)
        for func_name, calls in collector.builtin_calls.items():
            builtin_calls.setdefault(func_name, set()).update(calls)
        for func_name, calls in collector.decorator_calls.items():
            decorator_calls.setdefault(func_name, set()).update(calls)
        lambda_functions.update(collector.lambda_functions)

    for lambda_name in lambda_functions:
        project_graph.setdefault(lambda_name, set())

    return {
        "project_graph": {name: sorted(calls) for name, calls in sorted(project_graph.items())},
        "stdlib_calls": {name: sorted(calls) for name, calls in sorted(stdlib_calls.items())},
        "external_calls": {name: sorted(calls) for name, calls in sorted(external_calls.items())},
        "builtin_calls": {name: sorted(calls) for name, calls in sorted(builtin_calls.items())},
        "decorator_calls": {name: sorted(calls) for name, calls in sorted(decorator_calls.items())},
        "definitions": {
            "functions": sorted(definitions),
            "classes": sorted(class_names),
        },
        "lambdas": sorted(lambda_functions),
        "sources": function_sources,
    }


def build_call_graph(root: Path) -> Dict[str, List[str]]:
    return build_analysis(root)["project_graph"]


def build_call_map(root: Path) -> Dict[str, List[str]]:
    return build_call_graph(root)
