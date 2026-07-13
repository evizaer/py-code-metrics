# Metrics-guided iteration log

Target corpus: `src/py_code_metrics` (the tool analyzing itself).

**Purpose.** Document how well the complementary suite **guided** agent work:
volume and quality of edits made *because of* board/gate/hotspot signals, and
cases where metrics misled, wasted time, or pushed undesirable structure.
Board tables are evidence. This is **not** a feature changelog — verdicts that
only restate what shipped have drifted off-purpose (see skill
`metrics-dogfood-reflect`).


## Index — commits and feedback

| Round | Approx. commits / changeset | Snapshot | Notes |
| --- | --- | --- | --- |
| 1 | pre-`1446e9b` refactors (CS1–CS2) | `/tmp/pcm-baseline.json` → `/tmp/pcm-after2.json` | Flatten hotspots; roll back unpaid F=1 |
| 2 | `add5082` (P0 tests) + `1446e9b` (CS3) | `/tmp/pcm-self-before.json` → `/tmp/pcm-iter-final.json` | Oracle cleanup; paid extracts; stop rule |
| 3 | `5ee2701` (dashboard hardening) | `/tmp/pcm-round3-before.json` → `/tmp/pcm-round3-after.json` | Implements Round 2 product feedback |
| 4 | P1 SUT + coverage ingest | `/tmp/pcm-p1-before.json` → `/tmp/pcm-p1-after.json` | `test_sut` / `test_coverage` / `--delta`; gate PASS |

### Feedback tracker (Round 2 → status)

| ID | Feedback (R2) | Priority | Status | Addressed in |
| --- | --- | --- | --- | --- |
| F1 | Exempt AST `NodeVisitor` dispatch (fan-in / LCOM4 / ETSPA) | High | **done** | R3 — `dispatch_exempt`, `dispatch_class`, `lcom4_gate_exempt` |
| F2 | Hotspot = high complexity **and** unpaid | High | **done** | R3 — `overall.hotspots`, `unpaid` flag |
| F3 | Split dashboards: helper ETSPA vs leaf CAR/nesting | Medium | **done** | R3 — `etspa.helpers_cores`, `expression.leaves` |
| F4 | Counts of nest>3 / v_poly>15, not only max | Medium | **done** | R3 — `n_*` fields on complexity / module rollup |
| F5 | Self-analysis gate after feature drops | Medium | **done** | R3 — `scripts/compare_self_metrics.py` + README |
| F6 | Reduction-only / aggregation `v_poly` discount | Low | **done** | R3 — `reduction_like` annotation; hotspot sort ignores v_poly-alone when set |

---

## Round 1 — overall deltas

Snapshots: `/tmp/pcm-baseline.json` → after changeset 1 → `/tmp/pcm-after2.json`.

| Metric | Baseline | After CS1 | After CS2 (final) | Δ baseline→final |
| --- | ---: | ---: | ---: | ---: |
| `max_v_poly` | 43 | 19 | 19 | **-24** |
| `max_nesting` | 6 | 4 | 4 | **-2** |
| `mean_cyclomatic` | 4.887 | 4.280 | 4.386 | **-0.501** |
| `mean_cognitive` | 7.094 | 4.958 | 5.289 | **-1.805** |
| `sum_S` | -3581.6 | -3315.1 | -3189.1 | **+392.5** |
| `frac_S≤0` | 0.896 | 0.881 | 0.877 | **-0.019** |
| `frac_fan_in≤1` | 0.887 | 0.873 | 0.868 | **-0.019** |
| `mean_car` | 1.214 | 1.326 | 1.310 | **+0.096** |
| functions | 53 | 65 | 61 | +8 |
| roles core/leaf/helper | 5/39/62 | 7/53/58 | 7/52/55 | more core+leaf |
| import cycles | 0 | 0 | 0 | unchanged |
| visitor LCOM4 (`_ComplexityVisitor`) | 4 | 4 | 4 | **left alone** |

---

## Round 1 / Changeset 1 — flatten hotspots; extract only when reuse pays

