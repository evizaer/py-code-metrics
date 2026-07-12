# Implement-and-reflect — reference

Read this when the main skill’s rules are ambiguous mid-refactor.

## Complementary board (never one axis)

| Axis | Role | Gaming if alone |
| --- | --- | --- |
| `v_poly` / cognitive / nesting | Local spaghetti | Extract dust; Strategy poly |
| ETSPA `S`, `fan_in_ext` | Reuse amortization | Delete visitors / leaf steps |
| Role morphology | core / leaf / helper | Inflate leaf count |
| Import SCCs | Architecture | Hide cycles in dynamic imports |
| `helpers_cores` vs `leaves` | Gated dashboards | Judge helpers with leaf CAR |

Round 2/3 productization: unpaid hotspots, nest/v_poly **counts**, visitor exemptions, reduction-like aggregators. Prefer those signals over corpus max alone.

## Extract decision tree

```
Need less nesting/cognitive in a leaf?
  ├─ Can flatten in place? → do that
  ├─ Duplicated logic elsewhere OR body large + will be F≥2?
  │     → extract shared helper; verify S>0 after measure
  ├─ One named subproblem dominates cognitive (e.g. BoolOp merge)?
  │     → extract that subproblem even if F=1 briefly;
  │       remeasure — if parent cliff falls and board holds, keep;
  │       if only relocated branches, inline
  └─ Otherwise leave / redesign later
```

“Reject all F=1” is too blunt. Reject **unpaid relocation**. Keep **named subproblems that cut a cognitive cliff** when the complementary board agrees.

## Known false debt (do not “fix”)

| Pattern | Why metrics lie |
| --- | --- |
| `ast.NodeVisitor.visit_*` | Polymorphic dispatch → F=0; LCOM4 looks splitty |
| Tarjan `strongconnect` nested fn | Algorithm shape |
| `to_dict` / report assemblers | Ceremonial leaves |
| Flat aggregation (`reduction_like`) | High `v_poly` from many reductions, low nesting |
| Analyze pipeline steps | Intentional F=1 leaf vocabulary |

## Paid vs unpaid examples from this repo

| Keep (paid / intentional) | Roll back / avoid |
| --- | --- |
| `_callable_stats` F=2 S≫0 | `_resolve_named_receiver` F=1 S≪0 |
| `strip_docstring_body` F=3 S>0 | identity/membership split of `_classify_compare` |
| `_classify_compare` high v, S≫0 | Strategy per resolve callee shape |
| `_combine_oracle_hits` cliff cut | Micro-helpers solely to green parent `v_poly` |

## Gate script semantics

`scripts/compare_self_metrics.py`:

- **FAIL** if `n_unpaid_hotspots` rises
- **FAIL** if `max_v_poly` rises on an unpaid, non-`reduction_like` max symbol
- **NOTE** (not fail) if max rises on paid / reduction-like

After a feature module lands, global `sum_S` may dip; judge ETSPA via `helpers_cores`.

## Reflection log template

Append to `docs/metrics-iteration-log.md`:

```markdown
## Round N — <title>

**Intent:** …
**Snapshots:** `/tmp/pcm-before.json` → `/tmp/pcm-after.json`
**Gate:** PASS|FAIL (`compare_self_metrics`)

### Board
| Metric | Before | After | Δ |
| --- | ---: | ---: | ---: |
| n_unpaid_hotspots | | | |
| max_v_poly | | | |
| helpers_cores.sum_S | | | |

### Moves kept / rejected
- Kept: …
- Rejected: … (why — F/S / Goodhart)

### Metrics feedback
- What guided well: …
- What misled: …
```
