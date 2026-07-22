# Implemented metrics

This document describes every metric currently emitted by `py-code-metrics`: what a value means in practice, why it is in the suite, and which other signals it is meant to counter-balance.

Two report modes:

| Mode | CLI | Focus |
| --- | --- | --- |
| Structural | `py-code-metrics analyze <path>` | Anti-spaghetti shape: complexity, reuse, DOU, expression style, cohesion, imports |
| Test quality | `py-code-metrics tests <path>` | Oracle strength, smells, SUT linkage, optional coverage floors |

The design premise is Goodhart pressure: optimizing any single axis invites a cheat that another axis should make worse. Soft thresholds appear under `thresholds` in JSON; they inform hotspot predicates and dashboards but are not exit codes yet.

---

## How to read the complementary board

```text
Local complexity (cyclomatic, nesting, cognitive)
        ↕ tension ↕
Reuse accounting (fan-in, S / ETSPA)          ← stops “shatter into dust”
        ↕ tension ↕
Polymorphic expansion (v_poly)               ← stops “Strategy as hidden switch”
        ↕ tension ↕
DOU (untyped structured mappings)            ← stops “simplify” via dict bags
        ↕ tension ↕
Expression shape (CAR, LMD) on leaves        ← encourages orchestration over mutation
        ↕ tension ↕
Class cohesion (LCOM4, WMC, NOM)             ← stops god / unrelated bags
        ↕ tension ↕
Import cycles                                ← stops package spaghetti
```

Positive target shape for production code: **high-fan-in, simple cores** plus **expressive, low-mutation leaves** that call those cores. For tests: **coverage as a floor**, **strong oracles as the verification signal**.

---

# Structural metrics (default mode)

## Function / method — local complexity

### `cyclomatic`

**What it means.** McCabe-style cyclomatic complexity \(v(G)\): roughly \(1\) plus decision points in the callable’s control-flow graph (`if`/`elif`, loops, `except`, boolean short-circuit operators, etc.). Higher values mean more independent paths through the body—more cases to reason about and to test.

**Why include it.** Classic, cheap signal of local path explosion and defect risk. Gives a shared language with tools like Radon / flake8-mccabe.

**Counter-balances.** Alone it is gamed by splitting methods or by replacing branches with polymorphism. Pair with **`v_poly`**, **`max_nesting`**, **`cognitive`**, and reuse metrics (**`S`**, **`fan_in_ext`**). Do not treat a drop in `cyclomatic` as a win if `v_poly` or unpaid fragmentation rose.

### `cognitive`

**What it means.** Sonar-style cognitive complexity: increments for breaks in linear reading flow, with **extra cost for nesting**. A flat chain of peers is cheaper than the same path count nested deeply.

**Why include it.** Separates “readable decision table” from “nested spaghetti” when path count alone cannot. Nesting penalty is the primary anti-spaghetti lever for agents deciding edit vs extract.

**Counter-balances.** Same scope as cyclomatic—does not see polymorphic dispatch. Pair with **`v_poly`**. Does not stop micro-fragmentation; pair with **`S`** / **`frac_fan_in_le_1`**.

### `max_nesting`

**What it means.** Deepest stack of control-flow constructs in the function body (nesting depth of `if` / loops / `try` / etc.). Soft gate default: ≤ 3.

**Why include it.** Nesting depth is an independent readability failure even when cyclomatic is only moderate. Deep nesting is what humans and agents struggle to hold in working memory.

**Counter-balances.** Flattening via early returns is good; flattening by extracting unpaid helpers is not—check **`unpaid`** / **`S`**. High flat branching may keep nesting low while **`v_poly`** or **`cyclomatic`** stays high (`reduction_like` may apply).

### `params`

**What it means.** Effective parameter count. For instance methods, `self` is excluded; for classmethods, `cls` is excluded. Soft gate default: ≤ 5.

**Why include it.** Blocks “just add another flag” growth and pushes toward narrower functions or parameter objects.

