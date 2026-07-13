# Metrics-guided implement — reference

Read this when the main skill’s rules are ambiguous mid-refactor.

## Complementary board (never one axis)

| Axis | Role | Gaming if alone |
| --- | --- | --- |
| `v_poly` / cognitive / nesting | Local spaghetti | Extract dust; Strategy poly |
| ETSPA `S`, `fan_in_ext` | Reuse amortization | Delete visitors / leaf steps |
| Role morphology | core / leaf / helper | Inflate leaf count |
| Import SCCs | Architecture | Hide cycles in dynamic imports |
| `helpers_cores` vs `leaves` | Gated dashboards | Judge helpers with leaf CAR |

Prefer unpaid-hotspot and nest/v_poly **counts** over corpus max alone. Visitor
exemptions and `reduction_like` aggregators matter when present.

## Extract decision tree

```
Need less nesting/cognitive in a leaf?
  ├─ Can flatten in place? → do that
  ├─ Duplicated logic elsewhere OR body large + will be F≥2?
  │     → extract shared helper; verify S>0 after measure
  ├─ One named subproblem dominates cognitive?
  │     → extract that subproblem even if F=1 briefly;
  │       remeasure — if parent cliff falls and board holds, keep;
  │       if only relocated branches, inline
  └─ Otherwise leave / redesign later
```

“Reject all F=1” is too blunt. Reject **unpaid relocation**. Keep **named
subproblems that cut a cognitive cliff** when the complementary board agrees.

## After a feature lands

Global `sum_S` may dip when new modules add leaves. Judge ETSPA via
`helpers_cores`, not the corpus-wide sum.
