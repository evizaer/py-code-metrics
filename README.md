# py-code-metrics

Executable that scores Python code for humans and agentic development systems. It walks a directory tree, analyzes all `.py` files, and emits a hierarchical JSON report of complementary anti-spaghetti metrics (local complexity, reuse/expression shape, class cohesion, import cycles).

## Usage

```bash
# Install (editable, with dev tools)
uv sync

# Full hierarchical JSON (humans / archival)
uv run py-code-metrics /path/to/project
uv run python -m py_code_metrics /path/to/project

# Agent-oriented views (prefer these mid-edit — see docs/agent-cli-workflows.md)
uv run py-code-metrics snapshot src/py_code_metrics -o /tmp/pcm.json
uv run py-code-metrics board -f /tmp/pcm.json
uv run py-code-metrics hotspots -f /tmp/pcm.json
uv run py-code-metrics symbol -f /tmp/pcm.json pkg.mod.fn
uv run py-code-metrics diff --json /tmp/before.json /tmp/after.json

# Test-quality findings (compact); --full for the legacy tree
uv run py-code-metrics tests /path/to/project
uv run py-code-metrics tests /path/to/project --delta
uv run py-code-metrics tests /path/to/project --coverage coverage.json --full
uv run py-code-metrics tests /path/to/project --mutation mutants/mutmut-cicd-stats.json --full

# Legacy test flags still emit the full tree
uv run py-code-metrics --tests /path/to/project
```

## Test-quality mode (`--tests`)

Static oracle/smell analysis (P0), production linkage + optional coverage (P1), and mutation ingest + always-on state-field coverage (P2):

| Signal | Meaning |
| --- | --- |
| `oracle_tier` | `none` / `weak` / `strong` per test |
| `smell_codes` | e.g. `NO_ORACLE`, `TAUTOLOGY`, `WEAK_ORACLE`, `SWALLOWED_ERROR` |
| `calls_production` | Resolved production callable qnames invoked by the test |
| `coverage_line` / `coverage_branch` | Floors from `--coverage` JSON |
| `weak_oracle_covered_lines` | Lines whose run-contexts are only none/weak-oracle tests (needs contexts) |
| `unchecked_covered_callables` | Covered production callables with no strong-oracle static caller |
| `mutation_score` / `survivors` | From `--mutation` (mutmut CICID, Cosmic Ray dump, or PCM v1 JSON) |
| `mean_state_field_coverage` | Static share of SUT class fields mentioned in oracles (always-on) |
| `uncovered_state_fields` | Actionable field labels never inspected by oracles |

Pass the **project root** (not only `tests/`) so SUT resolve can see production modules. Generate contexts with `pytest --cov-context=test` then `coverage json --show-contexts`.

### Offline mutation campaigns

`py-code-metrics` does **not** run mutmut/Cosmic Ray. Export a report, then ingest:

```bash
# mutmut (score-only CICID export)
mutmut run
mutmut export-cicd-stats   # → mutants/mutmut-cicd-stats.json
uv run py-code-metrics tests . --mutation mutants/mutmut-cicd-stats.json --full

# Cosmic Ray (survivors with locations)
cosmic-ray dump session.sqlite > cosmic.jsonl
uv run py-code-metrics tests . --mutation cosmic.jsonl --full

# Or hand a normalized PCM report (score + survivors)
# format: "py-code-metrics.mutation.v1"
```

`mutation_score = killed / (killed + survived)` (timeouts/skipped excluded). Survivors are tagged with `overlap_flags` when they land on weak-oracle-covered lines or unchecked callables (if `--coverage` was also passed).

**Agent loop:** static `tests` findings first; scoped mutmut only for critical paths / campaigns. Judgment rules live in `.cursor/skills/metrics-guided-implement/` (§5 + reference “test-quality mill”).
## Metrics

The P0 suite below is the counterbalancing set from the research notes: gaming one axis tends to worsen another.

### Function / method

