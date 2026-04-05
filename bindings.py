from __future__ import annotations

from typing import Dict, Set, Tuple


class ScopeBindings:
    def __init__(self) -> None:
        self.callables: Dict[str, Set[Tuple[str, str]]] = {}
        self.instances: Dict[str, Set[str]] = {}
        self.dict_targets: Dict[str, Set[Tuple[str, str]]] = {}

    def clone(self) -> "ScopeBindings":
        cloned = ScopeBindings()
        cloned.callables = {name: set(values) for name, values in self.callables.items()}
        cloned.instances = {name: set(values) for name, values in self.instances.items()}
        cloned.dict_targets = {name: set(values) for name, values in self.dict_targets.items()}
        return cloned

    def bind_callables(self, name: str, targets: Set[Tuple[str, str]]) -> None:
        if targets:
            self.callables.setdefault(name, set()).update(targets)

    def bind_instances(self, name: str, types: Set[str]) -> None:
        if types:
            self.instances.setdefault(name, set()).update(types)

    def bind_dict_targets(self, name: str, targets: Set[Tuple[str, str]]) -> None:
        if targets:
            self.dict_targets.setdefault(name, set()).update(targets)
