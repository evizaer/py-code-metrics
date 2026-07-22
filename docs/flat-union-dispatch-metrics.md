# Flat discriminated-union dispatch and the metrics board

**Purpose.** Decide how `py-code-metrics` should treat **easy-to-understand,
exhaustive handling of a closed set of cases** (discriminated unions, `match`
tables, visitor arms, flat `if`/`elif` reductions) so the board does not push
agents to fragment healthy code.

**Status.** Open research (2026-07-20). Follows removal of hardcoded
`ast.NodeVisitor` exemptions — those exemptions were project-shaped and are
gone; this doc asks for a **general** complementary signal instead.

**Companions.** [`metrics.md`](metrics.md) (`reduction_like`, `unpaid`,
hotspots, LCOM4), [`metrics-suite-hardening.md`](metrics-suite-hardening.md)
(historical NodeVisitor exemption), [`design-feedback.md`](design-feedback.md)
(inherent vs design-bound stop cases),
[`metrics-guided-implement`](../.cursor/skills/metrics-guided-implement/SKILL.md).

---

## 1. The healthy pattern

**Claim.** Matching across a closed set of options, when the code covers those
options as peer cases, is a healthy way to write Python. A type or protocol with
many variants will produce **superficially complex** callables (high path count,
many methods). That complexity is often **breadth of a sum type**, not spaghetti.

Examples of the positive shape:

| Shape | What it looks like | Why it is healthy |
| --- | --- | --- |
| Flat `match` / `if`–`elif` on a tag | One function, shallow nesting, one arm per variant | Exhaustive, linear to read, easy to extend by adding an arm |
| Reduction / aggregation table | Wide branch fan-out, little nesting, similar arm bodies | Decision table, not nested control flow |
| Visitor / handler class | Many `visit_*` / `handle_*` methods, each small | One place per variant; polymorphic dispatch is intentional |
| Enum / union method dispatch | Small methods keyed off a closed enum | Same as visitor without AST ceremony |

**Not** the claim: every high-branch function is fine. Nested
`if` inside `for` inside `try`, unpaid micro-extracts, and Strategy-per-case
hierarchies that relocate the same switch remain anti-patterns the suite should
still pressure.

**Target morphology.** Prefer **flat exhaustive coverage** of a known sum type
over:

1. Class-per-case hierarchies that lower per-method CC while `v_poly` stays flat
   or rises.
2. Sharding each arm into an F=1 helper solely to green cyclomatic / cognitive.
3. Fake cohesion (dummy `self._touch`) to green LCOM4 on dispatch classes.

---

## 2. What the board does today

### 2.1 Signals that already help

| Signal | Helpful behavior |
| --- | --- |
| **`cognitive` + nesting** | Flat peer branches cost less than nested spaghetti |
| **`reduction_like`** | High `v_poly` (≥ 8), nesting ≤ 1, cognitive near branch count → not a hotspot **on `v_poly` alone** |
| **Guidance** | Do not split `visit_*` / game LCOM4; treat visitors as inherent stop cases |
| **Hotspot = unpaid ∧ complex** | Paid high-`S` cores are not “fix” targets |

### 2.2 Where healthy unions still look like debt

After dropping NodeVisitor exemptions, dogfood on `src/py_code_metrics`
(~408 callables) showed:

| Effect | Approx. impact |
| --- | --- |
| `visit_*` / `generic_visit` unpaid | **+42** unpaid flags (all such methods) |
| Visitors in `hotspots[]` | **0** (arms stay under soft complexity gates) |
| `helpers_cores` board | Count ↑ (~171→206); `sum_S` ↓ sharply (~2192→882); `frac_S_le_0` / `frac_fan_in_le_1` worsen |
| Class LCOM4 on visitors | Still looks “incohesive” (e.g. LCOM4=4) with no gate skip |

So the **action queue** (`hotspots`) can stay sensible while **unpaid** and
**`helpers_cores`** become noisy — fragmentation gates and agent dashboards that
watch those fields falsely report regression.

Additional hotspot gap: `reduction_like` only discounts the **`v_poly`** arm of
`is_hotspot`. A wide flat table can still hotspot via **`cognitive` > threshold**
even when nesting is 1:

```text
is_hotspot:
  unpaid?
  nesting > gate?     → hotspot
  cognitive > gate?   → hotspot   ← flat unions can still land here
  v_poly > lenient and not reduction_like? → hotspot
```

### 2.3 Why fan-in / ETSPA misfire

Polymorphic or framework dispatch often yields **external fan-in 0** on each
arm: the caller invokes `visit(node)` or a single dispatcher, not `visit_Name`
directly. ETSPA then marks every arm `S ≤ 0` and `unpaid`. That is a
**measurement artifact of the call graph**, not evidence the arm failed to earn
reuse.

