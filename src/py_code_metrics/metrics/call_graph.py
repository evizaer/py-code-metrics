"""Collect Call nodes inside a function, excluding nested defs."""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class CallSite:
    caller_qname: str
    callee_qname: str | None
    call: ast.Call
    module: str


@dataclass
class CallGraph:
    """Resolved call edges within the corpus."""

    fan_in_sites: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    sites: list[CallSite] = field(default_factory=list)

    def fan_in_ext(self, qname: str) -> int:
        return sum(1 for caller in self.fan_in_sites.get(qname, []) if caller != qname)

    def fan_in_rec(self, qname: str) -> int:
        return sum(1 for caller in self.fan_in_sites.get(qname, []) if caller == qname)

    def fan_in_total(self, qname: str) -> int:
        return len(self.fan_in_sites.get(qname, []))


def collect_calls_in_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    calls: list[ast.Call] = []

    def walk(n: ast.AST) -> None:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not node:
            return
        if isinstance(n, ast.Call):
            calls.append(n)
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            walk(child)

    for stmt in node.body:
        walk(stmt)
    return calls
