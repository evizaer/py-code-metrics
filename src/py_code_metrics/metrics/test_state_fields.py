"""Static state-field coverage (oracle quality proxy; Maguirre et al. ASE 2025)."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from py_code_metrics.discover import is_test_file
from py_code_metrics.metrics.test_oracles import (
    TestFunctionInfo,
    extract_test_functions,
)
from py_code_metrics.model import TestCaseMetrics, TestMetricsReport, TestModuleReport
from py_code_metrics.resolve import SymbolIndex

COLLECTION_NAMES = frozenset(
    {
        "list",
        "dict",
        "set",
        "tuple",
        "List",
        "Dict",
        "Set",
        "Tuple",
        "Sequence",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "frozenset",
        "FrozenSet",
    }
)
TYPE_GRAPH_DEPTH = 3


@dataclass
class ClassState:
    qname: str
    fields: dict[str, str | None] = field(default_factory=dict)
    coverable: list[str] = field(default_factory=list)


def apply_state_field_coverage(
    report: TestMetricsReport,
    index: SymbolIndex,
    root: Path,
) -> None:
    """Compute state-field coverage for production classes targeted by tests."""
    states = _build_class_states(index)
    if not states:
        return

    covered_by_class: dict[str, set[str]] = {q: set() for q in states}
    targeted: set[str] = set()
    test_infos = _index_test_infos(index)

    for mod in report.modules:
        for case in mod.tests:
            _accumulate_case(
                case,
                test_infos,
                index,
                states,
                covered_by_class,
                targeted,
            )

    details = _class_details(states, covered_by_class, targeted)
    report.overall.state_field_classes = details
    report.overall.uncovered_state_fields = [
        {"class": d["class"], "field": f} for d in details for f in d["uncovered"]
    ]
    report.overall.uncovered_state_field_count = len(report.overall.uncovered_state_fields)
    scores = [float(d["score"]) for d in details]
    report.overall.mean_state_field_coverage = sum(scores) / len(scores) if scores else None
    _attach_module_sfc(report, details, index)


def _accumulate_case(
    case: TestCaseMetrics,
    test_infos: dict[tuple[str, str], TestFunctionInfo],
    index: SymbolIndex,
    states: dict[str, ClassState],
    covered_by_class: dict[str, set[str]],
    targeted: set[str],
) -> None:
    if case.exempt:
        return
    info = test_infos.get((case.file, case.qualified_name))
    if info is None:
        return
    import_hints = _import_class_hints(index, states)
    locals_map = _local_class_map(info.node, states, import_hints)
    targets = _target_classes(case, index, states, info, locals_map, import_hints)
    if not targets:
        return
    targeted.update(targets)
    labels = _covered_labels(info, targets, states, index)
    for cq in targets:
        covered_by_class[cq].update(labels.get(cq, set()))


def _import_class_hints(index: SymbolIndex, states: dict[str, ClassState]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for mi in index.modules.values():
        for local, target in mi.local_names.items():
            cq = _class_from_import_target(target, states)
            if cq:
                hints[local] = cq
    return hints


def _class_from_import_target(target: str, states: dict[str, ClassState]) -> str | None:
    if target in states:
        return target
    simple = target.rsplit(".", 1)[-1]
    return _unique_class_suffix(simple, states)


def _unique_class_suffix(simple: str, states: dict[str, ClassState]) -> str | None:
    matches = [q for q in states if q.endswith(f".{simple}") or q == simple]
    return matches[0] if len(matches) == 1 else None


def _hint_to_state(
    hint: str | None, states: dict[str, ClassState], import_hints: dict[str, str]
) -> str | None:
    if not hint:
        return None
    if hint in states:
        return hint
    if hint in import_hints:
        return import_hints[hint]
    return _unique_class_suffix(hint.split(".")[-1], states)


def _constructor_class(
    value: ast.expr, states: dict[str, ClassState], import_hints: dict[str, str]
) -> str | None:
    if not isinstance(value, ast.Call):
        return None
    if isinstance(value.func, ast.Name):
        return _hint_to_state(value.func.id, states, import_hints)
    if isinstance(value.func, ast.Attribute):
        return _hint_to_state(value.func.attr, states, import_hints)
    return None


def _local_class_map(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    states: dict[str, ClassState],
    import_hints: dict[str, str],
) -> dict[str, str]:
    binding: dict[str, str] = {}
    for child in ast.walk(node):
        _bind_ann_local(child, binding, states, import_hints)
        _bind_assign_local(child, binding, states, import_hints)
    return binding


def _bind_ann_local(
    child: ast.AST,
    binding: dict[str, str],
    states: dict[str, ClassState],
    import_hints: dict[str, str],
) -> None:
    if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name):
        return
    hint = _annotation_name(child.annotation) if child.annotation else None
    cq = _hint_to_state(hint, states, import_hints)
    if cq:
        binding[child.target.id] = cq


def _bind_assign_local(
    child: ast.AST,
    binding: dict[str, str],
    states: dict[str, ClassState],
    import_hints: dict[str, str],
) -> None:
    if not isinstance(child, ast.Assign):
        return
    cq = _constructor_class(child.value, states, import_hints)
    if cq is None:
        return
    for t in child.targets:
        if isinstance(t, ast.Name):
            binding[t.id] = cq


def _build_class_states(index: SymbolIndex) -> dict[str, ClassState]:
    raw: dict[str, ClassState] = {}
    for qname, ci in index.classes.items():
        mi = index.modules.get(ci.module)
        if mi is None or is_test_file(Path(mi.path)):
            continue
        fields = _collect_fields(ci.node)
        if fields:
            raw[qname] = ClassState(qname=qname, fields=fields)
    for state in raw.values():
        state.coverable = _coverable_labels(state, raw)
    return {q: s for q, s in raw.items() if s.coverable}


def _collect_fields(node: ast.ClassDef) -> dict[str, str | None]:
    fields: dict[str, str | None] = {}
    for stmt in node.body:
        _collect_class_body_field(stmt, fields)
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect_method_self_stores(stmt, fields)
    return {k: v for k, v in fields.items() if not k.startswith("__")}


def _collect_class_body_field(stmt: ast.stmt, fields: dict[str, str | None]) -> None:
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        fields[stmt.target.id] = _annotation_name(stmt.annotation)
    elif isinstance(stmt, ast.Assign):
        for t in stmt.targets:
            if isinstance(t, ast.Name) and not t.id.startswith("_"):
                fields.setdefault(t.id, None)


def _collect_method_self_stores(
    stmt: ast.FunctionDef | ast.AsyncFunctionDef, fields: dict[str, str | None]
) -> None:
    self_name = stmt.args.args[0].arg if stmt.args.args else None
    if self_name is None:
        return
    param_hints = _param_annotation_map(stmt)
    for child in ast.walk(stmt):
        _record_self_ann_store(child, self_name, fields)
        _record_self_assign_store(child, self_name, fields, param_hints)


def _record_self_ann_store(child: ast.AST, self_name: str, fields: dict[str, str | None]) -> None:
    if not isinstance(child, ast.AnnAssign):
        return
    name = _self_attr_store(child.target, self_name)
    if name:
        fields[name] = _annotation_name(child.annotation) or fields.get(name)


def _record_self_assign_store(
    child: ast.AST,
    self_name: str,
    fields: dict[str, str | None],
    param_hints: dict[str, str | None],
) -> None:
    if not isinstance(child, ast.Assign):
        return
    for target in child.targets:
        name = _self_attr_store(target, self_name)
        if name:
            fields.setdefault(name, fields.get(name) or param_hints.get(name))


def _param_annotation_map(
    stmt: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for arg in stmt.args.args[1:]:
        if arg.annotation is not None:
            out[arg.arg] = _annotation_name(arg.annotation)
    return out


def _self_attr_store(target: ast.expr, self_name: str) -> str | None:
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == self_name
    ):
        return target.attr
    return None


def _annotation_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # X | None → prefer non-None side
        left = _annotation_name(node.left)
        right = _annotation_name(node.right)
        if left == "None":
            return right
        if right == "None":
            return left
        return left or right
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts: list[str] = []
        cur: ast.expr | None = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return parts[0] if parts else None
    if isinstance(node, ast.Subscript):
        return _annotation_name(node.value)
    if isinstance(node, ast.Constant) and node.value is None:
        return "None"
    return None


def _coverable_labels(state: ClassState, all_states: dict[str, ClassState]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    def add(label: str) -> None:
        if label not in seen:
            seen.add(label)
            labels.append(label)

    def walk(cq: str, prefix: str, depth: int) -> None:
        st = all_states.get(cq)
        if st is None or depth < 0:
            return
        simple = cq.rsplit(".", 1)[-1]
        for name, hint in st.fields.items():
            label = f"{prefix}{name}" if prefix else name
            add(label)
            if _is_iterable_hint(hint) or hint == simple:
                add(f"{label}+")
            nested = _resolve_hint_class(hint, cq, all_states)
            if nested == cq:
                add(f"{label}+")
            elif nested and depth > 0:
                walk(nested, f"{label}.", depth - 1)

    walk(state.qname, "", TYPE_GRAPH_DEPTH)
    return labels


def _is_iterable_hint(hint: str | None) -> bool:
    if not hint:
        return False
    return hint.split(".")[-1] in COLLECTION_NAMES


def _resolve_hint_class(
    hint: str | None, owner_qname: str, all_states: dict[str, ClassState]
) -> str | None:
    if not hint:
        return None
    if hint in all_states:
        return hint
    simple = hint.split(".")[-1]
    owner_mod = owner_qname.rsplit(".", 1)[0] if "." in owner_qname else ""
    candidate = f"{owner_mod}.{simple}" if owner_mod else simple
    if candidate in all_states:
        return candidate
    matches = [q for q in all_states if q.endswith(f".{simple}") or q == simple]
    return matches[0] if len(matches) == 1 else None


def _index_test_infos(
    index: SymbolIndex,
) -> dict[tuple[str, str], TestFunctionInfo]:
    out: dict[tuple[str, str], TestFunctionInfo] = {}
    root = index.root
    for mi in index.modules.values():
        if not is_test_file(Path(mi.path)):
            continue
        try:
            rel = str(mi.path.resolve().relative_to(root.resolve()))
        except ValueError:
            rel = str(mi.path)
        for info in extract_test_functions(mi.tree):
            out[(rel, info.qualified_name)] = info
            out[(str(Path(rel).as_posix()), info.qualified_name)] = info
    return out


def _target_classes(
    case: TestCaseMetrics,
    index: SymbolIndex,
    states: dict[str, ClassState],
    info: TestFunctionInfo,
    locals_map: dict[str, str],
    import_hints: dict[str, str],
) -> set[str]:
    targets: set[str] = set(locals_map.values())
    for qname in case.calls_production:
        call_info = index.callables.get(qname)
        if call_info is None or not call_info.class_qname:
            continue
        if call_info.class_qname in states:
            targets.add(call_info.class_qname)
    for child in ast.walk(info.node):
        if isinstance(child, ast.Call):
            cq = _constructor_class(child, states, import_hints)
            if cq:
                targets.add(cq)
    return targets


def _covered_labels(
    info: TestFunctionInfo,
    targets: set[str],
    states: dict[str, ClassState],
    index: SymbolIndex,
) -> dict[str, set[str]]:
    exprs = _oracle_exprs(info.node)
    attrs, loop_attrs, callee_methods = _scan_oracle_exprs(exprs)
    return {
        cq: _hits_for_class(cq, states, attrs, loop_attrs, callee_methods, index) for cq in targets
    }


def _hits_for_class(
    cq: str,
    states: dict[str, ClassState],
    attrs: set[str],
    loop_attrs: set[str],
    callee_methods: set[str],
    index: SymbolIndex,
) -> set[str]:
    field_names = set(states[cq].fields)
    hits = {a for a in attrs if a in field_names}
    for attr in loop_attrs:
        if attr in field_names:
            hits.add(attr)
            hits.add(f"{attr}+")
    hits.update(_one_hop_field_hits(cq, field_names, callee_methods, index))
    return hits


def _one_hop_field_hits(
    cq: str,
    field_names: set[str],
    callee_methods: set[str],
    index: SymbolIndex,
) -> set[str]:
    hits: set[str] = set()
    for method_name in callee_methods:
        method = index.callables.get(f"{cq}.{method_name}")
        if method is None:
            continue
        hits.update(a for a in _instance_attrs_read(method.node) if a in field_names)
    return hits


def _oracle_exprs(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    exprs: list[ast.AST] = []

    class Collector(ast.NodeVisitor):
        def visit_Assert(self, n: ast.Assert) -> None:
            exprs.append(n.test)

        def visit_Call(self, n: ast.Call) -> None:
            parts = _dotted(n.func)
            if parts and parts[0] == "self" and parts[-1].lower().startswith("assert"):
                exprs.extend(n.args)
                exprs.extend(k.value for k in n.keywords)
            self.generic_visit(n)

        def visit_With(self, n: ast.With) -> None:
            for item in n.items:
                exprs.append(item.context_expr)
            self.generic_visit(n)

        def visit_AsyncWith(self, n: ast.AsyncWith) -> None:
            for item in n.items:
                exprs.append(item.context_expr)
            self.generic_visit(n)

    Collector().visit(node)
    return exprs


def _scan_oracle_exprs(
    exprs: list[ast.AST],
) -> tuple[set[str], set[str], set[str]]:
    attrs: set[str] = set()
    loop_attrs: set[str] = set()
    callees: set[str] = set()
    for expr in exprs:
        attrs.update(_attrs_in(expr))
        callees.update(_callees_in(expr))
        loop_attrs.update(_loop_attrs_in(expr))
    return attrs, loop_attrs, callees


def _attrs_in(node: ast.AST) -> set[str]:
    return {c.attr for c in ast.walk(node) if isinstance(c, ast.Attribute)}


def _callees_in(node: ast.AST) -> set[str]:
    return {
        c.func.attr
        for c in ast.walk(node)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
    }


def _loop_attrs_in(node: ast.AST) -> set[str]:
    attrs: set[str] = set()
    for loop in _loops_in(node):
        attrs.update(_attrs_in(loop))
    return attrs


def _loops_in(node: ast.AST) -> list[ast.AST]:
    return [
        n
        for n in ast.walk(node)
        if isinstance(n, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.GeneratorExp))
    ]


def _instance_attrs_read(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    self_name = node.args.args[0].arg if node.args.args else None
    if not self_name:
        return set()
    return {
        child.attr
        for child in ast.walk(node)
        if isinstance(child, ast.Attribute)
        and isinstance(child.value, ast.Name)
        and child.value.id == self_name
    }


def _dotted(node: ast.expr) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_dotted(node.value), node.attr]
    return []


def _class_details(
    states: dict[str, ClassState],
    covered_by_class: dict[str, set[str]],
    targeted: set[str],
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for cq in sorted(targeted):
        st = states.get(cq)
        if st is None or not st.coverable:
            continue
        coverable = list(st.coverable)
        covered = sorted(c for c in covered_by_class.get(cq, set()) if c in coverable)
        uncovered = [c for c in coverable if c not in covered]
        score = len(covered) / len(coverable) if coverable else 0.0
        details.append(
            {
                "class": cq,
                "coverable": coverable,
                "covered": covered,
                "uncovered": uncovered,
                "score": score,
            }
        )
    return details


def _attach_module_sfc(
    report: TestMetricsReport,
    details: list[dict[str, Any]],
    index: SymbolIndex,
) -> None:
    score_by_class = {d["class"]: float(d["score"]) for d in details}
    for mod in report.modules:
        exercised = _module_exercised_scores(mod, score_by_class, index)
        mod.metrics.mean_state_field_coverage = (
            sum(exercised) / len(exercised) if exercised else None
        )


def _module_exercised_scores(
    mod: TestModuleReport,
    score_by_class: dict[str, float],
    index: SymbolIndex,
) -> list[float]:
    exercised: list[float] = []
    seen: set[str] = set()
    for t in mod.tests:
        for q in t.calls_production:
            info = index.callables.get(q)
            if info is None or not info.class_qname or info.class_qname in seen:
                continue
            if info.class_qname in score_by_class:
                seen.add(info.class_qname)
                exercised.append(score_by_class[info.class_qname])
    return exercised