**Files:** `resolve.py`, `roles.py`, `analyze.py`, `metrics/imports.py`, `metrics/v_poly.py`

**Intent (aligned with suite):**
- Cut nesting / cognitive / `v_poly` on god leaves (`resolve_call`, `_resolve_bases`, `classify_role`, `analyze_path`, `build_import_graph`).
- Prefer shared helpers with **fan-in ≥ 2 and positive `S`**, not Strategy/class-per-case splits.
- Turn `analyze_path` into a high-CAR orchestration leaf (pipeline of named steps).

**Key symbol moves:**

| Symbol | Before | After CS1 | Notes |
| --- | --- | --- | --- |
| `resolve.resolve_call` | v=43 n=5 cog=96 | v=12 n=3 cog=16 | Dead duplicate branches removed; dispatch flattened |
| `resolve._resolve_bases` | v=15 n=6 cog=57 | v=7 n=4 cog=19 | Guard-clause flatten + shared class lookup |
| `resolve._find_class_by_suffix` | — | F=3 **S=+137** core | Legitimate reuse amortization |
| `resolve._lookup_imported_callable` | — | F=2 **S=+62** | Legitimate reuse |
| `metrics.v_poly._ancestry` | nested F=0 | F=3 **S=+58** core | Hoisted nested fn → shared |
| `roles.classify_role` | v=19 cog=20 | v=13 cog=12 | Removed dead duplicate `return "leaf"` |
| `analyze.analyze_path` | v=22 n=3 cog=44 | v=6 n=0 cog=5 | Pipeline leaf |
| `imports.build_import_graph` | v=16 n=5 cog=41 | v=12 n=3 cog=21 | Less nesting |

**Also introduced (tension — see flags):** several F=1 pipeline/step helpers (`_score_callable`, `_module_report`, `_resolve_name_call`, …) with negative `S`. Function count rose 53→65.

---

## Round 1 / Changeset 2 — roll back unpaid F≤1 extracts

**Files:** `resolve.py`

**Intent (aligned with anti-fragmentation / ETSPA):**
- Inline helpers that were **F=1 and S≤0** from CS1 (`_resolve_name_call`, `_resolve_bound_attr`, `_annotation_name`, `_class_qname_from_annotation`).
- Keep positive-`S` cores (`_find_class_by_suffix`, `_lookup_imported_callable`, `_ancestry`, `_find_method_in_hierarchy`).

**Effect:**

| Symbol | After CS1 | After CS2 | Notes |
| --- | --- | --- | --- |
| `resolve.resolve_call` | v=12 n=3 cog=16 | v=19 n=4 cog=36 | Complexity rose again after inline — still ≪ baseline 43 |
| function count | 65 | 61 | Removed unpaid dust |
| `sum_S` | -3315.1 | -3189.1 | Better compression accounting |
| `frac_fan_in≤1` | 0.873 | 0.868 | Slightly healthier |

This is the suite working as designed: **CS1’s temporary `v_poly` win from extra F=1 shards was partially walked back** so net complexity wins stick without unpaid fragmentation.

---

## Flags — moves that fight the metrics’ stated purpose

### 1. Did **not** “fix” AST visitor LCOM4=4 / WMC (correct restraint)

`_ComplexityVisitor` (LCOM4=4, WMC=54, NOM=30) and `_ExpressionVisitor` (LCOM4=4) look like cohesion failures. They are not.

- Visit methods share little state by design; LCOM4 treats that as split candidates.
- Fan-in of `visit_*` is **0** because dispatch is polymorphic via `NodeVisitor.visit` — exactly the §2.8 “polymorphism as hidden switch” blind spot. Raw ETSPA/fan-in marks them as dead debt; they are not.
- Splitting into one class per node type would **game LCOM4** while raising `v_poly` / RFC-style cost (class-per-case). **Left unchanged on purpose.**

### 2. Analyze pipeline steps are F=1 by construction

