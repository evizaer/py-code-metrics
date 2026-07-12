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

## Verdict

Iteration **improved** the complementary suite targets that matter for this codebase’s real hotspots (local spaghetti in resolve/analyze/imports) **without** gaming class cohesion or polymorphism. Net: much lower max/`mean` complexity, better `sum_S`, fewer unpaid shards than the intermediate CS1 peak, import graph still acyclic. Remaining debt is concentrated in inherently awkward static-resolution and visitor-dispatch code — treat with design changes, not metric cosmetics.
