"""Data models for the metrics report tree."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Role = Literal["core", "leaf", "helper"]
CallableKind = Literal[
    "function",
    "method",
    "classmethod",
    "staticmethod",
    "nested_function",
]


@dataclass
class CallableMetrics:
    name: str
    qualified_name: str
    kind: CallableKind
    lineno: int
    role: Role = "helper"
    parent: str | None = None
    cyclomatic: int = 1
    v_poly: int = 1
    cognitive: int = 0
    max_nesting: int = 0
    params: int = 0
    statements: int = 0
    returns: int = 0
    fan_in: int = 0
    fan_in_ext: int = 0
    fan_in_rec: int = 0
    body_tokens: int = 0
    header_tokens: int = 0
    mean_call_cost: float = 3.0
    S: float = 0.0
    etspa: float = 0.0
    car: float = 0.0
    lmd: float = 0.0
    cvr: float = 0.0
    assign_count: int = 0
    call_count: int = 0
    local_stores: int = 0
    comprehension_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClassMetrics:
    name: str
    qualified_name: str
    lineno: int
    lcom4: int = 0
    wmc: int = 0
    nom: int = 0
    methods: list[CallableMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "lineno": self.lineno,
            "metrics": {
                "lcom4": self.lcom4,
                "wmc": self.wmc,
                "nom": self.nom,
            },
            "methods": [m.to_dict() for m in self.methods],
        }


@dataclass
class ModuleRollup:
    callable_count: int = 0
    class_count: int = 0
    sum_S: float = 0.0
    frac_S_le_0: float = 0.0
    frac_fan_in_le_1: float = 0.0
    max_v_poly: int = 0
    max_nesting: int = 0
    mean_cyclomatic: float = 0.0
    mean_cognitive: float = 0.0
    mean_car: float = 0.0
    mean_lmd: float = 0.0
    roles: dict[str, int] = field(default_factory=lambda: {"core": 0, "leaf": 0, "helper": 0})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModuleReport:
    path: str
    name: str
    metrics: ModuleRollup = field(default_factory=ModuleRollup)
    imports: list[str] = field(default_factory=list)
    scc_id: int | None = None
    functions: list[CallableMetrics] = field(default_factory=list)
    classes: list[ClassMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "metrics": self.metrics.to_dict(),
            "imports": {"imports": self.imports, "scc_id": self.scc_id},
            "functions": [f.to_dict() for f in self.functions],
            "classes": [c.to_dict() for c in self.classes],
        }


@dataclass
class OverallReport:
    totals: dict[str, int] = field(
        default_factory=lambda: {
            "modules": 0,
            "classes": 0,
            "functions": 0,
            "methods": 0,
        }
    )
    complexity: dict[str, float] = field(
        default_factory=lambda: {
            "max_v_poly": 0,
            "max_nesting": 0,
            "mean_cyclomatic": 0.0,
            "mean_cognitive": 0.0,
        }
    )
    etspa: dict[str, float] = field(
        default_factory=lambda: {
            "sum_S": 0.0,
            "frac_S_le_0": 0.0,
            "frac_fan_in_le_1": 0.0,
        }
    )
    expression: dict[str, float] = field(
        default_factory=lambda: {
            "mean_car": 0.0,
            "mean_lmd": 0.0,
            "mean_cvr": 0.0,
        }
    )
    roles: dict[str, int] = field(default_factory=lambda: {"core": 0, "leaf": 0, "helper": 0})
    imports: dict[str, Any] = field(
        default_factory=lambda: {
            "edge_count": 0,
            "cycle_count": 0,
            "cycles": [],
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetricsReport:
    version: int = 1
    tool: str = "py-code-metrics"
    input: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(
        default_factory=lambda: {
            "nesting_depth": 3,
            "params": 5,
            "v_poly_strict": 10,
            "v_poly_lenient": 15,
            "cognitive": 15,
            "statements": 50,
            "lcom4_max": 1,
        }
    )
    overall: OverallReport = field(default_factory=OverallReport)
    modules: list[ModuleReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tool": self.tool,
            "input": self.input,
            "thresholds": self.thresholds,
            "overall": self.overall.to_dict(),
            "modules": [m.to_dict() for m in self.modules],
        }