`_score_callable`, `_module_report`, `_collect_call_costs`, `_rollup`, `_overall` each have F≈1 and S&lt;0. Under a strict “reject new helpers with F≤1” gate they fail.

**Why kept:** `analyze_path` is an intentional **expressive leaf** (high CAR, low nesting): it should *speak* named steps. Treating those steps as “combinator core” would be wrong; they are leaf vocabulary. Flag for humans: do not optimize them for ETSPA; judge the leaf’s readability instead.

### 3. CS1 briefly over-extracted resolve helpers

`_resolve_name_call` / `_resolve_bound_attr` improved `resolve_call` metrics by **relocating** branches into F=1 helpers (micro-fragmentation pressure). CS2 inlined them. If future edits re-extract for a greener `v_poly` on `resolve_call` alone, that is **against** §2.9–2.10 unless the extract reaches F≥2 or replaces duplication.

### 4. Role reclassification inflated “leaf” count

Simplifying `classify_role` marked more public module-level functions as `leaf` (39→52). That is closer to the §2.11 morphology, but it makes `frac` dashboards look better without proving expression quality. Prefer watching **leaf CAR/LMD** over leaf headcount.

### 5. Still-hot after iteration (not “fixed,” just improved)

| Symbol | Final | Comment |
| --- | --- | --- |
| `resolve.resolve_call` | v_poly=19 nest=4 cog=36 | Still above soft gate (~10–15); needs better static resolution design, not more dust |
| `analyze._overall` | v_poly=19 | Aggregation leaf; further split unlikely to pay ETSPA |
| `resolve._index_module_body` | v_poly=12 nest=2 | Recursive indexer; acceptable complexity for the job |
| Visitor methods | F=0 S≪0 | Measurement artifact — do not “optimize” |

### 6. What would have been **wrong** to do next

- Replace `resolve_call` branches with a Strategy hierarchy per callee shape → unpaid poly (`Δv(G)<0` while `Δv_poly≥0`).
- Split each `visit_*` into a tiny free function → NOM/WMC/RFC up, navigation cost up, fake CC wins.
- Maximize average ETSPA by deleting low-`S` visitors or pipeline steps → Goodhart on the scorer.
- Drive LCOM4→1 on visitors via artificial `self._touch` coupling → cosmetic cohesion.

---

## Verdict (Round 1)

Iteration **improved** the complementary suite targets that matter for this codebase’s real hotspots (local spaghetti in resolve/analyze/imports) **without** gaming class cohesion or polymorphism. Net: much lower max/`mean` complexity, better `sum_S`, fewer unpaid shards than the intermediate CS1 peak, import graph still acyclic. Remaining debt is concentrated in inherently awkward static-resolution and visitor-dispatch code — treat with design changes, not metric cosmetics.

---

## Round 2 — after test-quality P0 (oracle module + further self-iteration)

**Context.** Round 1 analyzed a ~61-function corpus. P0 test-quality work (`metrics/test_oracles.py`, `metrics/test_smells.py`, `analyze_tests.py`, models) grew the corpus to ~100+ functions and immediately reintroduced a **new max hotspot** (`_classify_assert_test` at `v_poly=23`). Round 2 covers (A) cleaning that regression, then (B) iterating until no good-faith metric win remained without a larger complementary cost.

Snapshots: `/tmp/pcm-self-before.json` (post-P0, pre-refactor) → oracle cleanup → `/tmp/pcm-iter-base.json` → CS3 paid extracts/flattens → `/tmp/pcm-iter-final.json`.

### Overall deltas (Round 2)

Corpus is not comparable 1:1 to Round 1 (new modules). Compare **within Round 2**:

| Metric | Post-P0 hotspot | After oracle cleanup | After CS3 (stop) | Δ post-P0→stop |
| --- | ---: | ---: | ---: | ---: |
| `max_v_poly` | 23 | 19 | **19** | **-4** |
| `max_nesting` | 4 | 4 | **4** (resolve nest 4→3) | 0 global / −1 local |
| `mean_cyclomatic` | 4.571 | 4.362 | **4.240** | **-0.331** |
| `mean_cognitive` | 5.202 | 4.713 | **4.503** | **-0.699** |
| `sum_S` | -3856.2 | -3850.4 | **-3824.2** | **+32.0** |
| `frac_S≤0` | 0.869 | 0.862 | 0.863 | −0.006 |
| `frac_fan_in≤1` | 0.815 | 0.799 | 0.800 | −0.015 |
| `mean_car` | 1.470 | 1.558 | 1.543 | +0.073 |
| functions | 102 | 109 | 110 | +8 |
| import cycles | 0 | 0 | 0 | unchanged |
| visitor LCOM4 | 4 | 4 | 4 | **left alone** |

### Changeset A — kill the P0 oracle hotspot (without Strategy dust)

**Files:** `metrics/test_oracles.py`, `metrics/test_smells.py` (resolve F=1 extract attempted then rolled back).

| Move | Guidance used | Result |
| --- | --- | --- |
| Table-drive unittest weak asserts; module-level `_call_oracle` / `_context_oracle` | Flatten god leaf; dispatch as leaf vocabulary | Removed method hotspots `v=18/15` |
| `_combine_oracle_hits` for BoolOp chains | Extract only the branch that dominated cognitive | `_classify_assert_test` **23→11** |
| Shared compare path kept at F=2 | ETSPA: keep when F≥2 and S≫0 | `_classify_compare` **S=+210**, F=2 |
| Tried `_resolve_named_receiver` | Same trap as Round 1 CS1 | F=1 S≪0 → **inlined** (suite working) |
| `derive_smells` → thin leaf + `_smell_codes` | Named step on expressive leaf | `derive_smells` **13→2** |

**False start:** inlining *all* F=1 shards brought `_classify_assert_test` back toward v≈18. Restoring only `_combine_oracle_hits` recovered the win — evidence that “reject all F=1” is too blunt; reject **unpaid relocation**, keep **named subproblems that cut a leaf’s cognitive cliff**.

### Changeset B (CS3) — paid sharing + in-place flatten; then stop

**Files:** `astutil.py` (new), `metrics/etspa.py`, `metrics/test_oracles.py`, `analyze.py`, `metrics/v_poly.py`, `metrics/cohesion.py`, `roles.py`, `resolve.py`.

| Move | Why “good faith” | Metric effect |
| --- | --- | --- |
| `astutil.leading_docstring` / `strip_docstring_body` | Dedup across etspa + test oracles | F=2/3, **S=+25 / +11** |
| `analyze._callable_stats` shared by `_rollup` + `_overall` | Real duplication, large body | F=2, **S=+164**; `_overall` **19→7**, `_rollup` **14→2** |
| Flatten `is_trivial_body` (guard `len!=1`) | Nesting without new symbols | nest **3→1**, cog **16→8** |
| Precompute ancestry sets in `build_override_index` | Same asymptotics, less nested recompute | cog 25→23 (small) |
| `combinations` for LCOM4 attr edges | Flatten double index loop | cog 29→27 (small) |
| Drop dead `classify_role` duplicate `return "helper"` | Dead code | v 13→12 |
| Collapse redundant class/mod candidate checks in `resolve_call` | In-place nest cut, no extract | nest **4→3**, cog 36→33; **v_poly still 19** |

**Rejected after probing (would fail the complementary suite):**

- Re-extract resolve branches → unpaid F=1 (Round 1 lesson).
- Split `_classify_compare` into identity/membership helpers → F=1 S≪0 (tried earlier; rolled back).
- Tiny `_mean` / `_count_roles` free functions → B too small for positive S even at F=2.
- Touch visitors / Tarjan nested `strongconnect` / `to_dict` methods → measurement artifacts or inherent algorithms.
- Strategy/class-per-case for resolve or oracle kinds → games CC, worsens `v_poly`/navigation.

### How well the metrics guided Round 2

**What worked**

