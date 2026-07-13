# Complementary suite hardening (from self-iteration)

These changes harden the **production** complementary suite so it keeps guiding
feature work (including test-quality) without false debt or false wins.
**Status: implemented in Round 3** (see iteration log feedback tracker F1–F6).

Origin: product feedback from dogfooding rounds 1–2. Round-by-round evidence
lives in [`metrics-iteration-log.md`](metrics-iteration-log.md). Test-quality
research and module plan: [`../test-quality-metrics.md`](../test-quality-metrics.md).

---

## 1. High — Dispatch-exempt scoring for AST `NodeVisitor` patterns — DONE

**What changed.** `visit_*` / `generic_visit` on `ast.NodeVisitor` subclasses get `dispatch_exempt=True`; classes get `dispatch_class` / `lcom4_gate_exempt`. Exempt methods are not `unpaid` and never enter `hotspots`.

**Why.** Fan-in 0 and bleak ETSPA were measurement artifacts; splitting visitors games LCOM4.

## 2. High — Hotspot = high complexity *and* unpaid — DONE

**What changed.** Per-callable `unpaid`; `overall.hotspots[]` sorted by complexity among unpaid symbols only. Paid cores (e.g. `_classify_compare`) drop off the fix list.

**Why.** Complexity alone measures decision size; unpaidness measures whether splitting helps.

## 3. Medium — Split dashboards by role (helper ETSPA vs leaf expression) — DONE

**What changed.** `etspa.helpers_cores` (helpers+cores, non-exempt) and `expression.leaves`. Global fracs kept for continuity with a note to prefer the split boards for gates.

**Why.** Leaf pipeline vocabulary is F=1 by construction; global `frac_fan_in≤1` punished the positive shape.

## 4. Medium — Count of over-threshold callables, not only corpus max — DONE

**What changed.** `n_v_poly_gt_15`, `n_nesting_gt_3`, unpaid variants, `n_unpaid_hotspots` on overall complexity and module rollups.

**Why.** Max can stick while counts improve (Round 2 nest 4→3 invisible on max alone).

## 5. Medium — Process: self-analysis gate after feature drops — DONE

**What changed.** `scripts/compare_self_metrics.py` + README section. Fails on rising unpaid hotspot count or unpaid `max_v_poly`.

**Why.** P0 briefly shipped `v_poly=23` oracle spaghetti; gates make that visible.

## 6. Low — Aggregation / reduction-only discount on `v_poly` — DONE

**What changed.** `reduction_like` annotation; hotspot predicate does not fire on high `v_poly` alone when set (nesting/cognitive can still fire).

**Why.** Flat aggregation leaves overstate spaghetti risk relative to nested unpaid debt.

---

## Implementation order

| Step | Item | Status |
| --- | --- | --- |
| 1 | §2 unpaid hotspot predicate + `hotspots[]` | **done** |
| 2 | §4 over-threshold counts | **done** |
| 3 | §3 role-split ETSPA / expression dashboards | **done** |
| 4 | §1 NodeVisitor dispatch exemption | **done** |
| 5 | §5 self-analysis / CI gate | **done** |
| 6 | §6 reduction-like annotation | **done** |

---

## What not to implement (confirmed anti-patterns)

From iteration stop rules—do not productize these as “fixes”:

- Strategy / class-per-case hierarchies to lower raw CC while `v_poly` rises.
- Splitting each `visit_*` into a tiny free function to beautify LCOM4/NOM.
- Maximizing average ETSPA by deleting low-`S` leaf vocabulary or visitors.
- Artificial `self._touch` coupling to force LCOM4→1 on visitors.
- Re-extracting resolve/oracle branches solely to green one symbol’s `v_poly` without F≥2 or real cognitive relief.