**Counter-balances.** Wide APIs can hide behind “simple” bodies. Pair with cohesion on the owning type and unpaid/hotspot complexity—not with a per-function length cap. Does not measure reuse—wide but highly reused cores may still be legitimate.

### `statements`

**What it means.** Count of statements walked in the function body (complexity visitor). Reported on each callable for context; **not** a soft threshold and **not** part of the hotspot predicate.

**Why include it.** Useful when reading a symbol (how large is this body?) alongside nesting / cognitive / `v_poly`. Length alone is not a readability verdict.

**Counter-balances.** Do **not** extract or shard to shrink `statements` (or tokens) when complexity gates are already fine—that is the unpaid-fragmentation failure mode. Prefer **`max_nesting`**, **`cognitive`**, **`v_poly`**, and **`unpaid`/`S`** as the split signals.

### `returns`

**What it means.** Number of `return` statements in the body.

**Why include it.** Multiple exits can signal tangled control flow (alongside nesting). Reported as a size/shape signal; not currently a hard gate.

**Counter-balances.** Guard-clause early returns *reduce* nesting—do not treat high `returns` alone as spaghetti if **`max_nesting`** and **`cognitive`** improved.

---

## Function / method — polymorphism-aware complexity

### `v_poly`

**What it means.**

\[
v_{\mathrm{poly}}(m) = v(G_m) + \sum_{c \in \text{poly calls in } m}(\lvert\mathrm{targets}(c)\rvert - 1)
\]

At each resolvable polymorphic call site, override sets from corpus inheritance expand the call into an implicit multi-way branch. Soft bands: ≤ 10 (strict) / ≤ 15 (lenient).

**Why include it.** Plain McCabe does not charge for Strategy / override families that relocate `if`/`switch` into type dispatch. Agents optimizing only `cyclomatic` will invent class-per-case hierarchies. `v_poly` closes that cheat by charging hidden decision breadth on the caller.

**Counter-balances.** **`cyclomatic`** / **`cognitive`** (local readability without dispatch). High flat `v_poly` with shallow nesting may be **`reduction_like`** (aggregation), not deep spaghetti—hotspot logic discounts that case. Does not stop unpaid extracts; pair with **`S`**.

---

## Function / method — call graph and reuse (ETSPA)

### `fan_in` / `fan_in_ext` / `fan_in_rec`

**What they mean.** Static call-site counts resolving to this callable within the analyzed corpus:

| Field | Meaning |
| --- | --- |
| `fan_in` | All call sites (external + recursive) |
| `fan_in_ext` | Call sites whose caller is not this callable |
| `fan_in_rec` | Self-recursive call sites |

**Why include them.** Fan-in is the strongest local signal of real reuse. High external fan-in marks combinator/core material; fan-in ≤ 1 marks one-shot helpers or leaves.

**Counter-balances.** Complexity caps that reward tiny methods. ETSPA uses **`fan_in_ext`** as \(F\). Role classification uses fan-in to separate **core** vs **helper** vs **leaf**. High fan-in alone is not enough if the body is a god method—still gate with nesting / `v_poly`.

### `body_tokens` / `header_tokens` / `mean_call_cost`

**What they mean.** Token inputs to ETSPA (comments/newlines/indent stripped):

| Field | Meaning |
| --- | --- |
| `body_tokens` (\(B\)) | Implementation tokens (docstring stripped) |
| `header_tokens` (\(H\)) | Signature + decorators through the colon |
| `mean_call_cost` (\(C\)) | Mean token cost of resolved call sites to this symbol; default prior \(C = 3\) if none measured |

**Why include them.** Make abstraction cost explicit: headers and call sites are not free relative to inlining.

**Counter-balances.** Naïve “minimize tokens per function.” These feed **`S`**; they are inputs, not objectives by themselves.

### `S` / `etspa`

**What they mean.** Effective tokens saved versus inlining the body at every external call site (\(U = 1\), so `etspa == S`):

