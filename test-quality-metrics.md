# Test Quality Metrics: Research Notes and Module Plan

**Purpose.** Identify metrics that keep automated test suites *adequately covering* production code while actively flagging *fake* or *useless* tests—especially assertion-free smoke stubs, tautologies, and weak oracles that inflate coverage without verifying behavior. Target consumers: humans and agentic workflows using `py-code-metrics` (and a future test-focused companion module).

**Verdict.** Line/branch coverage measures **execution**, not **verification**. A complementary suite is required: (1) coverage adequacy as a floor, (2) static oracle/smell signals as a fast fake-test detector, (3) mutation (or mutation-correlated proxies) as the gold standard for fault-detection power. Single-metric optimization is unsafe under Goodhart pressure—agents optimizing “coverage %” or “tests exist” correctly emit the cheapest green artifacts. Pair coverage with oracle strength; pair oracle counts with mutation or state-field checks so strong-looking assertions that check the wrong thing still fail.

**Status (2026-07).** P0 static fake-test detection is implemented (`metrics/test_oracles.py`, `metrics/test_smells.py`, `analyze_tests.py`). **P1** production linkage + coverage ingest is implemented (`metrics/test_sut.py`, `metrics/test_coverage.py`, `metrics/test_delta.py`; CLI `--coverage` / `--delta`). **P2** mutation ingest + state-field coverage is implemented (`metrics/test_mutation.py`, `metrics/test_state_fields.py`; CLI `--mutation`; SFC always-on). Rounds 1–3 hardened the production complementary board; Round 4 landed P1; Round 6 landed P2 (see [`docs/metrics-iteration-log.md`](docs/metrics-iteration-log.md)). Next coding fork: **P3** gates and agent UX.

---

## 1. The problem: coverage lies by omission

Industry and research consensus (Trail of Bits 2026; MutGen / IEEE TSE 2026; Banik et al. 2026):

| What coverage says | What it does *not* say |
| --- | --- |
| Which lines/branches ran under the suite | Whether any observable was checked |
| That a path was exercised | That a fault on that path would be detected |
| That a `test_*` file touched production code | That the test encodes requirements vs accidents |

Concrete failure modes:

- **Assertion-free theater.** Call the SUT (sometimes under bare `try/except`), assert nothing. Coverage rises; behavioral signal is “did not crash.” Banik et al. (2026) found **80.2%** of agent-authored test patches across 86k+ test-file PRs carried weak or no explicit oracle signals when graded against an eight-category taxonomy.
- **100% coverage / near-zero mutation score.** MutGen reports suites with **100% line coverage but ~4% mutation score**—tests execute everything and verify almost nothing.
- **Presence gates.** Merge rules of the form “new code has a test file” incentivize smoke stubs. The defect is often the **gate predicate**, not the agent: cheapest passing output wins.
- **Incidental coverage.** Helpers hit via unrelated tests get “covered” without localized oracles (mutmut’s `max_stack_depth` guidance exists for this reason).

**Implication for this project.** Treat coverage as a *necessary but insufficient* floor. The module’s distinctive value is flagging tests that make the floor look healthy while contributing little fault-detection power.

---

## 2. Taxonomy of “fake” / low-value tests

Useful operational categories (drawn from rotten-green-test research, falsegreen/Pragma catalogs, classic tautology writing, and Banik’s oracle tiers):

### 2.1 Oracle tiers (behavioral signal)

| Tier | Pattern | Signal |
| --- | --- | --- |
| **None** | Call-only / smoke; swallowed exceptions; no assert / `expect.assertions(0)` | Crash-only |
| **Weak** | `assert result`, `assert x is not None`, `assertTrue`, `len > 0`, `"x" in str(...)` | Truthiness / non-null |
| **Strong** | Specific value, boundary, state, exception type+message, differential vs reference | Behavioral |

Legitimate exceptions (do **not** auto-fail): import/integration pings, property-based/Hypothesis tests (oracle lives in the runner), intentional smoke suites, early-spike churn where brittle value asserts rot faster than they help.

### 2.2 Static false-positive families (parser-provable)

