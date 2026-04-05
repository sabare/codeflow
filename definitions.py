from __future__ import annotations

import ast
from typing import Dict, List, Set

from utils import get_dotted_name, get_qualified_name


class DefinitionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_names: Set[str] = set()
        self.class_names: Set[str] = set()
        self.class_methods: Dict[str, Set[str]] = {}
        self.class_bases: Dict[str, List[str]] = {}
        self.decorators: Dict[str, List[str]] = {}
        self.scope: List[str] = []
        self.class_stack: List[str] = []
        self.function_depth = 0

    def _record_function(self, node: ast.AST) -> None:
        qualified_name = get_qualified_name(self.scope, node.name)
        self.function_names.add(qualified_name)

        if self.class_stack and self.function_depth == 0:
            self.class_methods.setdefault(self.class_stack[-1], set()).add(node.name)

        self.decorators[qualified_name] = [
            name
            for decorator in node.decorator_list
            if (name := get_dotted_name(decorator))
        ]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node)
        self.function_depth += 1
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()
        self.function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node)
        self.function_depth += 1
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()
        self.function_depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = get_qualified_name(self.scope, node.name)
        self.class_names.add(qualified_name)
        self.class_methods.setdefault(qualified_name, set())
        self.class_bases[qualified_name] = [
            base_name
            for base in node.bases
            if (base_name := get_dotted_name(base))
        ]
        self.class_stack.append(qualified_name)
        self.scope.append(node.name)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()
        self.class_stack.pop()


class ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: Dict[str, str] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local_name = alias.asname or alias.name.split(".", 1)[0]
            self.imports[local_name] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            local_name = alias.asname or alias.name
            self.imports[local_name] = f"{node.module}.{alias.name}"