1. **`max_v_poly` + cognitive as a paired alarm** correctly flagged the new oracle classifier as worse than legacy resolve debt — without them, P0 would have shipped a silent spaghetti regression.
2. **ETSPA / fan-in** again blocked Goodhart: the resolve extract looked like a local complexity win and failed F/S; inlining restored honesty.
3. **Positive-S F≥2 extracts** (`_callable_stats`, docstring helpers, `_classify_compare`) are exactly the §2.10 “reuse amortization” shape — metrics and readability agreed.
4. **Stopping rule was operational:** for every remaining top symbol, either (a) further improvement needs a *design* change (resolve), (b) the symbol is already a paid helper, or (c) the only local move is unpaid dust. That is a usable agent gate.

**Where guidance was noisy or incomplete**

1. **`v_poly` on aggregation leaves** (`_overall` before CS3) was high from *many independent reductions*, not deep spaghetti. Cognitive/nesting told the truth better; sharing aggregates fixed both. Feedback: consider a “flat fan-out of similar reductions” discount, or report **nesting-weighted** complexity beside raw `v_poly`.
2. **Fan-in 0 on `visit_*`** still marks visitors as ETSPA disasters. Round 1 already flagged this; Round 2 confirms — ship an explicit **dispatch-exempt** role or `fan_in` model for `NodeVisitor` patterns before agents “fix” them.
3. **Global `max_nesting=4` stuck** while `resolve_call` nest went 4→3. Max is a coarse dashboard; prefer **per-symbol gates** and “count of functions with nest>3”.
4. **`frac_fan_in≤1` / function count** still punish intentional leaf vocabulary (`_call_oracle`, analyze pipeline). Role=`leaf` helps narrative but dashboards still look “worse.” Feedback: report **frac_fan_in≤1 among role=helper only**, or ETSPA only for helpers/cores.
5. **`_classify_compare` at v=15 with S=+210** shows high local complexity can be *healthy* when reused. Optimizing it further for `v_poly` alone would destroy a paid core. Feedback: gate “refactor hotspot” on **(v_poly high) ∧ (S≤0 ∨ F≤1)**, not v_poly alone.
6. **Means improved while `max_v_poly` plateaued at 19.** Agents chasing only the max will thrash resolve; means + sum_S showed CS3 still paid. Keep the complementary board mandatory.

### Feedback for metric / product evolution

| ID | Feedback | Priority | Later |
| --- | --- | --- | --- |
| F1 | Exempt or specially score AST `NodeVisitor` dispatch (fan-in / LCOM4 / ETSPA) | High — recurring false debt | → **R3** |
| F2 | Hotspot predicate: high complexity **and** unpaid (F≤1 or S≤0), so paid cores are not “fixed” | High | → **R3** |
| F3 | Split dashboards: helper ETSPA/frac_F vs leaf CAR/nesting | Medium | → **R3** |
| F4 | Count of nest>3 / v_poly>15 callables, not only corpus max | Medium | → **R3** |
| F5 | After feature drops (like P0), require a self-analysis gate so new modules cannot raise `max_v_poly` unnoticed | Medium (process) | → **R3** |
| F6 | `v_poly` on pure aggregation functions overstates risk; optional “reduction-only” heuristic | Low | → **R3** |

### Still-hot after Round 2 (accept, don’t cosmetics)

| Symbol | Final | Why stop |
| --- | --- | --- |
| `resolve.resolve_call` | v=19 nest=3 cog=33 | Needs richer resolution design; extracts are unpaid |
| `compute_lcom4` | v=18 nest=3 cog=27 | Graph algorithm; further split is dust |
| `_classify_compare` | v=15 F=2 **S=+210** | Paid helper — leave |
| `build_override_index` | v=14 nest=3 | Hierarchy indexing; precompute done |
| `build_import_graph` | v=12 nest=3 | Already CS1-flattened |
| Visitors / Tarjan | F=0 or nested | Measurement / algorithm artifacts |

### Round 2 verdict