\[
S = (F - 1)\,B - H - F\cdot C
\quad\text{with } F = \mathtt{fan\_in\_ext}
\]

- \(S > 0\): reuse more than pays for the abstraction tax.
- \(S \le 0\): extract does not amortize (typical of fan-in-1 helpers or tiny bodies).
- Trivial bodies (`pass` / `...` / constant `return`) force \(S \le 0\).

**Why include them.** Complexity caps create pressure to shatter readable functions into dust. ETSPA asks whether the call graph *pays you back*. Module/overall **`sum_S`** and **`frac_S_le_0`** measure compression health of a scope.

**Counter-balances.** Per-method CC / LOC / nesting wins from unpaid extracts. Leaves with low \(F\) may legitimately have negative \(S\)—judge those with **`car`** / role **`leaf`**, not as failed cores. Prefer **`overall.etspa.helpers_cores`** for fragmentation gates (excludes leaves).

### `unpaid`

**What it means.** Boolean: `fan_in_ext ≤ 1` or `S ≤ 0`. Marks abstractions that do not earn their keep as shared helpers.

**Why include it.** Turns ETSPA/fan-in into a hotspot predicate: complex *and* unpaid is debt; complex *and* paid (high \(S\)) may be a legitimate core.

**Counter-balances.** Raw complexity hotspots that would punish highly reused libraries. Leaves are often “unpaid” by construction—use role-split boards.

---

## Function / method — expression shape

### `car` (call-to-assign ratio)

**What it means.**

\[
\mathrm{CAR} = \frac{\text{call count}}{1 + \text{assign count}}
\]

Assignments include `=`, annotated assigns with values, and augmented assigns. Higher CAR ≈ more “speaking in calls” vs staging through locals.

**Why include it.** Encourages expressive leaves and pipelines over imperative scratch-pad style. Target morphology: leaves orchestrate; cores compute.

**Counter-balances.** ETSPA pressure that might otherwise demand every leaf become a reused helper. Prefer **`overall.expression.leaves`** for orchestration quality. High CAR with deep nesting is still spaghetti—pair with nesting/cognitive.

### `lmd` (local mutation density)

**What it means.**

\[
\mathrm{LMD} = \frac{\text{local/param stores (+ mutating methods on locals)}}{\text{body tokens}}
\]

(when \(B > 0\); else 0). Lower is more expression-oriented.

**Why include it.** Captures “accumulator / scratch local” style that CAR alone may miss when calls are present but state is still heavily mutated.

**Counter-balances.** Call-count vanity (many calls that still thrash locals). Complements **`car`** on leaves.

### `cvr` (combinator vocabulary rate)

**What it means.** Fraction of calls + comprehensions that hit a default combinator allowlist (`map`, `filter`, `reduce`, `any`, `all`, comprehensions, itertools-style names, etc.):

\[
\mathrm{CVR} = \frac{\text{combinator hits}}{\text{calls} + \text{comprehensions}}
\]

**Why include it.** Soft positive signal for expression-oriented vocabulary. Not a hard quality proof—domain APIs matter more than stdlib names.

**Counter-balances.** Weak alone; use as texture beside **`car`** / **`lmd`**, not as a primary gate.

### Related counts

`call_count`, `assign_count`, `local_stores`, `comprehension_count` — raw numerators for the ratios above; useful when diagnosing a surprising CAR/LMD.

---

## Function / method — roles and annotations

### `role`

**What it means.** One of:

| Role | Typical meaning |
| --- | --- |
| `core` | External fan-in ≥ 3, not an obvious entrypoint — reuse center |
| `leaf` | Entrypoint (`main`/`run`/…), dunder, public module-level function, or low-F high-CAR orchestration |
| `helper` | Everything else — private / low-reuse abstraction |

**Why include it.** The same number means different things on a core vs a leaf. Dashboards split ETSPA (helpers+cores) from expression (leaves) so unpaid leaves are not scored as failed libraries.

