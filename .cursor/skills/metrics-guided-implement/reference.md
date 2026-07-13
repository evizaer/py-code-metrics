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
| Oracle tier / smells | Fake-test detection | Many weak asserts / `assert True` |
| State-field coverage | Oracle depth (static) | Touch fields only in setup |
| Mutation score / survivors | Fault-detection power | Freeze bugs; assert internals |

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

## Escalate vs continue

```
Gate fail or hotspot still unpaid after local tactics?
  ├─ Inherent / paid / false debt? → leave; stop-annotate
  ├─ Extract would be F=1 S≤0 or branch relocation? → inline; if goal blocked → escalate
  ├─ Needs new API / algorithm / boundary? → escalate (design-bound)
  ├─ Fix clear but out of allowed scope? → escalate (scope)
  └─ Unsure after attempt budget? → escalate (ambiguous)
```

Escalate when the user’s goal still needs the design-bound area (or a campaign
quality goal is blocked). Do **not** escalate merely because unpaid hotspots
exist at baseline and the current change already gate-PASSes.

Skills own this judgment; CLI `diff` / `hotspots` / `symbol` are evidence only
— never invent a “design fail” exit code. Full packet template:
`docs/design-feedback.md` when present, else the main skill’s step 5.

## Test-quality mill (survivors → better tests)

```
After production/test edit:
  1. py-code-metrics tests . [--delta]
       ├─ high smells (NO_ORACLE / TAUTOLOGY / SWALLOWED_ERROR)?
       │     → fix those tests first (strong value / raises / state)
       ├─ WEAK_ORACLE or unchecked_state_field?
       │     → upgrade oracle; mention uncovered fields in asserts
       └─ optional --coverage with contexts
             → weak_oracle_covered_lines / unchecked_covered_callables

  2. Need mutation? (critical path / hotspot / explicit campaign / suspect theater)
       ├─ NO → stop after static board is clean on touched tests
       └─ YES → scope mutmut/Cosmic Ray to changed production files + related tests
             → export → py-code-metrics tests . --mutation FILE
             → for each survivor (mutmut show / Cosmic Ray diff):
                   write requirement-oriented strong oracle that kills it
                   re-run scoped campaign
                   leave equivalent/low-value survivors documented, not gamed
```

### Oracle upgrade patterns

| Before (weak / fake) | After (strong) |
| --- | --- |
| `add(2, 3)` / `assert add(2, 3)` | `assert add(2, 3) == 5` |
| `assert result is not None` | equality / boundary / field asserts |
| bare `except: pass` | `pytest.raises(Type, match=…)` |
| `assert c.inc() == 1` only | also `assert c.value == 1` (state field) |
| covers line via incidental call | localized test with strong oracle on that symbol |

### Mutation scoping recipe

1. Identify production paths from the edit or unpaid hotspot (`symbol` / `hotspots`).
2. Set mutmut `source_paths` to those files only.
3. Select tests with `-k` / path args that import or call them.
4. Ingest CICID for score; prefer PCM v1 / Cosmic Ray dump when you need
   `mutation_survivor` finding rows.
5. Re-scope after fixes — do not widen to the whole package by default.

### Anti-Goodhart (tests)

- Do not treat `mutation_score` as a merge gate alone without reading survivors.
- Do not invent expected values from `mutmut show` diffs of *buggy* mutants.
- Do not add tests that only re-implement production logic (tautological homogenization).
- Prefer fewer strong tests over many weak ones (same anti-dust ethos as production).

## After a feature lands

Global `sum_S` may dip when new modules add leaves. Judge ETSPA via
`helpers_cores`, not the corpus-wide sum.

For test modules: prefer oracle-tier / survivor / state-field boards over
“tests exist” or global coverage %.
