"""Symbol indexing and best-effort static call / import resolution."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from py_code_metrics.metrics.call_graph import CallGraph, CallSite, collect_calls_in_function
from py_code_metrics.metrics.imports import extract_import_names
from py_code_metrics.parse import ParsedFile


@dataclass
class CallableInfo:
    qname: str
    name: str
    module: str
    kind: str  # function | method | classmethod | staticmethod | nested_function
    node: ast.FunctionDef | ast.AsyncFunctionDef
    class_qname: str | None = None
    parent_qname: str | None = None
    is_public: bool = True
    lineno: int = 0


@dataclass
class ClassInfo:
    qname: str
    name: str
    module: str
    node: ast.ClassDef
    bases_raw: list[str] = field(default_factory=list)
    bases_resolved: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    name: str
    path: Path
    tree: ast.Module
    source: str
    source_lines: list[str]
    imports_raw: list[str] = field(default_factory=list)
    local_names: dict[str, str] = field(default_factory=dict)


@dataclass
class SymbolIndex:
    root: Path
    modules: dict[str, ModuleInfo] = field(default_factory=dict)
    callables: dict[str, CallableInfo] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    imports_by_module: dict[str, list[str]] = field(default_factory=dict)


def _module_name_for_path(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.stem

    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        if path.name == "__init__.py":
            return root.name
        return path.stem
    return ".".join(parts)


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.add(dec.attr)
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                names.add(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                names.add(dec.func.attr)
    return names


def _method_kind(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    decs = _decorator_names(node)
    if "staticmethod" in decs:
        return "staticmethod"
    if "classmethod" in decs:
        return "classmethod"
    return "method"


def _is_public_name(name: str) -> bool:
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def _record_import_aliases(mi: ModuleInfo, tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                mi.local_names[local] = alias.name
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            local = alias.asname or alias.name
            mi.local_names[local] = f"{module}.{alias.name}" if module else alias.name


def build_symbol_index(parsed: list[ParsedFile], root: Path) -> SymbolIndex:
    index = SymbolIndex(root=root.resolve())

    for pf in parsed:
        mod_name = _module_name_for_path(pf.path, root)
        if mod_name in index.modules:
            mod_name = _module_name_for_path(pf.path, pf.path.parent)

        mi = ModuleInfo(
            name=mod_name,
            path=pf.path,
            tree=pf.tree,
            source=pf.source,
            source_lines=pf.source.splitlines(),
            imports_raw=extract_import_names(pf.tree),
        )
        index.modules[mod_name] = mi
        index.imports_by_module[mod_name] = mi.imports_raw
        _record_import_aliases(mi, pf.tree)
        _index_module_body(index, mi, pf.tree.body, parent_qname=None)

    _resolve_bases(index)
    return index


def _base_expr_name(base: ast.expr) -> str | None:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return ast.unparse(base)
    return None


def _index_module_body(
    index: SymbolIndex,
    mi: ModuleInfo,
    body: list[ast.stmt],
    parent_qname: str | None,
    class_qname: str | None = None,
) -> None:
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            cq = f"{class_qname}.{stmt.name}" if class_qname else f"{mi.name}.{stmt.name}"
            bases_raw = [n for b in stmt.bases if (n := _base_expr_name(b)) is not None]
            ci = ClassInfo(
                qname=cq,
                name=stmt.name,
                module=mi.name,
                node=stmt,
                bases_raw=bases_raw,
            )
            index.classes[cq] = ci
            mi.local_names[stmt.name] = cq
            _index_module_body(index, mi, stmt.body, parent_qname=cq, class_qname=cq)
            continue

        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if class_qname:
            kind = _method_kind(stmt)
            qname = f"{class_qname}.{stmt.name}"
        elif parent_qname and parent_qname in index.callables:
            kind = "nested_function"
            qname = f"{parent_qname}.{stmt.name}"
        else:
            kind = "function"
            qname = f"{mi.name}.{stmt.name}"

        info = CallableInfo(
            qname=qname,
            name=stmt.name,
            module=mi.name,
            kind=kind,
            node=stmt,
            class_qname=class_qname,
            parent_qname=parent_qname,
            is_public=_is_public_name(stmt.name),
            lineno=stmt.lineno,
        )
        index.callables[qname] = info
        if class_qname is None and parent_qname is None:
            mi.local_names[stmt.name] = qname
        _index_nested(index, mi, stmt, qname, class_qname)


def _index_nested(
    index: SymbolIndex,
    mi: ModuleInfo,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_qname: str,
    class_qname: str | None,
) -> None:
    for stmt in func.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        qname = f"{parent_qname}.{stmt.name}"
        info = CallableInfo(
            qname=qname,
            name=stmt.name,
            module=mi.name,
            kind="nested_function",
            node=stmt,
            class_qname=class_qname,
            parent_qname=parent_qname,
            is_public=False,
            lineno=stmt.lineno,
        )
        index.callables[qname] = info
        _index_nested(index, mi, stmt, qname, class_qname)


def _find_class_by_suffix(
    index: SymbolIndex, raw: str, prefer_module: str | None = None
) -> str | None:
    """Resolve a bare class name to a corpus class qname."""
    if prefer_module:
        for cq in index.classes:
            if cq.split(".")[-1] == raw and cq.startswith(prefer_module + "."):
                return cq
    for cq in index.classes:
        if cq == raw or cq.endswith("." + raw):
            return cq
    short = raw.split(".")[-1]
    for cq in index.classes:
        if cq.split(".")[-1] == short:
            return cq
    return None


def _resolve_bases(index: SymbolIndex) -> None:
    for ci in index.classes.values():
        resolved: list[str] = []
        mi = index.modules[ci.module]
        for raw in ci.bases_raw:
            if raw in mi.local_names:
                target = mi.local_names[raw]
                if target in index.classes:
                    resolved.append(target)
                    continue
                found = _find_class_by_suffix(index, raw)
                if found:
                    resolved.append(found)
                continue
            found = _find_class_by_suffix(index, raw, prefer_module=ci.module)
            if found:
                resolved.append(found)
        ci.bases_resolved = resolved


def build_call_graph(index: SymbolIndex) -> CallGraph:
    graph = CallGraph()
    for qname, info in index.callables.items():
        mi = index.modules[info.module]
        for call in collect_calls_in_function(info.node):
            callee = resolve_call(index, mi, info, call)
            graph.sites.append(
                CallSite(
                    caller_qname=qname,
                    callee_qname=callee,
                    call=call,
                    module=info.module,
                )
            )
            if callee:
                graph.fan_in_sites[callee].append(qname)
    return graph


def _lookup_imported_callable(index: SymbolIndex, target: str, name: str) -> str | None:
    """Map an import target string to a callable qname when possible."""
    if target in index.callables:
        return target
    if target.endswith("." + name) and target in index.callables:
        return target
    for cq, ci in index.callables.items():
        if cq == target:
            return cq
        if ci.name != name:
            continue
        if target.endswith("." + name) or target == cq:
            return cq
        if target.endswith(ci.module) or target.startswith(ci.module):
            return cq
        if cq.startswith(target + "."):
            return cq
    return None


def resolve_call(
    index: SymbolIndex,
    mi: ModuleInfo,
    caller: CallableInfo,
    call: ast.Call,
) -> str | None:
    """Best-effort resolve a Call to a callable qualified name."""
    func = call.func

    if isinstance(func, ast.Name):
        name = func.id
        if name in mi.local_names:
            hit = _lookup_imported_callable(index, mi.local_names[name], name)
            if hit:
                return hit
        candidate = f"{mi.name}.{name}"
        return candidate if candidate in index.callables else None

    if not isinstance(func, ast.Attribute):
        return None

    attr = func.attr
    if isinstance(func.value, ast.Name):
        receiver = func.value.id
        if receiver in ("self", "cls") and caller.class_qname:
            candidate = f"{caller.class_qname}.{attr}"
            if candidate in index.callables:
                return candidate
            return _find_method_in_hierarchy(index, caller.class_qname, attr)
        if receiver in mi.local_names:
            target = mi.local_names[receiver]
            class_cand = f"{target}.{attr}"
            if target in index.classes and class_cand in index.callables:
                return class_cand
            if class_cand in index.callables:
                return class_cand
            hit = _lookup_imported_callable(index, target, attr)
            if hit:
                return hit

    try:
        unparsed = ast.unparse(func)
    except Exception:
        return None
    if unparsed in index.callables:
        return unparsed
    if isinstance(func.value, ast.Name):
        cand = f"{mi.local_names.get(func.value.id, func.value.id)}.{attr}"
        if cand in index.callables:
            return cand
    return None


def _find_method_in_hierarchy(index: SymbolIndex, class_qname: str, method: str) -> str | None:
    seen: set[str] = set()
    stack = [class_qname]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        cand = f"{cur}.{method}"
        if cand in index.callables:
            return cand
        ci = index.classes.get(cur)
        if ci:
            stack.extend(ci.bases_resolved)
    return None


def resolve_polymorphic_targets(
    index: SymbolIndex,
    caller: CallableInfo,
    call: ast.Call,
) -> list[tuple[str, str]]:
    """Return [(class_qname, method_name), ...] for polymorphic-looking calls."""
    func = call.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return []

    method = func.attr
    receiver = func.value.id

    if receiver in ("self", "cls"):
        if not caller.class_qname:
            return []
        found = _find_method_in_hierarchy(index, caller.class_qname, method)
        if not found:
            return []
        return [(found.rsplit(".", 1)[0], method)]

    ann_class = _annotation_class_for_param(index, caller, receiver)
    if ann_class:
        return [(ann_class, method)]

    mi = index.modules[caller.module]
    if receiver in mi.local_names:
        t = mi.local_names[receiver]
        if t in index.classes:
            return [(t, method)]
    return []


def _annotation_class_for_param(
    index: SymbolIndex,
    caller: CallableInfo,
    param_name: str,
) -> str | None:
    """If *param_name* is a parameter annotated with a known class, return its qname."""
    mi = index.modules[caller.module]
    args = (
        list(caller.node.args.posonlyargs)
        + list(caller.node.args.args)
        + list(caller.node.args.kwonlyargs)
    )
    for arg in args:
        if arg.arg != param_name:
            continue
        ann = arg.annotation
        name: str | None = None
        if isinstance(ann, ast.Name):
            name = ann.id
        elif isinstance(ann, ast.Attribute):
            try:
                name = ast.unparse(ann)
            except Exception:
                name = ann.attr
        elif isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            name = ann.value
        if not name:
            return None
        if name in mi.local_names and mi.local_names[name] in index.classes:
            return mi.local_names[name]
        candidate = f"{mi.name}.{name}"
        if candidate in index.classes:
            return candidate
        return _find_class_by_suffix(index, name)
    return None
