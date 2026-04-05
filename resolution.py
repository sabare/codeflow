from __future__ import annotations

import ast
from typing import Dict, List, Set, Tuple

from bindings import ScopeBindings
from constants import BUILTIN_NAMES
from utils import get_qualified_name, is_project_module, is_stdlib_module, iter_target_names


class Resolver:
    def __init__(
        self,
        definitions: Set[str],
        class_names: Set[str],
        class_methods: Dict[str, Set[str]],
        class_bases: Dict[str, List[str]],
        imports: Dict[str, str],
        project_roots: Set[str],
    ) -> None:
        self.definitions = definitions
        self.class_names = class_names
        self.class_methods = class_methods
        self.class_bases = class_bases
        self.imports = imports
        self.project_roots = project_roots

    def _class_candidates(self, class_name: str) -> List[str]:
        candidates = []
        for name in self.class_methods:
            if name == class_name or name.endswith(f".{class_name}"):
                candidates.append(name)
        return candidates or [class_name]

    def resolve_class_method(self, class_name: str, method_name: str, seen: Set[str] | None = None) -> str | None:
        seen = set() if seen is None else seen
        for candidate in self._class_candidates(class_name):
            if candidate in seen:
                continue
            seen.add(candidate)

            if method_name in self.class_methods.get(candidate, set()):
                return f"{candidate}.{method_name}"

            for base in self.class_bases.get(candidate, []):
                resolved = self.resolve_class_method(base, method_name, seen)
                if resolved:
                    return resolved
        return None

    def _resolve_import(self, name: str) -> Tuple[str, str] | None:
        imported = self.imports.get(name)
        if not imported:
            return None
        if is_project_module(imported, self.project_roots):
            return "project", imported
        if is_stdlib_module(imported):
            return "stdlib", imported
        return "external", imported

    def _resolve_name_reference(
        self,
        name: str,
        bindings: ScopeBindings,
        scope: List[str],
    ) -> Set[Tuple[str, str]]:
        if name in bindings.callables:
            return set(bindings.callables[name])

        qualified_name = get_qualified_name(scope, name)
        if qualified_name in self.definitions:
            return {("project", qualified_name)}
        if name in self.definitions:
            return {("project", name)}
        if qualified_name in self.class_names:
            return {("project", qualified_name)}
        if name in self.class_names:
            return {("project", name)}

        imported = self._resolve_import(name)
        if imported:
            return {imported}
        if name in BUILTIN_NAMES:
            return {("builtin", name)}
        return {("external", name)}

    def _resolve_attribute_reference(
        self,
        node: ast.Attribute,
        bindings: ScopeBindings,
        scope: List[str],
        class_scope: List[str],
    ) -> Set[Tuple[str, str]]:
        owner = node.value
        attr = node.attr
        resolved: Set[Tuple[str, str]] = set()

        if isinstance(owner, ast.Name):
            owner_name = owner.id

            if owner_name in bindings.instances:
                for class_name in bindings.instances[owner_name]:
                    method_name = self.resolve_class_method(class_name, attr)
                    if method_name:
                        resolved.add(("project", method_name))
                if resolved:
                    return resolved

            if owner_name in {"self", "cls"} and class_scope:
                method_name = self.resolve_class_method(class_scope[-1], attr)
                if method_name:
                    return {("project", method_name)}

            if owner_name in self.class_names:
                method_name = self.resolve_class_method(owner_name, attr)
                if method_name:
                    return {("project", method_name)}

            imported = self.imports.get(owner_name)
            if imported:
                qualified = f"{imported}.{attr}"
                if is_project_module(imported, self.project_roots):
                    return {("project", qualified)}
                if is_stdlib_module(imported):
                    return {("stdlib", qualified)}
                return {("external", qualified)}

        return resolved

    def _resolve_getattr(
        self,
        node: ast.Call,
        bindings: ScopeBindings,
        scope: List[str],
        class_scope: List[str],
    ) -> Set[Tuple[str, str]]:
        if len(node.args) < 2:
            return set()

        attr_node = node.args[1]
        if not isinstance(attr_node, ast.Constant) or not isinstance(attr_node.value, str):
            return set()

        method_name = attr_node.value
        owner_types = self.infer_instance_types(node.args[0], bindings, scope, class_scope)
        resolved: Set[Tuple[str, str]] = set()

        for class_name in owner_types:
            target = self.resolve_class_method(class_name, method_name)
            if target:
                resolved.add(("project", target))
        if resolved:
            return resolved

        if isinstance(node.args[0], ast.Name):
            owner_name = node.args[0].id
            imported = self.imports.get(owner_name)
            if imported:
                qualified = f"{imported}.{method_name}"
                if is_project_module(imported, self.project_roots):
                    return {("project", qualified)}
                if is_stdlib_module(imported):
                    return {("stdlib", qualified)}
                return {("external", qualified)}

        return set()

    def resolve_callable_references(
        self,
        node: ast.AST,
        bindings: ScopeBindings,
        scope: List[str],
        class_scope: List[str],
    ) -> Set[Tuple[str, str]]:
        if isinstance(node, ast.Name):
            return self._resolve_name_reference(node.id, bindings, scope)

        if isinstance(node, ast.Attribute):
            return self._resolve_attribute_reference(node, bindings, scope, class_scope)

        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                return set(bindings.dict_targets.get(node.value.id, set()))
            return set()

        if isinstance(node, ast.Call):
            if self.is_getattr_call(node):
                return self._resolve_getattr(node, bindings, scope, class_scope)
            return self.resolve_callable_references(node.func, bindings, scope, class_scope)

        return set()

    def infer_instance_types(
        self,
        node: ast.AST,
        bindings: ScopeBindings,
        scope: List[str],
        class_scope: List[str],
    ) -> Set[str]:
        if isinstance(node, ast.Name) and node.id in bindings.instances:
            return set(bindings.instances[node.id])

        if isinstance(node, ast.Call):
            if self.is_getattr_call(node):
                return set()
            targets = self.resolve_callable_references(node.func, bindings, scope, class_scope)
            if targets and all(category == "project" and self._is_class_target(name) for category, name in targets):
                return {name for _, name in targets}

        if isinstance(node, ast.Name):
            qualified_name = get_qualified_name(scope, node.id)
            if qualified_name in self.class_names:
                return {qualified_name}
            if node.id in self.class_names:
                return {node.id}

        return set()

    def infer_value(
        self,
        node: ast.AST,
        bindings: ScopeBindings,
        scope: List[str],
        class_scope: List[str],
    ) -> Tuple[Set[Tuple[str, str]], Set[str], Set[Tuple[str, str]]]:
        if isinstance(node, ast.Lambda):
            return set(), set(), set()

        if isinstance(node, ast.Dict):
            callables: Set[Tuple[str, str]] = set()
            for value in node.values:
                callables.update(self.resolve_callable_references(value, bindings, scope, class_scope))
            return callables, set(), set()

        if isinstance(node, ast.Tuple):
            callables: Set[Tuple[str, str]] = set()
            instances: Set[str] = set()
            dict_targets: Set[Tuple[str, str]] = set()
            for value in node.elts:
                sub_callables, sub_instances, sub_dict_targets = self.infer_value(value, bindings, scope, class_scope)
                callables.update(sub_callables)
                instances.update(sub_instances)
                dict_targets.update(sub_dict_targets)
            return callables, instances, dict_targets

        if isinstance(node, ast.List):
            callables: Set[Tuple[str, str]] = set()
            instances: Set[str] = set()
            dict_targets: Set[Tuple[str, str]] = set()
            for value in node.elts:
                sub_callables, sub_instances, sub_dict_targets = self.infer_value(value, bindings, scope, class_scope)
                callables.update(sub_callables)
                instances.update(sub_instances)
                dict_targets.update(sub_dict_targets)
            return callables, instances, dict_targets

        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                return set(), set(), set(bindings.dict_targets.get(node.value.id, set()))
            return set(), set(), set()

        if isinstance(node, ast.Name):
            if node.id in bindings.callables:
                return set(bindings.callables[node.id]), set(), set()
            if node.id in bindings.instances:
                return set(), set(bindings.instances[node.id]), set()
            if node.id in bindings.dict_targets:
                return set(), set(), set(bindings.dict_targets[node.id])
            return self._resolve_name_reference(node.id, bindings, scope), set(), set()

        if isinstance(node, ast.Attribute):
            return self.resolve_callable_references(node, bindings, scope, class_scope), set(), set()

        if isinstance(node, ast.Call):
            if self.is_getattr_call(node):
                return self._resolve_getattr(node, bindings, scope, class_scope), set(), set()

            targets = self.resolve_callable_references(node.func, bindings, scope, class_scope)
            if targets and all(category == "project" and self._is_class_target(name) for category, name in targets):
                return set(), {name for _, name in targets}, set()
            return targets, set(), set()

        return set(), set(), set()

    def is_getattr_call(self, node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "getattr"

    def _is_class_target(self, name: str) -> bool:
        return name in self.class_names or any(name.endswith(f".{candidate}") for candidate in self.class_names)


def bind_assignment(
    targets: List[ast.AST],
    value: ast.AST,
    bindings: ScopeBindings,
    resolver: Resolver,
    scope: List[str],
    class_scope: List[str],
    lambda_functions: Set[str],
) -> None:
    target_names = [name for target in targets for name in iter_target_names(target)]
    if not target_names:
        return

    if isinstance(value, ast.Lambda):
        for target_name in target_names:
            lambda_name = get_qualified_name(scope, target_name)
            lambda_functions.add(lambda_name)
            bindings.bind_callables(target_name, {("project", lambda_name)})
        return

    callables, instances, dict_targets = resolver.infer_value(value, bindings, scope, class_scope)
    for target_name in target_names:
        bindings.bind_callables(target_name, callables)
        bindings.bind_instances(target_name, instances)
        bindings.bind_dict_targets(target_name, dict_targets)