The same artifact hits any closed handler set whose public entry is one
function and whose private arms are never named at call sites.

---

## 3. Design constraints

Any fix must stay **project-agnostic** (usable on any Python tree),
**complementary** (hard to game without worsening another axis), and
**preferable to exemption lists** as the primary story — though a reusable
exemption list remains a last-resort escape hatch.

| Constraint | Implication |
| --- | --- |
| No py-code-metrics-only special cases | Do not hardcode `ast.NodeVisitor` again as product truth |
| Do not hide real spaghetti | Nested unpaid debt must still hotspot |
| Do not invite Strategy / dust-sharding | Lowering CC by relocating the same switch must still look bad (`v_poly`, unpaid, NOM) |
| Prefer structural recognition over config | Auto-detect flat exhaustive dispatch when cheap; config only for rare false positives |
| Board vs gate | Prefer fixing **predicates and role boards** over burying noise in docs alone |

---

## 4. Options

Options are ordered from “sharpen what we have” to “new roles / config.” They
are not mutually exclusive; a small package (A+B or B+C) is likely enough.

### Option A — Strengthen `reduction_like` (hotspot only)

**Idea.** Treat flat high-breadth callables as non-hotspots more consistently.

Concrete knobs:

1. When `reduction_like`, also skip the **cognitive** hotspot trigger (keep
   nesting trigger — deep nest is never “just a table”).
2. Optionally lower the `v_poly ≥ 8` floor or accept `match`/`elif` chain shape
   with nesting ≤ 1 even at moderate `v_poly`.
3. Emit `reduction_like` on more shapes: consecutive `match` cases, `elif`
   chains on one discriminant, `isinstance` ladders with shallow bodies.

**Pros.** Tiny change; reuses an existing flag; directly fixes the cognitive
gap.  
**Cons.** Does not fix unpaid / `helpers_cores` noise; arms still look like
failed helpers on ETSPA boards. Agents reading raw `unpaid` still thrash.

**Goodhart risk.** Deeply nested code with a misleading flat outer match —
mitigate by **keeping nesting as a hard hotspot trigger**.

### Option B — Exclude flat-dispatch arms from `helpers_cores` (board only)

**Idea.** Keep measuring unpaid for honesty, but build
`overall.etspa.helpers_cores` from helpers+cores that are **not**
`reduction_like` / not tagged as flat-dispatch arms. Fragmentation gates watch
that board; visitor noise stops dominating `sum_S`.

**Pros.** Matches the original motivation of role-split boards (leaves already
excluded). Low risk to hotspot queue.  
**Cons.** Needs a reliable arm tag (see C/D); if the tag is wrong, real unpaid
helpers disappear from the board.

### Option C — New annotation: `flat_dispatch` / `union_coverage` (generalize
`reduction_like`)

**Idea.** A first-class per-callable (and optionally per-class) flag meaning:
“this complexity is exhaustive peer coverage of a closed case set.”

Suggested detection (structural, no framework allowlist required):

| Cue | Weight |
| --- | --- |
| `max_nesting ≤ 1` | Required |
| High peer-branch count (`elif` / `match` cases / `isinstance` chain) | Strong |
| Cognitive ≤ f(cyclomatic, v_poly) (current `reduction_like` inequality) | Strong |
| Method name pattern alone (`visit_*`) | **Weak / insufficient** — too easy to abuse |
| Class is a family of same-prefix handlers with shallow bodies | Class-level `flat_dispatch_class` for LCOM4 soft-gate skip |
| Single discriminant expression shared across arms | Strong (AST) |

Effects when set:

- Not a hotspot unless nesting (or optional: non-peer nested complexity inside
  an arm) exceeds gates.
- Excluded from `helpers_cores` ETSPA board (Option B).
- Optionally: `unpaid` stays true for raw honesty, **or** unpaid is false for
  hotspot/board purposes only (`unpaid_for_gate` vs display) — prefer one
  clear semantics.

**Pros.** Names the healthy pattern; applies to match tables and visitors
alike; documentation-friendly.  
**Cons.** Detection work; false positives on “flat but incoherent” god
switches that mix unrelated concerns (pair with module/cohesion signals).

### Option D — Role or sub-role: `dispatch` / `handler`

**Idea.** Extend `role` beyond `core` | `leaf` | `helper` with
`dispatch` (or a sub-role). Dashboards already split by role; add a third
board or fold into expression / a dedicated slice.

**Pros.** Clean mental model; agents learn “dispatch is inherent.”  
**Cons.** Role classifier becomes heavier; risk of dumping ambiguous F=1
helpers into `dispatch` to escape unpaid pressure.

