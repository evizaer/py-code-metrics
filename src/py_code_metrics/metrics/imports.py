"""Import graph and strongly connected components (cycles)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class ImportGraph:
    """Directed graph of module → imported modules (corpus-local only)."""

    edges: dict[str, set[str]] = field(default_factory=dict)
    scc_of: dict[str, int] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)
    _importers: dict[str, set[str]] = field(default_factory=dict, repr=False)

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self.edges.values())

    def efferent(self, mod: str) -> int:
        """Ce — distinct modules this one imports."""
        return len(self.edges.get(mod, ()))

    def afferent(self, mod: str) -> int:
        """Ca — distinct modules that import this one."""
        return len(self._importers.get(mod, ()))

    def rebuild_importers(self) -> None:
        importers: dict[str, set[str]] = {m: set() for m in self.edges}
        for src, targets in self.edges.items():
            for tgt in targets:
                importers.setdefault(tgt, set()).add(src)
        self._importers = importers


def extract_import_names(tree: ast.AST) -> list[str]:
    """Return absolute-ish module names referenced by import statements."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        dots = "." * node.level
        if node.module:
            names.append(dots + node.module)
            continue
        if not node.level:
            continue
        for alias in node.names:
            names.append(dots if alias.name == "*" else dots + alias.name)
    return names


def resolve_relative_import(current_module: str, imported: str) -> str | None:
    """Resolve a possibly-relative import to a dotted module name."""
    if not imported.startswith("."):
        return imported
    level = 0
    while level < len(imported) and imported[level] == ".":
        level += 1
    remainder = imported[level:]
    parts = current_module.split(".")
    if level > len(parts):
        return None
    base = parts[: len(parts) - level]
    if remainder:
        return ".".join(base + remainder.split("."))
    return ".".join(base) if base else None


def _corpus_module(target: str, module_names: set[str]) -> str | None:
    """Map an import target to a corpus module name.

    Prefer exact / longest submodule matches. When analyzing a package root
    (e.g. ``src/py_code_metrics``), absolute imports like ``py_code_metrics.model``
    must resolve to ``model``, not collapse onto the package ``__init__``.
    """
    if target in module_names:
        return target
    parts = target.split(".")
    # Strip corpus package prefixes: prefix + remainder both in corpus → remainder.
    for i in range(1, len(parts)):
        prefix = ".".join(parts[:i])
        remainder = ".".join(parts[i:])
        if prefix in module_names and remainder in module_names:
            return remainder
    # Longest prefix still in the corpus (submodule or package).
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in module_names:
            return cand
    return None


def build_import_graph(
    module_names: set[str],
    imports_by_module: dict[str, list[str]],
) -> ImportGraph:
    graph = ImportGraph()
    for mod in module_names:
        graph.edges.setdefault(mod, set())

    for mod, raw_imports in imports_by_module.items():
        for raw in raw_imports:
            target = resolve_relative_import(mod, raw)
            if target is None:
                continue
            cand = _corpus_module(target, module_names)
            if cand is None or cand == mod:
                continue
            graph.edges.setdefault(mod, set()).add(cand)

    sccs = tarjan_scc(graph.edges)
    cycles: list[list[str]] = []
    for i, component in enumerate(sccs):
        for name in component:
            graph.scc_of[name] = i
        if len(component) > 1:
            cycles.append(sorted(component))
        elif len(component) == 1 and component[0] in graph.edges.get(component[0], set()):
            cycles.append([component[0]])
    graph.cycles = cycles
    graph.rebuild_importers()
    return graph


def tarjan_scc(edges: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan's algorithm for strongly connected components."""
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    result: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in edges.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] != indices[v]:
            return
        component: list[str] = []
        while True:
            w = stack.pop()
            on_stack.discard(w)
            component.append(w)
            if w == v:
                break
        result.append(component)

    nodes = set(edges) | {t for targets in edges.values() for t in targets}
    for node in sorted(nodes):
        if node not in indices:
            strongconnect(node)
    return result