The suite **successfully** (1) caught P0’s oracle spaghetti, (2) steered cleanup toward paid sharing and in-place flattening, (3) rejected resolve micro-extraction again, and (4) provided a clear **stop** once remaining hotspots were either paid, inherent, or design-bound. Net vs post-P0: lower means, better `sum_S`, `max_v_poly` back to the Round 1 plateau (19), resolve nesting improved without fragmentation. Metrics worked best as a **counterbalancing board**; they work worst when a single scalar (`max_v_poly` or `frac_fan_in≤1`) is optimized in isolation — the same Goodhart lesson as Round 1, now validated on a larger corpus that includes the test-quality module.

---

## Round 3 — dashboard hardening (addresses F1–F6)

**Changeset:** implement `test-quality-metrics.md` §11 (product feedback from Round 2).  
**Commit:** `5ee2701`. Base HEAD at start: `1446e9b`.  
**Files:** `dashboard.py` (new), `model.py`, `analyze.py`, `scripts/compare_self_metrics.py`, `README.md`, tests/fixtures under `dashboard_pkg/`.  
**Snapshots:** `/tmp/pcm-round3-before.json` (post-R2 corpus, old report shape) → `/tmp/pcm-round3-after.json`.

### What shipped (by feedback ID)

| ID | Plain-language change | Verification |
| --- | --- | --- |
| F2 | Report `unpaid` + `overall.hotspots[]` — complexity above soft gates **and** (F≤1 or S≤0) | `_classify_compare` (v=15, S=+210) **not** in hotspots; `resolve_call` is #1 |
| F4 | `n_v_poly_gt_15`, `n_nesting_gt_3`, unpaid variants on complexity / module rollup | Present on after JSON (`n_unpaid_hotspots=11`, `n_nesting_gt_3=2`) |
| F3 | `etspa.helpers_cores` vs `expression.leaves` | helpers_cores `sum_S≈+335`, `frac_fan_in≤1≈0.48` vs global `frac≈0.80` |
| F1 | `dispatch_exempt` on `visit_*`; class `dispatch_class` / `lcom4_gate_exempt` | 42 exempt methods; none appear in `hotspots` |
| F6 | `reduction_like` flag; hotspot predicate ignores high `v_poly` alone when set | Annotates flat aggregators; deep unpaid leaves still flag |
| F5 | `scripts/compare_self_metrics.py` + README self-analysis section | Gate **PASS** before→after (`max_v_poly` held at 19) |

### Overall deltas (Round 3)

Comparable core board (same soft meaning as R2 final). New module `dashboard.py` adds callables — global `sum_S` dips as expected for a feature drop; **gated** helper board stays healthy.

| Metric | Before (R2 stop) | After R3 | Δ |
| --- | ---: | ---: | ---: |
| `max_v_poly` | 19 | **19** | 0 |
| `max_nesting` | 4 | 4 | 0 |
| `mean_cyclomatic` | 4.240 | 4.235 | ≈0 |
| `mean_cognitive` | 4.503 | 4.524 | +0.021 |
| `sum_S` (global) | -3824.2 | -3969.2 | −145 (new module dust) |
| `frac_S≤0` | 0.863 | 0.872 | +0.009 |
| `frac_fan_in≤1` (global) | 0.800 | 0.797 | −0.003 |
| `n_unpaid_hotspots` | — | **11** | new signal |
| `n_v_poly_gt_15` / unpaid | — | 3 / **2** | new signal |
| `n_nesting_gt_3` / unpaid | — | 2 / **2** | new signal |
| `helpers_cores.sum_S` | — | **+335** | new gated board |
| `helpers_cores.frac_fan_in≤1` | — | **0.475** | honest fragmentation |
| functions / methods | 110 / 65 | 121 / 66 | +11 / +1 |
| import cycles | 0 | 0 | unchanged |
| visitor LCOM4 | 4 | 4 | left alone (now `lcom4_gate_exempt`) |

### Hotspot board (after) — top unpaid