**Counter-balances.** Global averages that mix entrypoints with shared utilities (`frac_S_le_0` over everything is noisy—prefer `helpers_cores`).

### `reduction_like`

**What it means.** High `v_poly` (≥ 8) with shallow nesting (≤ 1) and cognitive not much above branch count—flat aggregation / multi-way reduction, not deep spaghetti.

**Why include it.** Avoids hotspot false positives on wide-but-flat dispatch tables.

**Counter-balances.** **`v_poly`** alone as a hotspot trigger; `is_hotspot` ignores reduction-like when only `v_poly` exceeds the lenient gate.

### `n_dou_sites` / `dou_sites` (DOU)

**What it means.** Count (and detail list) of **L1 record-annotation** sites on the callable: parameters or return types that are untyped structured mappings (`dict[str, Any]`, bare `dict`, `Mapping[str, Any]`, `list[dict[…]]`, optional wrappers). Homogeneous indexes (`dict[str, int]`, `dict[str, MyDc]`) do **not** count. Wire-then-coerce (param only passed into a dataclass / `from_dict` / `model_validate`) is exempt. Each site carries an **impact** object: `fan_out_sites`, `key_vocab_size`, `cross_module`, `on_public_api`.

**Why include it.** Propagates “prefer dataclasses for structured data” via the board on **any** analyzed tree—same pressure as unpaid hotspots for anti-spaghetti—without TypedDict as the recommended fix.

**Counter-balances.** Unpaid fragmentation (do not split one bag into many F=1 dict builders); one-field wrappers that still hold `dict[str, Any]`; treating DOU as purity (PIF stays a separate axis).

---

## Class metrics

### `lcom4`

**What it means.** Hitz–Montazeri lack of cohesion: number of connected components in the undirected graph of methods, where edges exist if two methods share an instance attribute or one calls the other on `self`. Ideal cohesive class: **1**. Soft gate: ≤ 1.

**Why include it.** Catches god classes and bags of unrelated responsibilities that per-method CC will miss.

**Counter-balances.** Method-level complexity wins that leave the type incoherent. Weak against cohesive micro-method dust—pair with **NOM** / **WMC** / **S**. Visitor `visit_*` method graphs often look “incohesive” by design—do not split them solely to green LCOM4.

### `wmc`

**What it means.** Weighted Methods per Class: sum of method cyclomatic complexities.

**Why include it.** Class-level complexity budget. Sharding one method into N CC≈1 methods still raises WMC.

**Counter-balances.** Per-method CC minimization via fragmentation.

### `nom`

**What it means.** Number of methods on the class.

**Why include it.** Direct cardinality check against method proliferation.

**Counter-balances.** Same fragmentation cheat as WMC; together they resist “many tiny methods” refactors that look clean locally.

---

## Module / overall rollups

### Complexity board (`overall.complexity` / module `metrics`)

| Field | Meaning |
| --- | --- |
| `max_v_poly` / `max_nesting` | Worst outliers in the scope |
| `mean_cyclomatic` / `mean_cognitive` | Averages (hide power-law tails—use with counts) |
| `n_v_poly_gt_15` / `n_nesting_gt_3` | How many callables exceed soft gates |
| `n_unpaid_v_poly_gt_15` / `n_unpaid_nesting_gt_3` / `n_unpaid_hotspots` | Same, restricted to unpaid debt |

**Why include them.** Progress when corpus max is stuck; unpaid variants track *actionable* debt rather than paid library cores.

**Counter-balances.** Celebrating mean drops while unpaid hotspot count rises.

### ETSPA board (`overall.etspa`)

| Field | Meaning |
| --- | --- |
| `sum_S` | Total compression accounting |
| `frac_S_le_0` | Share of callables with non-positive \(S\) |
| `frac_fan_in_le_1` | Share with external fan-in ≤ 1 |
| `helpers_cores` | Same stats on helpers+cores only — **prefer for fragmentation gates** |

