---
name: metrics-guided-implement
description: >-
  Metrics-guided implement loop with py-code-metrics: baseline any package,
  make the smallest change, remeasure with agent views, keep only complementary
  wins, reject unpaid fragmentation. Use when editing production Python,
  refactoring, fixing hotspots, or when the user asks to implement with metrics
  guidance in any project that has py-code-metrics available.
---

# Metrics-guided implement

Do **not** ship structural edits without a before/after metrics pass.
Optimize the **complementary board**, never a single scalar.

Prefer agent CLI views (`board`, `hotspots`, `symbol`, `diff`); do **not** open
full JSON reports wholesale. Workflow detail: the project's
`docs/agent-cli-workflows.md` if present, else `py-code-metrics --help`.

Set `SRC` to the package or tree under edit (e.g. `src/mypkg`).

## Workflow (every non-trivial change)

Copy and track:

```
- [ ] 1. Baseline
- [ ] 2. Implement (smallest change that fits existing style)
- [ ] 3. Remeasure + gate
- [ ] 4. Keep, tweak, or roll back
```

### 1. Baseline

```bash
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-before.json
# Optional small reads only — never open the snapshot wholesale:
uv run py-code-metrics board -f /tmp/pcm-before.json
uv run py-code-metrics hotspots -f /tmp/pcm-before.json
```

### 2. Implement

Prefer, in order:

1. **In-place flatten** (guards, early returns, collapse redundant nests) — no new symbols.
2. **Paid extract** — shared helper with expected **F≥2** and body large enough for **S>0**, or a named subproblem that cuts a leaf’s cognitive cliff (not branch relocation).
3. **Expressive leaf vocabulary** — F=1 pipeline steps under a high-CAR leaf are OK; do **not** ETSPA-optimize them.

Match existing naming, typing, and test style. No drive-by refactors outside the task.

### 3. Remeasure + gate

```bash
# Run the project's usual test/lint checks first, then:
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-after.json
uv run py-code-metrics diff --json /tmp/pcm-before.json /tmp/pcm-after.json
```

Gate must **PASS** (exit 0). Failures: rising `n_unpaid_hotspots`, or rising
`max_v_poly` on an unpaid non-`reduction_like` symbol.

On failure or ambiguity (small payloads only):

```bash
uv run py-code-metrics hotspots -f /tmp/pcm-after.json
uv run py-code-metrics board -f /tmp/pcm-after.json
uv run py-code-metrics symbol -f /tmp/pcm-after.json some.module.fn
```

Also check the board by eye via `board` / `hotspots` (not the full snapshot):

| Watch | Prefer |
| --- | --- |
| `n_unpaid_hotspots` / unpaid nest & v_poly counts | Flat or down |
| `helpers_cores.sum_S` / `helpers_cores.frac_fan_in≤1` | Better or stable (ignore global `sum_S` noise from tiny new leaves) |
| `expression.leaves` CAR | Not collapsing into mutation-heavy helpers |
| New symbols in `hotspots` | None that you introduced unpaid |

If you only touched tests with no production-code change, skip the structural
gate; still run the project's tests. For test quality:
`uv run py-code-metrics tests . --delta`.

### 4. Keep / tweak / roll back

| Outcome | Action |
| --- | --- |
| Gate PASS + board stable/better | Keep |
| Local `v_poly` win via **F=1 S≤0** extract | **Inline** the extract |
| Paid core (F≥2, S≫0) now “looks hot” on raw v_poly | **Leave it** — not a hotspot under unpaid predicate |
| Only fix left is design-level | Stop; do not dust-shard |

## Hotspot predicate (what to “fix”)

Refactor candidates are symbols that are **complex and unpaid**:

- Above soft gates (`v_poly` / nesting / cognitive), **and**
- `unpaid` (`fan_in_ext≤1` or `S≤0`), **and**
- not `dispatch_exempt`, not a healthy paid core

Do **not** chase raw high `v_poly` on paid helpers (F≥2, S≫0).

## Hard no’s (Goodhart)

- Strategy / class-per-case to lower method CC while `v_poly` stays flat or rises
- Split `visit_*` / fix visitor LCOM4 with fake coupling (`dispatch_exempt` / `lcom4_gate_exempt`)
- Maximize average ETSPA by deleting intentional leaf steps or visitors
- Optimize `frac_fan_in≤1` or function count in isolation
- Extract F=1 shards solely to relocate branches out of a parent

## Stopping rule

Stop iterating when every remaining top unpaid hotspot is one of:

1. **Design-bound** (needs a different algorithm/architecture),
2. **Inherent** (graph algorithms, visitor dispatch, etc.), or
3. **Already paid** (should not appear in `hotspots`).

## Scale

| Change size | Depth |
| --- | --- |
| Typo / comment / pure test fixture | tests only |
| Small production edit | Full gate once |
| New module or hotspot campaign | Baseline → iterate until stop rule |

## References

- Extract decision tree & board axes: [reference.md](reference.md)
- Metric meanings: project README / `docs/metrics.md` when present
