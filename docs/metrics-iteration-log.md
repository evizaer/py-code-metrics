# Metrics-guided iteration log

Target corpus: `src/py_code_metrics` (the tool analyzing itself).  
Snapshots: `/tmp/pcm-baseline.json` → after changeset 1 → `/tmp/pcm-after2.json`.

## Overall deltas

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

## Changeset 1 — flatten hotspots; extract only when reuse pays

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

## Changeset 2 — roll back unpaid F≤1 extracts

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

| Feedback | Priority |
| --- | --- |
| Exempt or specially score AST `NodeVisitor` dispatch (fan-in / LCOM4 / ETSPA) | High — recurring false debt |
| Hotspot predicate: high complexity **and** unpaid (F≤1 or S≤0), so paid cores are not “fixed” | High |
| Split dashboards: helper ETSPA/frac_F vs leaf CAR/nesting | Medium |
| Count of nest>3 / v_poly>15 callables, not only corpus max | Medium |
| After feature drops (like P0), require a self-analysis gate so new modules cannot raise `max_v_poly` unnoticed | Medium (process) |
| `v_poly` on pure aggregation functions overstates risk; optional “reduction-only” heuristic | Low |

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