Tools such as [falsegreen](https://github.com/vinicq/falsegreen) (Python/pytest AST scanner) and [Pragma](https://github.com/Joncik91/pragma) encode patterns grounded in Delplanque et al. (ICSE 2019) and Soares (2023) rotten-green work:

| Family | Examples | Why useless |
| --- | --- | --- |
| Empty / never-runs | No assert; assert in dead branch; commented-out assert | Green regardless of SUT |
| Always-true / tautology | `assert True`, `assert 1 == 1`, self-compare | Passes unconditionally |
| Weak check | Truthiness, `len > 0` only | Accepts almost any broken result |
| Swallowed failure | Broad `except: pass` / skip-in-except | Turns red into green/yellow |
| Mock theater | Mocks the unit under test; mistyped mock assert | Tests the mock |
| Name/body mismatch | `test_raises_*` with no raise expectation | Claims a path it never checks |
| Flaky / order | Time/random/sleep dependence; order-dependent state | Passes by luck |

Semantic layer (often LLM-assisted): expected value contradicts production intent; freezes a bug as correct; mocks SUT by design—patterns a pure AST pass cannot prove.

### 2.3 Tautological / homogenized tests

Distinct from empty asserts: the test **reimplements or mirrors** production logic (shared helpers for expected values, over-mocking so the test reconstructs the implementation). These pass while encoding implementation accidents; they fail when internals change and miss real regressions (Coulman; Williams). Agent co-generation of code+tests amplifies **test homogenization**—same blind spots in production and oracle.

### 2.4 Test smells (maintainability vs effectiveness)

Classic catalogs (tsDetect, PyNose, ICSME 2025 prioritization work) include Assertion Roulette, Eager Test, Conditional Test Logic, Duplicate Assert, Redundant Assertion, Obscure Inline Setup, Mystery Guest, etc. Recent Python work ranks **Conditional Test Logic, Duplicate Assert, Obscure In-Line Setup, Redundant Assertion** as high priority by both empirical risk and developer agreement.

**Module stance:** smell metrics inform *maintainability* and *review priority*; for “fake test” flagging, prioritize **oracle absence/weakness** and **mutation survivors** over every maintainability smell.

---

## 3. Metric families (research inventory)

### 3.1 Coverage adequacy (floor)

| Metric | Role | Limits |
| --- | --- | --- |
| Line / statement coverage | Cheap CI floor | Ignores oracles |
| Branch / decision coverage | Stronger path floor | Still execution-only |
| Path / MC/DC | High-assurance subsets | Expensive; still not verification |
| Per-test / differential coverage | Which tests cover which lines; PR delta coverage | Presence of touch ≠ check |

**Suggested product use:** report corpus and per-module coverage when available (integration with `coverage.py` / pytest-cov), enforce **delta** floors on changed lines, never treat global % as proof of quality.

### 3.2 Oracle / assertion metrics (fast fake-test flags)

| Metric | Definition (sketch) | Use |
| --- | --- | --- |
| Assertion count / density | Asserts (and pytest `raises`/`warns`, unittest asserts, mock `assert_*`) per test or per LOC | Floor against empty tests |
| Oracle tier histogram | none / weak / strong per test | Primary fake-test dashboard |
| Asserts per covered production callable | Map tests → SUT symbols; ratio of strong oracles | Catches “covered but unchecked” |
| Exception-oracle ratio | Fraction of error-path tests with typed `raises` | Happy-path bias |
| State field coverage (ASE 2025) | Fraction of SUT object fields mentioned in oracles; static; correlates with mutation score | Oracle quality without full mutation |

**State field coverage** (Maguirre et al., ASE 2025): statically measures how much of an object’s declared state assertions inspect. Strong correlation with mutation score; actionable (“these fields never appear in oracles”) unlike raw survivor lists alone.

### 3.3 Mutation testing (gold standard for suite power)

| Concept | Meaning |
| --- | --- |
| Mutant | Small syntactic change (operator swap, constant tweak, statement delete, …) |
| Killed | Some test fails → suite detected the fault |
| Survived | Suite still green → gap in verification (or equivalent mutant) |
| Mutation score | killed / (killed + survived) [excluding timeouts/equivalent as configured] |

Evidence: superior to coverage for fault-detection assessment; used to guide LLM test generation (MutGen); security audits (Trail of Bits) found real bugs coverage missed. Python tooling: **mutmut** (ease of use, coverage-filtered mutate, stack-depth limits), **Cosmic Ray**, historically MutPy.

**Costs / caveats:**

- Runtime: suite_time × mutant_count (mitigate: covered-lines only, per-test targeting, severity tiers, changed-code `--since`, component scope).
- Equivalent mutants and low-value survivors need triage.
- **Mutation-driven generation peril:** agents can crystallize *buggy* behavior into tests that kill mutants. Prefer requirement-oriented oracles; treat survivors as questions, not automatic expected values (Trail of Bits).

**Suggested product use:** optional / offline campaign; ingest mutmut/Cosmic Ray JSON into the report; do not block every commit on full-corpus mutation. Gate critical packages or PR deltas when feasible.

### 3.4 Dynamic “does it touch the SUT?” gates

Pragma’s tier-2 idea: run the test under coverage instrumentation and ask whether production target lines actually executed. Catches tests that assert constants or only exercise mocks/stubs while claiming to test a module.

### 3.5 Process / gate metrics (anti-theater)

| Bad gate | Better gate |
| --- | --- |
| Test file present | Oracle-tier distribution on new/changed tests |
| Coverage % only | Coverage of changed lines **and** ≥1 strong oracle per touched behavioral symbol |
| Test count | Mutation score or survivor hotspots on critical paths |

---

## 4. Complementary suite design (anti-Goodhart)

Mirror the anti-spaghetti philosophy: gaming one axis should worsen another.

| Optimize this alone | How agents game it | Counterbalance |
| --- | --- | --- |
| Line coverage | Call every line, assert nothing | Oracle tier / assertion density |
| Assertion count | Many `assert True` / weak truthiness | Strong-oracle ratio; tautology scanner |
| Mutation score | Assert implementation accidents / freeze bugs | Human/requirement review; smell + semantic checks |
| Test count / files | Empty `test_*` stubs | Per-test oracle classification |
| Mock assert count | Mock the SUT | “Mocks unit under test” detection; SUT line touch |

**Positive target shape for tests:**

- **Coverage floor** on production paths that matter (esp. changed code).
- **Strong oracles** tied to observable behavior (values, boundaries, state, typed errors).
- **Localized tests** for complex cores (avoid incidental-only coverage of hotspots).
- **Mutation survivors** treated as debt on critical modules, not ignored green bars.

---

## 5. Proposed `py-code-metrics` test module

### 5.1 Goals

1. Analyze pytest/unittest-style trees the same way production code is analyzed today (discover → parse → metrics → JSON).
2. Maintain pressure for **adequate coverage** (report + suggested thresholds; optional integration with coverage data).
3. **Flag fake/useless tests** with deterministic, explainable codes (AST-first), suitable for agents and CI.
4. Leave room for **optional dynamic/mutation layers** without making the default path slow.

### 5.2 Non-goals (v1)

- Replacing coverage.py, mutmut, or falsegreen as full products.
- Semantic “is this the right expected value?” without an explicit opt-in LLM/skill layer.
- Enforcing global mutation score on every `py-code-metrics` invocation.

### 5.3 Architecture sketch

```
discover test files (test_*.py / *_test.py, unittest loaders)
    → parse AST
    → per-test extraction (name, fixtures, asserts, raises, mocks, skips)
    → oracle classification (none / weak / strong + smell codes)
    → optional: map imports/calls to production symbols (reuse resolve.py)
    → optional: merge coverage.json (line/branch + per-test if available)
    → optional: merge mutation report (survivors by location)
    → report JSON (tests[] + rollups + thresholds)
```

Fit with existing package layout:

| Piece | Location (proposed) |
| --- | --- |
| Models | `model.py` additions or `model_tests.py`: `TestCaseMetrics`, `TestModuleReport`, `TestOverallReport` |
| Discovery | Extend `discover.py` with `discover_tests(root)` or flag `--tests` |
| Oracle AST pass | `metrics/test_oracles.py` |
| Smells / fake codes | `metrics/test_smells.py` (codes aligned with rotten-green / falsegreen families) |
| Coverage ingest | `metrics/test_coverage.py` (read `coverage.json`, no runner required for v1) |
| Mutation ingest | `metrics/test_mutation.py` (read mutmut/Cosmic Ray export) |
| CLI | `py-code-metrics tests PATH` |
| Analyze orchestration | `analyze_tests_path` parallel to `analyze_path` |

### 5.4 Per-test metrics (v1 — static)

| Field | Meaning |
| --- | --- |
| `name`, `qualified_name`, `lineno`, `file` | Identity |
| `framework` | `pytest` \| `unittest` \| `unknown` |
| `assertion_count` | Explicit asserts + `pytest.raises`/`warns` as oracles |
| `oracle_tier` | `none` \| `weak` \| `strong` |
| `oracle_kinds` | e.g. `equality`, `identity`, `truthiness`, `raises`, `mock`, `approx` |
| `calls_production` | bool / list of resolved SUT qnames (best-effort) |
| `smell_codes` | e.g. `TAUTOLOGY`, `NO_ORACLE`, `WEAK_ORACLE`, `SWALLOWED_ERROR`, `MOCKS_SUT`, `EMPTY_BODY`, `SKIP_IN_EXCEPT` |
| `severity` | `high` \| `low` \| `info` (high ≈ block-worthy fake) |
| `markers` | skip/xfail/parametrize metadata |

### 5.5 Rollups (module + overall)

| Rollup | Purpose |
| --- | --- |
| `test_count`, `frac_oracle_none`, `frac_oracle_weak`, `frac_oracle_strong` | Suite oracle health |
| `mean_assertion_density` | Asserts per test (and per test LOC) |
| `high_severity_findings` | Count + list of fake-test flags |
| `tests_per_production_callable` / `unchecked_covered_callables` | When coverage+resolve available: covered but no strong oracle |
| `coverage_line`, `coverage_branch` | Ingested floors |
| `mutation_score`, `survivor_count` | Ingested gold-standard |
| `happy_path_bias` | Ratio of non-raises tests among tests that only hit except-heavy SUT (heuristic, later) |

### 5.6 Suggested thresholds (emitted, not necessarily exit codes)

| Signal | Suggest |
| --- | --- |
| New/changed behavioral tests with `oracle_tier=none` | Fail / high |
| `frac_oracle_none` on unit tests | Warn above ~5–10% (exempt marked smoke) |
| Strong-oracle share of unit tests | Prefer majority strong on non-smoke |
| Changed-line coverage | Project policy (e.g. ≥80–90% on diff) |
| Mutation score on critical packages | Aspirational bands; literature often treats ~85%+ as diminishing returns after triage |
| Tautology / always-true | Always high severity |

Exempt via markers/config: `smoke`, `import_ping`, `property`, `hypothesis`, explicit `# pcm:allow-no-oracle`.

### 5.7 Phased delivery

**P0 — Static fake-test detector — DONE**

- Discover/parse tests; classify oracles; emit smell codes; JSON rollups.
- No test execution → fast, agent-friendly, CI-cheap.
- Round 2 lesson: shipping P0 briefly raised corpus `max_v_poly` (`_classify_assert_test` → 23). Static test quality and production spaghetti pressure must land together—see the self-analysis gate in [`docs/metrics-suite-hardening.md`](docs/metrics-suite-hardening.md).

**P1 — Production linkage + coverage ingest — DONE**

- Resolve test imports/calls into corpus symbols (reuse `resolve.py`).
- Ingest `coverage.json`; flag “line covered only by none/weak oracle tests.”
- Delta mode: compare against git diff paths.

**P2 — Mutation / dynamic optional adapters — DONE**

- Ingest mutmut CICID / Cosmic Ray dump / PCM-normalized JSON; surface survivors next to static findings.
- Optional offline campaign docs (no default runner).
- Always-on static state-field coverage as a mutation-correlated proxy.

**P3 — Gates and agent UX**

- SARIF/JUnit output; pre-commit exit codes (high vs low).
- PR summary: “N new tests; M none-oracle; K survivors on touched lines.”
- Document anti-gaming explicitly (like `anti-spaghetti-research.md` §2.8–2.10).
- Include production complementary board (not only oracle tiers) so agents cannot green test rollups while worsening unpaid hotspots in the analyzer itself.

### 5.8 Interaction with existing production metrics

Production spaghetti metrics and test-quality metrics reinforce each other:

- High `v_poly` / nesting **cores** need **localized strong oracles** and mutation attention—not incidental coverage.
- ETSPA “expressive leaves” still need behavioral checks when they own domain rules.
- Do not encourage exploding test micro-files for coverage theater; prefer fewer strong tests (same anti-dust ethos).

**Lessons from self-iteration (Rounds 1–2)** that apply when evolving this module:

| Lesson | Implication for test-quality work |
| --- | --- |
| Complexity + unpaid reuse is the real hotspot | Prefer paid shared oracles (`F≥2`, `S≫0`) over splitting each classifier into F=1 shards for a greener local `v_poly` |
| “Reject all F=1” is too blunt | Named subproblems that cut a leaf’s cognitive cliff (e.g. `_combine_oracle_hits`) may stay F=1; reject **unpaid relocation** of branches, not vocabulary |
| Leaf pipeline steps look like ETSPA debt | `derive_smells` → thin leaf + `_smell_codes` is intentional leaf speech; do not optimize those steps for `sum_S` |
| Paid cores can be locally complex | `_classify_compare` at high `v_poly` with `S=+210` is healthy reuse—do not “fix” it for max-alone |
| Visitors / polymorphic dispatch are measurement artifacts | Oracle collectors that subclass `NodeVisitor` will show F=0 / bad LCOM4; do not split into class-per-node to game cohesion |
| Single-scalar chase fails | Keep oracle-tier dashboards *and* production means/`sum_S`/role-split fracs when reviewing a test-module change |

---

## 6. Worked examples (what the module should flag)

```python
# HIGH — no oracle (theater)
def test_add():
    add(2, 3)

# HIGH — tautology
def test_add():
    result = add(2, 3)
    assert True

# LOW/HIGH — weak oracle
def test_add():
    assert add(2, 3)

# CLEAN — strong oracle
def test_add():
    assert add(2, 3) == 5

# HIGH — swallowed failure
def test_parse():
    try:
        parse("{")
    except Exception:
        pass

# CLEAN — typed exception oracle
def test_parse_bad_json():
    with pytest.raises(ValueError, match="Expecting"):
        parse("{")
```

Coverage alone marks all of the first examples “green” if `add`/`parse` lines run.

---

## 7. Related tooling (do not reinvent blindly)

| Tool | Role vs this module |
| --- | --- |
| coverage.py / pytest-cov | Floor data source to ingest |
| mutmut / Cosmic Ray | Mutation campaigns; ingest reports |
| falsegreen | Overlapping AST false-positive codes—either integrate ideas or shell out; avoid contradictory code names |
| Pragma | Agent-hook AST + optional coverage-of-target |
| PyNose / tsDetect | Broader smell catalogs for P1+ maintainability |

This module’s niche inside `py-code-metrics`: **one JSON report** combining production structure metrics with test oracle health, so agents optimize a *counterbalancing* suite rather than coverage alone.

---

## 8. Open questions

1. **Default CLI:** separate `tests` subcommand vs `--include-tests` on the main analyzer?
2. **Hypothesis/property tests:** detection via decorator/import before oracle_tier scoring.
3. **Parametrize:** count as one test or N cases for density/tier rollups?
4. **Equivalent mutants / survivor triage:** human vs agent skill—out of band for v1.
5. **Exit codes:** mirror falsegreen (0 / warn / high) or stay report-only like current production metrics?

---

## 9. References (selected)

- Trail of Bits. *Mutation testing for the agentic era* (2026). Coverage as execution-not-verification; agent-oriented mutation tooling and generation risks. https://blog.trailofbits.com/2026/04/01/mutation-testing-for-the-agentic-era/
- Wang et al. *Mutation-Guided Unit Test Generation With a Large Language Model* (IEEE TSE, 2026; arXiv:2506.02954). Coverage vs mutation score gap (e.g. 100% coverage / ~4% mutation).
- Banik et al. (2026). Agent-authored test oracle study summarized in *Assertion-Free Test Theater* (AgentPatterns). https://agentpatterns.ai/anti-patterns/assertion-free-test-theater/ — 80.2% weak/no oracle; grade oracles not files.
- Maguirre et al. *State Field Coverage: A Metric for Oracle Quality* (ASE 2025). Static oracle metric correlating with mutation score.
- Delplanque et al.; Soares (rotten green tests). Basis for AST false-positive scanners.
- falsegreen (Vinicius Queiroz). Python/pytest AST false-positive catalog. https://github.com/vinicq/falsegreen
- Pragma. Multi-tier rejection of gamed AI-written tests. https://github.com/Joncik91/pragma
- mutmut / Cosmic Ray. Python mutation testing. https://mutmut.readthedocs.io/ · https://cosmic-ray.readthedocs.io/
- ICSME 2025. *Prioritizing Test Smells* (Python/PyNose; CP/FP + developer severity).
- Coulman; Williams. Tautological tests (implementation-mirroring oracles).
- Tuchyna. *Benchmarking of LLM generated unit-tests* (2025). Mutation-based benchmarking beyond coverage/assertion density.

---

## 10. Immediate next implementation step (when coding)

**P1 is done** (Round 4). **P2 is done** (Round 6): mutation ingest + state-field coverage. Next: **P3** — gates / SARIF / agent UX.

Production complementary-suite hardening from dogfood rounds (dispatch exemptions, unpaid hotspots, role-split boards, self-analysis gate) lives in [`docs/metrics-suite-hardening.md`](docs/metrics-suite-hardening.md).
