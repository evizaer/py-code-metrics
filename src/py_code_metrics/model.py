"""Data models for the metrics report tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from py_code_metrics.serde import MappingMixin

Role = Literal["core", "leaf", "helper"]
CallableKind = Literal[
    "function",
    "method",
    "classmethod",
    "staticmethod",
    "nested_function",
]
OracleTier = Literal["none", "weak", "strong"]
TestFramework = Literal["pytest", "unittest", "unknown"]
Severity = Literal["high", "low", "info"]

_OMIT_NONE = {"omit_none": True}


@dataclass(frozen=True)
class Thresholds(MappingMixin):
    """Soft gates emitted in reports and used by hotspot predicates.

    Per-callable size (`statements`, body/header tokens) stays on each callable
    as context only — it is intentionally absent here so agents do not treat
    length as a split mandate when nesting / cognitive / ``v_poly`` are fine.
    """

    nesting_depth: int = 3
    params: int = 5
    v_poly_strict: int = 10
    v_poly_lenient: int = 15
    cognitive: int = 15
    lcom4_max: int = 1


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class SkippedFileEntry(MappingMixin):
    path: str
    reason: str


@dataclass
class ReportInput(MappingMixin):
    root: str = ""
    files_analyzed: int = 0
    files_skipped: list[SkippedFileEntry] = field(default_factory=list)
    coverage_path: str | None = field(default=None, metadata=_OMIT_NONE)
    coverage_has_contexts: bool | None = field(default=None, metadata=_OMIT_NONE)
    mutation_path: str | None = field(default=None, metadata=_OMIT_NONE)
    mutation_format: str | None = field(default=None, metadata=_OMIT_NONE)
    delta: bool | None = field(default=None, metadata=_OMIT_NONE)
    files_in_delta: list[str] | None = field(default=None, metadata=_OMIT_NONE)
    delta_note: str | None = field(default=None, metadata=_OMIT_NONE)


@dataclass
class RoleCounts(MappingMixin):
    core: int = 0
    leaf: int = 0
    helper: int = 0

    def bump(self, role: str) -> None:
        if role == "core":
            self.core += 1
        elif role == "leaf":
            self.leaf += 1
        else:
            self.helper += 1


@dataclass
class CallableMetrics(MappingMixin):
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
    dispatch_exempt: bool = False
    unpaid: bool = False
    reduction_like: bool = False
    n_dou_sites: int = 0
    dou_sites: list[DouSite] = field(default_factory=list)


@dataclass
class DouImpact(MappingMixin):
    """Prioritization fields for a DOU candidate (sort keys, not a blended score)."""

    fan_out_sites: int = 0
    key_vocab_size: int = 0
    cross_module: bool = False
    on_public_api: bool = False
    churn_hint: bool | None = field(default=None, metadata=_OMIT_NONE)


@dataclass
class DouSite(MappingMixin):
    dou_kind: str = "record_annotation"
    site: str = "param"  # param | return | attr
    name: str | None = field(default=None, metadata=_OMIT_NONE)
    annotation: str = ""
    impact: DouImpact = field(default_factory=DouImpact)


@dataclass
class DouHotspotEntry(MappingMixin):
    qualified_name: str
    n_dou_sites: int = 0
    annotation: str = ""
    impact: DouImpact = field(default_factory=DouImpact)
    path: str | None = field(default=None, metadata=_OMIT_NONE)


@dataclass
class DouBoard(MappingMixin):
    n_dou_sites: int = 0
    n_dou_callables: int = 0


@dataclass
class ClassMetrics(MappingMixin):
    name: str
    qualified_name: str
    lineno: int
    lcom4: int = field(default=0, metadata={"nest": "metrics"})
    wmc: int = field(default=0, metadata={"nest": "metrics"})
    nom: int = field(default=0, metadata={"nest": "metrics"})
    dispatch_class: bool = field(default=False, metadata={"nest": "metrics"})
    lcom4_gate_exempt: bool = field(default=False, metadata={"nest": "metrics"})
    methods: list[CallableMetrics] = field(default_factory=list)


@dataclass
class ModuleRollup(MappingMixin):
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
    n_v_poly_gt_15: int = 0
    n_nesting_gt_3: int = 0
    n_unpaid_v_poly_gt_15: int = 0
    n_unpaid_nesting_gt_3: int = 0
    n_unpaid_hotspots: int = 0
    n_dou_sites: int = 0
    roles: RoleCounts = field(default_factory=RoleCounts)


@dataclass
class ModuleReport(MappingMixin):
    path: str
    name: str
    metrics: ModuleRollup = field(default_factory=ModuleRollup)
    imports: list[str] = field(default_factory=list, metadata={"nest": "imports"})
    scc_id: int | None = field(default=None, metadata={"nest": "imports"})
    functions: list[CallableMetrics] = field(default_factory=list)
    classes: list[ClassMetrics] = field(default_factory=list)


@dataclass
class OverallTotals(MappingMixin):
    modules: int = 0
    classes: int = 0
    functions: int = 0
    methods: int = 0


@dataclass
class ComplexityBoard(MappingMixin):
    max_v_poly: int = 0
    max_nesting: int = 0
    mean_cyclomatic: float = 0.0
    mean_cognitive: float = 0.0
    n_v_poly_gt_15: int = 0
    n_nesting_gt_3: int = 0
    n_unpaid_v_poly_gt_15: int = 0
    n_unpaid_nesting_gt_3: int = 0
    n_unpaid_hotspots: int = 0


@dataclass
class HelpersCoresEtspa(MappingMixin):
    callable_count: int = 0
    sum_S: float = 0.0
    frac_S_le_0: float = 0.0
    frac_fan_in_le_1: float = 0.0


ETSPA_GLOBAL_NOTE = "Global fracs mix leaves+helpers; prefer helpers_cores for gates."


@dataclass
class EtspaOverall(MappingMixin):
    sum_S: float = 0.0
    frac_S_le_0: float = 0.0
    frac_fan_in_le_1: float = 0.0
    note: str = ETSPA_GLOBAL_NOTE
    helpers_cores: HelpersCoresEtspa = field(default_factory=HelpersCoresEtspa)


@dataclass
class LeavesExpressionBoard(MappingMixin):
    callable_count: int = 0
    mean_car: float = 0.0
    mean_lmd: float = 0.0
    mean_nesting: float = 0.0
    mean_cognitive: float = 0.0


@dataclass
class ExpressionOverall(MappingMixin):
    mean_car: float = 0.0
    mean_lmd: float = 0.0
    mean_cvr: float = 0.0
    leaves: LeavesExpressionBoard = field(default_factory=LeavesExpressionBoard)


@dataclass
class HotspotEntry(MappingMixin):
    qualified_name: str
    v_poly: int = 0
    nesting: int = 0
    cognitive: int = 0
    fan_in_ext: int = 0
    S: float = 0.0
    role: Role = "helper"
    unpaid: bool = True
    reduction_like: bool = False
    dispatch_exempt: bool = False
    path: str | None = field(default=None, metadata=_OMIT_NONE)


@dataclass
class ImportsOverall(MappingMixin):
    edge_count: int = 0
    cycle_count: int = 0
    cycles: list[list[str]] = field(default_factory=list)


@dataclass
class OverallReport(MappingMixin):
    totals: OverallTotals = field(default_factory=OverallTotals)
    complexity: ComplexityBoard = field(default_factory=ComplexityBoard)
    etspa: EtspaOverall = field(default_factory=EtspaOverall)
    expression: ExpressionOverall = field(default_factory=ExpressionOverall)
    hotspots: list[HotspotEntry] = field(default_factory=list)
    dou: DouBoard = field(default_factory=DouBoard)
    dou_hotspots: list[DouHotspotEntry] = field(default_factory=list)
    roles: RoleCounts = field(default_factory=RoleCounts)
    imports: ImportsOverall = field(default_factory=ImportsOverall)


@dataclass
class MetricsReport(MappingMixin):
    version: int = 2
    tool: str = "py-code-metrics"
    input: ReportInput = field(default_factory=ReportInput)
    thresholds: Thresholds = field(default_factory=lambda: DEFAULT_THRESHOLDS)
    overall: OverallReport = field(default_factory=OverallReport)
    modules: list[ModuleReport] = field(default_factory=list)


@dataclass(frozen=True)
class TestThresholds(MappingMixin):
    __test__ = False

    frac_oracle_none_warn: float = 0.10
    prefer_strong_majority: bool = True
    no_oracle: Severity = "high"
    tautology: Severity = "high"
    weak_oracle: Severity = "low"
    swallowed_error: Severity = "high"
    empty_body: Severity = "high"
    weak_oracle_covered_line: Severity = "low"
    mutation_score_warn: float = 0.85
    unchecked_state_field: Severity = "low"


DEFAULT_TEST_THRESHOLDS = TestThresholds()


@dataclass
class OracleHistogram(MappingMixin):
    none: int = 0
    weak: int = 0
    strong: int = 0

    def bump(self, tier: str) -> None:
        if tier == "none":
            self.none += 1
        elif tier == "weak":
            self.weak += 1
        else:
            self.strong += 1


@dataclass
class HighSeverityFinding(MappingMixin):
    file: str
    name: str
    lineno: int
    smell_codes: list[str] = field(default_factory=list)
    oracle_tier: OracleTier = "none"


@dataclass
class WeakOracleCoveredLine(MappingMixin):
    file: str
    line: int
    tests: list[str] = field(default_factory=list)
    best_oracle_tier: OracleTier = "weak"


@dataclass
class MutationSurvivor(MappingMixin):
    file: str = ""
    line: int | None = None
    id: Any = None
    operator: Any = None
    status: str = "survived"
    overlap_flags: list[str] = field(default_factory=list)


@dataclass
class UncoveredStateField(MappingMixin):
    class_: str = field(metadata={"key": "class"})
    field: str


@dataclass
class StateFieldClassDetail(MappingMixin):
    class_: str = field(metadata={"key": "class"})
    coverable: list[str] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class TestCaseMetrics(MappingMixin):
    __test__ = False

    name: str
    qualified_name: str
    lineno: int
    file: str
    framework: TestFramework = "unknown"
    assertion_count: int = 0
    oracle_tier: OracleTier = "none"
    oracle_kinds: list[str] = field(default_factory=list)
    smell_codes: list[str] = field(default_factory=list)
    severity: Severity = "info"
    markers: list[str] = field(default_factory=list)
    exempt: bool = False
    calls_production: list[str] = field(default_factory=list)


@dataclass
class TestModuleRollup(MappingMixin):
    __test__ = False

    test_count: int = 0
    frac_oracle_none: float = 0.0
    frac_oracle_weak: float = 0.0
    frac_oracle_strong: float = 0.0
    mean_assertion_density: float = 0.0
    high_severity_count: int = 0
    coverage_line: float | None = None
    coverage_branch: float | None = None
    weak_oracle_covered_line_count: int = 0
    unchecked_covered_callable_count: int = 0
    survivor_count: int = 0
    mean_state_field_coverage: float | None = None


@dataclass
class TestModuleReport(MappingMixin):
    __test__ = False

    path: str
    name: str
    metrics: TestModuleRollup = field(default_factory=TestModuleRollup)
    tests: list[TestCaseMetrics] = field(default_factory=list)


@dataclass
class TestOverallReport(MappingMixin):
    __test__ = False

    test_count: int = 0
    module_count: int = 0
    frac_oracle_none: float = 0.0
    frac_oracle_weak: float = 0.0
    frac_oracle_strong: float = 0.0
    mean_assertion_density: float = 0.0
    high_severity_count: int = 0
    high_severity_findings: list[HighSeverityFinding] = field(default_factory=list)
    oracle_histogram: OracleHistogram = field(default_factory=OracleHistogram)
    coverage_line: float | None = None
    coverage_branch: float | None = None
    unchecked_covered_callables: list[str] = field(default_factory=list)
    weak_oracle_covered_lines: list[WeakOracleCoveredLine] = field(default_factory=list)
    unchecked_covered_callable_count: int = 0
    weak_oracle_covered_line_count: int = 0
    mutation_score: float | None = None
    survivor_count: int = 0
    survivors: list[MutationSurvivor] = field(default_factory=list)
    mean_state_field_coverage: float | None = None
    uncovered_state_fields: list[UncoveredStateField] = field(default_factory=list)
    state_field_classes: list[StateFieldClassDetail] = field(default_factory=list)
    uncovered_state_field_count: int = 0


@dataclass
class TestMetricsReport(MappingMixin):
    __test__ = False

    version: int = 1
    tool: str = "py-code-metrics"
    mode: str = "tests"
    input: ReportInput = field(default_factory=ReportInput)
    thresholds: TestThresholds = field(default_factory=lambda: DEFAULT_TEST_THRESHOLDS)
    overall: TestOverallReport = field(default_factory=TestOverallReport)
    modules: list[TestModuleReport] = field(default_factory=list)