**Why include them.** Scope-level anti-fragmentation. Global fracs mix leaves; the note on the report says to prefer `helpers_cores`.

### Expression board (`overall.expression`)

| Field | Meaning |
| --- | --- |
| `mean_car` / `mean_lmd` / `mean_cvr` | Corpus-wide expression texture |
| `leaves` | CAR / LMD / nesting / cognitive for `role=leaf` — **prefer for orchestration quality** |

### `overall.hotspots`

**What it means.** List of callables that are **unpaid** and above soft complexity gates (nesting, cognitive, or non-reduction-like `v_poly`). Paid high-\(S\) cores are excluded.

**Why include it.** Action queue for refactoring: complexity that has not earned reuse.

**Counter-balances.** Ranking by raw `v_poly` alone (which would flag reduction leaves and paid cores).

### DOU board (`overall.dou` / `overall.dou_hotspots` / module `n_dou_sites`)

| Field | Meaning |
| --- | --- |
| `n_dou_sites` | Total L1 record-annotation sites in scope |
| `n_dou_callables` | Callables with at least one DOU site |
| `dou_hotspots[]` | Ranked candidates with annotation snippet + **impact** (`fan_out_sites`, `key_vocab_size`, `cross_module`, `on_public_api`) |

**Why include them.** Agent action queue for introducing dataclasses; impact ranking beats random bag conversion. CLI: `py-code-metrics dou`.

**Counter-balances.** Whole-package DOU as a hard gate — **`diff` gates `n_dou_sites_on_delta` only** (changed paths via snapshot inference or `--paths` / `--delta`). Homogeneous indexes and wire coerce stay green.

### Import graph (`overall.imports` / per-module `imports`)

| Field | Meaning |
| --- | --- |
| `edge_count` | Corpus-local import edges |
| `cycle_count` / `cycles` | Tarjan SCCs with size > 1 |
| `scc_id` (module) | Which SCC the module belongs to |

**Why include them.** Package-scale spaghetti: mutual imports and layer tangles that function metrics cannot see.

**Counter-balances.** Local cleanup that secretly introduces cyclic packages. Method-only splits inside one file evade this—still need cohesion / NOM.

### Module depth board (`overall.module_depth` / per-module `depth`)

Module-native depth and reuse signals (not averages of callable CC). See `[module-metrics-research.md](module-metrics-research.md)`.