| Symbol | v_poly | nest | cog | Why listed |
| --- | ---: | ---: | ---: | --- |
| `resolve.resolve_call` | 19 | 3 | 33 | Unpaid leaf; design-bound |
| `compute_lcom4` | 18 | 3 | 27 | Graph algorithm |
| `build_override_index` | 14 | 3 | 23 | Hierarchy indexing |
| `analyze._module_report` | 14 | 2 | 19 | Unpaid leaf vocabulary |
| `resolve._index_module_body` | 12 | 2 | 25 | Recursive indexer |

**Excluded by design:** `_classify_compare` (paid), all `visit_*` (F1 exempt).

### Process note (F5)

```bash
uv run py-code-metrics src/py_code_metrics > /tmp/pcm-before.json
# edit
uv run py-code-metrics src/py_code_metrics > /tmp/pcm-after.json
uv run python scripts/compare_self_metrics.py /tmp/pcm-before.json /tmp/pcm-after.json
```

Fails on rising `n_unpaid_hotspots`, or rising `max_v_poly` when the new max symbol is unpaid and not `reduction_like`.

### Round 3 verdict

This round *was* the product response to Round 2’s feedback: unpaid hotspot predicate, dispatch exemptions, helpers_cores vs leaves, and count-based dashboards. Guidance quality should improve going forward — agents get pointed at unpaid debt and stop nagging visitors / paid cores. Accepted cost: global `sum_S` dipped from new dashboard helpers; ETSPA judgment moves to `helpers_cores`. Success of R3 is measured by whether later rounds thrash less on false debt (see R4+).

---

## Round 4 — P1 production linkage + coverage ingest

**Intent.** Ship test-quality P1: resolve test calls into production symbols, ingest `coverage.json` (floors + weak-oracle-covered lines when contexts present), optional `--delta` git path filter — without raising unpaid hotspots.

**Files:** `metrics/test_sut.py`, `metrics/test_coverage.py`, `metrics/test_delta.py`, `analyze_tests.py`, `cli.py`, `model.py`, fixtures under `tests/fixtures/sut_pkg/`.

**Snapshots:** `/tmp/pcm-p1-before.json` → `/tmp/pcm-p1-after.json`. Gate **PASS** (`n_unpaid_hotspots` 11→10; `max_v_poly` held at 19).

### What shipped

| Piece | Behavior |
| --- | --- |
| SUT linkage | `calls_production` via `resolve_call` on non-test callables |
| Coverage floors | `--coverage FILE` → `coverage_line` / `coverage_branch` |
| Contexts | `weak_oracle_covered_lines` when JSON has per-line contexts |
| Static fallback | `unchecked_covered_callables` (covered body ∩ no strong-oracle caller) |
| Delta | `--delta` filters modules/findings to git-changed `*.py` |

### Overall deltas (Round 4)

| Metric | Before (R3) | After R4 | Δ |
| --- | ---: | ---: | ---: |
| `max_v_poly` | 19 | **19** | 0 |
| `max_nesting` | 4 | 4 | 0 |
| `mean_cyclomatic` | 4.235 | 4.230 | ≈0 |
| `mean_cognitive` | 4.524 | 4.414 | −0.11 |
| `n_unpaid_hotspots` | 11 | **10** | −1 |
| `n_unpaid_v_poly_gt_15` | 2 | **1** | −1 |
| `helpers_cores.sum_S` | +335 | **+438** | +103 |
| `helpers_cores.frac_fan_in≤1` | 0.475 | 0.524 | +0.05 (new leaf helpers) |
| callables | 187 | 222 | +35 (feature modules) |

### Notable board effect

`resolve.resolve_call` left the unpaid hotspot list: `test_sut.resolve_production_calls` raises its fan-in so the design-bound resolver is **paid**. First coverage draft briefly added two unpaid hotspots (`_weak_oracle_covered_lines`, `_unchecked_covered_callables`); flattened into named pipeline steps (nest/cog under gates) before shipping.

### Round 4 verdict

**Guided well:** the unpaid-hotspot gate forced a mid-feature cleanup — first coverage draft briefly added two unpaid helpers; flattening them into pipeline steps was work the board demanded, not optional polish. Raising `resolve_call` fan-in via SUT linkage moved a long-standing design-bound symbol off the unpaid list for the right reason (amortization), which matches the F2 hotspot predicate better than another extract campaign would have.