| Metric | Meaning |
| --- | --- |
| `cyclomatic` | McCabe `v(G)` — decision-point path count |
| `v_poly` | Dispatch-expanded complexity: `v(G)` plus `(|targets|-1)` at resolvable polymorphic call sites |
| `cognitive` | Sonar-style cognitive complexity (nesting-weighted) |
| `max_nesting` | Deepest control-flow nesting |
| `params` / `returns` | Interface / exit-shape signals (method params exclude `self`/`cls`) |
| `statements` | Body size context only — not a split gate or soft threshold |
| `body_tokens` / `header_tokens` / `mean_call_cost` | Token inputs to ETSPA (also useful size context; not a length gate) |
| `S` / `etspa` | Effective tokens saved vs inlining: `S = (F-1)B - H - F·C` (`U=1`) |
| `car` | Call-to-assign ratio: `calls / (1 + assigns)` |
| `lmd` | Local mutation density: local/param stores ÷ body tokens |
| `cvr` | Combinator vocabulary hit rate (default allowlist + comprehensions) |
| `role` | `core` (high reuse), `leaf` (entrypoint / expressive), or `helper` |
| `unpaid` | `true` when `fan_in_ext≤1` or `S≤0`, except `dispatch_exempt` visitors |
| `dispatch_exempt` | `visit_*` / `generic_visit` on an `ast.NodeVisitor` subclass |
| `reduction_like` | High `v_poly` with shallow nesting — aggregation-shaped, not deep spaghetti |

### Class

| Metric | Meaning |
| --- | --- |
| `lcom4` | Hitz–Montazeri lack of cohesion (connected components over methods) |
| `wmc` | Weighted methods per class (sum of method cyclomatic complexities) |
| `nom` | Number of methods |

### Module / overall

| Metric | Meaning |
| --- | --- |
| Module rollups | `sum_S`, fractions with `S≤0` / `fan_in≤1`, max nesting/`v_poly`, over-threshold counts, role counts |
| `overall.hotspots` | Unpaid callables above soft complexity gates (`v_poly` / nesting / cognitive); paid high-`S` cores are excluded |
| `overall.etspa.helpers_cores` | ETSPA board for helpers+cores only (excludes `dispatch_exempt` visitors) — prefer for fragmentation gates |
| `overall.expression.leaves` | CAR / nesting / cognitive for `role=leaf` — prefer for orchestration quality |
| Over-threshold counts | `n_v_poly_gt_15`, `n_nesting_gt_3`, plus unpaid variants — progress when corpus max is stuck |
| Import graph | Corpus-local import edges and Tarjan SCCs (`cycles` when size > 1) |

Per-callable flags: `unpaid`, `dispatch_exempt` (`visit_*` on `ast.NodeVisitor`), `reduction_like` (flat aggregation vs deep spaghetti). Class metrics add `dispatch_class` / `lcom4_gate_exempt` so visitor LCOM4 is not treated as a split mandate.

Suggested thresholds (emitted under `thresholds`, not enforced as exit codes yet): nesting ≤ 3, params ≤ 5, `v_poly` ≤ 10–15, cognitive ≈ 15, LCOM4 ≤ 1 (skip LCOM4 gates on dispatch classes). There is **no** per-function statements/LOC threshold—long flat functions are fine when complexity and unpaid/hotspot signals are healthy.

## Self-analysis gate

After changing `src/`, snapshot and compare so new modules cannot raise unpaid hotspots unnoticed:

```bash
uv run py-code-metrics snapshot src/py_code_metrics -o /tmp/pcm-before.json
# ... edit ...
uv run py-code-metrics snapshot src/py_code_metrics -o /tmp/pcm-after.json
uv run py-code-metrics diff --json /tmp/pcm-before.json /tmp/pcm-after.json
```

`diff` exits non-zero if `n_unpaid_hotspots` or unpaid `max_v_poly` rises. (`scripts/compare_self_metrics.py` remains a thin wrapper.) Log notable deltas in `docs/metrics-iteration-log.md`. Agent workflow details and payload success metrics: [docs/agent-cli-workflows.md](docs/agent-cli-workflows.md).

## Report shape

```json
{
  "version": 1,
  "tool": "py-code-metrics",
  "input": {"root": "...", "files_analyzed": 0, "files_skipped": []},
  "thresholds": {},
  "overall": {},
  "modules": [
    {
      "path": "pkg/mod.py",
      "name": "pkg.mod",
      "metrics": {},
      "imports": {"imports": [], "scc_id": null},
      "functions": [],
      "classes": [{"name": "Foo", "metrics": {"lcom4": 1, "wmc": 4, "nom": 2}, "methods": []}]
    }
  ]
}
```

Nested functions appear in the module `functions` list with a `parent` qualified name.

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
uv run pyrefly check
```

## Deferred (later passes)

TCC, CBO, ATFD, God Class, RFC′, Martin package metrics, Halstead/ABC, layer contracts, CI exit codes / SARIF (P3), exclude files, and `-m` symbol filters.