| Field | Meaning |
| --- | --- |
| `mdi` | Module Depth Index: \(F_{\mathrm{impl}} / (1 + C_{\mathrm{iface}})\) — body tokens behind public entrypoints (helpers counted once) over formal interface cost |
| `piw` | Public Interface Width: \(N_{\mathrm{exports}} + \overline{n_{\mathrm{params}}} + N_{\mathrm{public\ types}}\) (α=β=1) |
| `ptr` | Pass-Through Rate: fraction of public callables that are thin signature-echo wrappers to another module/class |
| `ca` / `ce` / `instability` / `hub_risk` | Import-graph afferent / efferent coupling, \(I = Ce/(Ca+Ce)\), hub risk \(Ca \times Ce\) |
| `f_impl` / `c_iface` | Raw numerator / denominator inputs to MDI |
| `sum_public_S` | \(\sum \max(S,0)\) on public symbols (reuse check; not used in MDI) |
| `role` | `library` vs `leaf_script` (tiny PIW — don't demand library depth) |
| `sum_piw` / `n_low_mdi` (overall) | Corpus public surface and count of library modules with MDI below soft threshold (anti file-split gaming) |

**Why include them.** Function gates can green while a module stays a wide shallow API, a pass-through layer, or a popular hub. Ousterhout depth and Muratori “false tier” detection need module-scale signals.

**Counter-balances.** Raising MDI by hiding needed exports (pair with Ca). Padding private dead code (reachability later). Splitting files to lower per-file PIW (watch `sum_piw` / `n_low_mdi`). Inserting pass-through packages to “add layers” (PTR↑).

CLI: `py-code-metrics module-board`; corpus slice also on `board` under `module_depth`.

### Role histogram (`overall.roles` / module `roles`)

Counts of `core` / `leaf` / `helper`. Useful for seeing whether a change grew unpaid helpers vs reusable cores.

---

# Test-quality metrics (`--tests`)

Pass the **project root** (not only `tests/`) so production linkage can resolve. Optional `--coverage coverage.json`; contexts need `coverage json --show-contexts` (e.g. after `pytest --cov-context=test`). Optional `--delta` restricts findings to git-changed `*.py` paths.

## Per-test signals

### `oracle_tier`

**What it means.** Best real oracle in the test: `none` / `weak` / `strong`. Tautologies do not count as verification.

| Tier | Typical patterns |
| --- | --- |
| `none` | No assert / raises / mock assert (or only tautologies) |
| `weak` | Truthiness, non-null, membership, identity-only, etc. |
| `strong` | Equality to expected values, typed `raises`, richer comparisons, approx, etc. |

**Why include it.** Coverage and “test file exists” gates incentivize assertion-free or weak smoke stubs. Tier is the primary fake-test dashboard signal.

**Counter-balances.** **`coverage_line` / `coverage_branch`** (execution without verification). Assertion *count* without tier (many weak asserts).

### `oracle_kinds`

**What it means.** Deduplicated kinds of oracles found (`equality`, `truthiness`, `raises`, `mock`, `tautology`, …).

**Why include it.** Explains *why* a tier was assigned; helps review without re-reading the AST.

### `assertion_count`

**What it means.** Count of non-tautology oracle hits (asserts, `pytest.raises` / warns, unittest asserts, mock `assert_*`, …).

**Why include it.** Floor against empty tests; feeds **`mean_assertion_density`**.

**Counter-balances.** Inflating count with tautologies or weak checks—tier and smell codes catch that.

### `smell_codes` / `severity`

**What they mean.** Static fake-test / rotten-green patterns and a severity:

| Code | Severity (typical) | Meaning |
| --- | --- | --- |
| `NO_ORACLE` | high | No real oracle |
| `TAUTOLOGY` | high | Always-true assert |
| `SWALLOWED_ERROR` | high | Broad except that hides failures |
| `SKIP_IN_EXCEPT` | high | Skip/xfail inside except |
| `EMPTY_BODY` | high | Empty / non-running body |
| `WEAK_ORACLE` | low | Only weak-tier checks |

`severity` is `high` / `low` / `info`. Exempt tests (`smoke`, `import_ping`, `property`, `hypothesis` markers, or `pcm:allow-no-oracle`) still get codes but severity `info`.

**Why include them.** Parser-provable theater that green bars hide. Prioritize oracle absence/weakness over maintainability smells.

**Counter-balances.** Coverage % and test-count gates.

### `calls_production`

**What it means.** Sorted unique production callable qualified names statically invoked by the test (corpus resolve; test modules excluded as callees).

**Why include it.** Links oracles to SUT symbols. Enables **unchecked covered callables**: covered production code with no strong-oracle static caller.

**Counter-balances.** Tests that only exercise mocks/constants while claiming to cover a module; coverage without localized verification.

### `markers` / `exempt` / `framework`

Pytest marks, exemption flag, and framework hint (`pytest` / `unittest` / `unknown`). Support legitimate smoke/property tests without auto-failing them.

---

## Test module / overall rollups

| Field | Meaning |
| --- | --- |
| `frac_oracle_none` / `_weak` / `_strong` | Oracle-tier distribution |
| `mean_assertion_density` | Mean non-tautology asserts per test |
| `high_severity_count` / `high_severity_findings` | Action queue for fake-test debt |
| `oracle_histogram` | Counts by tier |

**Why include them.** Suite-level health beyond a single failing test. Soft warn when `frac_oracle_none` is high (threshold field `frac_oracle_none_warn`, default 0.10).

**Counter-balances.** Rising coverage with a worsening none/weak mix.

### Coverage floors (with `--coverage`)

| Field | Meaning |
| --- | --- |
| `coverage_line` / `coverage_branch` | Percent floors from coverage.py JSON (overall and per test module when available) |

**Why include them.** Necessary execution adequacy—especially on changed code—but never sufficient as proof of quality.

**Counter-balances.** Oracle tiers, smells, and unchecked/weak-oracle findings. Agents optimizing coverage alone emit call-everything assert-nothing suites.

### `weak_oracle_covered_lines` (needs contexts)

**What it means.** Production lines whose run-phase contexts map only to none/weak-oracle tests (not strong). Each finding includes file, line, and contributing test names.

**Why include it.** Pins “covered but barely checked” to concrete lines when pytest-cov contexts are present.

**Counter-balances.** Line coverage % that looks healthy while oracles are weak.

### `unchecked_covered_callables`

**What it means.** Production callables whose body lines were executed under coverage, yet no non-exempt **strong**-oracle test statically calls them.

**Why include it.** Catches incidental or smoke-only coverage of behavioral symbols.

**Counter-balances.** Coverage floors and weak/none tests that merely import or touch a function.

### `mutation_score` / `survivors` (optional `--mutation`)

**What it means.** Ingested mutation campaign results. Supported shapes: PCM `py-code-metrics.mutation.v1` JSON, mutmut `mutmut-cicd-stats.json` (score-only), Cosmic Ray `dump` NDJSON/array (survivors with locations). Score is `killed / (killed + survived)`; timeouts/skipped excluded. Survivors may carry `overlap_flags` joining P1 coverage signals.

**Why include it.** Gold-standard fault-detection power without embedding a mutation runner in the default path.

**Counter-balances.** Coverage % and assertion counts that look healthy while mutants survive.

### `mean_state_field_coverage` / `uncovered_state_fields` (always-on)

**What it means.** Static Maguirre-style state-field coverage: share of SUT class field labels (plus iterable `field+` labels) referenced in oracle expressions, including one-hop reads inside production methods called from asserts. Reports uncovered labels for oracle improvement.

**Why include it.** Mutation-correlated proxy that is cheap, static, and actionable when full mutation is offline.

**Counter-balances.** Strong-looking equality asserts that only check return values and never inspect object state.

---

## Soft thresholds (emitted, not exit codes)

**Structural defaults** (`Thresholds`):

| Key | Default | Used for |
| --- | --- | --- |
| `nesting_depth` | 3 | Hotspot / counts |
| `params` | 5 | Reported guidance |
| `v_poly_strict` / `v_poly_lenient` | 10 / 15 | Guidance / hotspot |
| `cognitive` | 15 | Hotspot |
| `lcom4_max` | 1 | Guidance (skip dispatch classes) |

Per-callable `statements` / `body_tokens` / `header_tokens` remain in the report JSON as informational fields only (LTR: no per-function length threshold).

**Test defaults:** `frac_oracle_none_warn`, smell severities, `prefer_strong_majority`, `mutation_score_warn` (0.85), `unchecked_state_field`.

Self-analysis gate (`py-code-metrics diff`) fails if `n_unpaid_hotspots`, unpaid `max_v_poly`, or `n_dou_sites_on_delta` rises between snapshots—see README and `docs/metrics-iteration-log.md`.

---

## Not yet implemented

Deferred from research notes (not in the current report): TCC, CBO, ATFD, God Class, RFC′, Martin package metrics, Halstead/ABC, layer contracts, PIF, DOU P2 half-shell attrs / L2 dict literals, and enforced CI exit codes beyond the optional self-compare script (P3).

DOU **P0+P1** (L1 annotations + impact + views; `diff` fails on rising `n_dou_sites_on_delta`) is implemented — see above and [`dataclass-structure-enforcement.md`](dataclass-structure-enforcement.md).