**Risk / lesson:** a reader could treat “`resolve_call` left hotspots” as a complexity win; it was a **payment** win. Gate PASS alone would have hidden the draft thrash if the log only celebrated flat counts.

---

## Round 5 — Agent CLI views (2026-07-12)

**Intent.** Ship agent-facing subcommands (`board`, `hotspots`, `symbol`, `diff`, `snapshot`, compact `tests`) so mid-edit loops interrogate small JSON instead of full reports. Measure success as interrogated bytes.

**Files.** `compare.py`, `views.py`, `cli.py` rewrite; `scripts/measure_agent_payloads.py`; thin `compare_self_metrics.py` wrapper; skill + README + `docs/agent-cli-workflows.md`.

**Board.** New modules initially added unpaid hotspots (`compare.compare`, `views.find_symbol`, …). Paid extracts (`iter_callables` / gate helpers) restored **n_unpaid_hotspots = 10** (flat vs prior self-gate). Import graph still acyclic.

**Payload wins (measure harness):** W1 pass **423 B** (was ~510 KB naive); W1 fail **4 624 B**; W2 **4 201 B**; W3 findings **4 682 B** (was ~52 KB full tests).

**Metrics-caused moves.** New view helpers initially raised unpaid hotspots; paid extracts (`iter_callables` / gate helpers) were kept only after F/S looked honest — same anti-fragmentation loop as earlier rounds, applied to agent UX code. Payload measurement (not structural metrics) drove the “never open full snapshots” skill rule.

**Verdict.** Structural suite correctly blocked shipping the first draft of the CLI views as unpaid dust; complementary board stayed flat only after paid sharing. Separate success signal (interrogated bytes) was necessary — `n_unpaid_hotspots` alone would not have justified the agent-view work.

---

## Round 6 — P2 mutation ingest + state-field coverage (2026-07-12)

**Intent.** Complete P2: optional `--mutation` ingest (PCM v1 / mutmut CICID / Cosmic Ray dump) plus always-on static state-field coverage; surface survivors and uncovered fields in `tests` findings view; document offline campaigns.

**Files.** `metrics/test_mutation.py`, `metrics/test_state_fields.py`; wire-up in `analyze_tests.py`, `model.py`, `cli.py`, `views.py`; fixtures under `tests/fixtures/sut_pkg/` + `stateful_pkg/`; docs in README, `docs/metrics.md`, `test-quality-metrics.md`.

**Board (vs pre-P2 snapshot of `src/py_code_metrics`).**

| Signal | Before | After | Δ |
| --- | --- | --- | --- |
| `n_unpaid_hotspots` | 10 | **10** | 0 |
| unpaid `max_v_poly` | 19 | **19** | 0 |
| `max_nesting` | 4 | 4 | 0 |
| `helpers_cores.sum_S` | +1266 | **+1393** | +127 |

First draft raised unpaid hotspots 10→17 (`_apply_delta_filter`, several SFC helpers). Flattened into named pipeline steps / shared suffix resolvers until the unpaid hotspot set was unchanged.

### Round 6 verdict

**Guided well / volume:** the gate caught a real Goodhart path — first draft raised unpaid hotspots 10→17 (`_apply_delta_filter`, several SFC helpers). The suite forced a second pass of flatten / shared suffix resolvers until the unpaid set was unchanged; that cleanup volume is attributable to metrics, not to the P2 feature checklist.

**Quality:** ending flat (`n_unpaid_hotspots` 10→10, unpaid max still 19) with higher `helpers_cores.sum_S` is the desired shape for a feature drop: new paid sharing, no new unpaid spaghetti.

**Mislead risk:** a gate that only checked `max_v_poly` would have PASS’d the dusty first draft (max held at 19 while unpaid count spiked). Unpaid-hotspot count remains the higher-signal primary fail for feature modules.