### Option E — Arm-complexity vs table-complexity

**Idea.** For flat tables, report **per-arm** complexity (max or p90 over arms)
as the hotspot driver, and treat **arm count** as size context (like
`statements`) — not a split mandate.

**Pros.** Aligns score with “is any single case hard?” vs “are there many
easy cases?”  
**Cons.** Requires robust arm partitioning (`match` cases, `elif` chain,
visitor methods as arms of one logical table). Larger implementation.

### Option F — LCOM4 soft-gate policy for dispatch classes

**Idea.** When a class is tagged flat-dispatch (Option C), do not treat
LCOM4 > 1 as a split mandate in guidance / future class hotspots. Still
**emit** LCOM4 for transparency.

**Pros.** Stops the LCOM4 Goodhart on visitors without pretending cohesion is
1.  
**Cons.** Needs the class tag; alone does not fix unpaid / helpers_cores.

### Option G — Reusable exemption list (escape hatch only)

**Idea.** Config / CLI list of qualified names or glob patterns that suppress
unpaid/hotspot/`helpers_cores` inclusion. Documented as **project policy**, not
metric truth.

**Pros.** Unblocks odd frameworks without baking them into the tool.  
**Cons.** Easy to paper over real debt; agents may grow the list instead of
fixing design. Use only after structural options fail.

**Do not** revive a hardcoded `NodeVisitor`-only product rule as the main fix.

---

## 5. Recommended direction

**Prefer a small package: C (annotation) + A (hotspot) + B (board), with F for
class LCOM4 guidance.**

1. **Generalize** today’s `reduction_like` into a clearer
   `flat_dispatch` / keep the name but broaden detection and effects (C).
2. **Hotspot:** nesting still fires; `v_poly` and **cognitive** do not fire when
   the flat-dispatch tag is set (A).
3. **Board:** exclude tagged callables from `helpers_cores` so ΣS / fracs track
   reusable helpers again (B).
4. **Class:** when most methods are flat-dispatch arms, skip LCOM4-as-split in
   agent guidance / any future class hotspot list (F).
5. **Defer** exemption lists (G) and full per-arm scoring (E) until dogfood shows
   residual false debt.

**Explicit non-goals**

- Maximizing average ETSPA by deleting handler vocabulary.
- Strategy / class-per-case to lower method CC.
- Project-specific base-class allowlists as the primary mechanism.

---

## 6. Evaluation plan (when implementing)

Dogfood `src/py_code_metrics` and a fixture package with:

| Fixture | Expect |
| --- | --- |
| Flat `match` on an enum / tagged union, nesting 1 | `flat_dispatch` / `reduction_like`; not in hotspots; not distorting `helpers_cores` |
| Nested spaghetti with many branches | Still hotspot + unpaid |
| AST `NodeVisitor` with tiny `visit_*` | Arms tagged; LCOM4 high but not a split mandate; helpers_cores stable vs pre-exemption-removal |
| Paid core (F≥2, high S) with real branches | Unchanged — still not hotspot if paid |
| Wide flat table with one deeply nested arm | Prefer: hotspot or arm-level flag (E lite) so nesting inside an arm is not invisible |

Gate checks:

- Self-`diff`: `n_unpaid_hotspots` should not jump solely from visitor
  reclassification noise once B/C land.
- `helpers_cores.sum_S` / fracs should move closer to the pre-noise baseline
  without hiding real F=1 unpaid helpers outside dispatch shapes.

---

## 7. Doc / agent surface (when shipping)

Update together:

- [`metrics.md`](metrics.md) — define the flag; document hotspot and board
  effects; state that exhaustive flat union coverage is a **positive** shape.
- [`design-feedback.md`](design-feedback.md) — inherent stop case cites the
  flag, not a NodeVisitor exemption.
- Skills / [`agent-cli-workflows.md`](agent-cli-workflows.md) — hotspot payload
  fields; Goodhart hard-no remains “do not shard handlers to green the board.”

Historical NodeVisitor exemption notes in
[`metrics-suite-hardening.md`](metrics-suite-hardening.md) stay history;
point here for the general replacement.

---

## 8. Summary

| Question | Answer |
| --- | --- |
| Is flat exhaustive union handling healthy? | **Yes** |
| Does the board punish it today? | **Yes** on unpaid / `helpers_cores` / LCOM4; **sometimes** on hotspots via cognitive |
| Right fix? | Structural **flat-dispatch** recognition + hotspot/board policy — not project-specific exemptions |
| First implementation slice | Broaden / rename `reduction_like` effects (cognitive + helpers_cores exclusion) before building exemption lists |
