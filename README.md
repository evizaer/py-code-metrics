# py-code-metrics

Executable that scores Python code for humans and agentic development systems. It walks a directory tree, analyzes all `.py` files, and emits a hierarchical JSON report of complementary anti-spaghetti metrics (local complexity, reuse/expression shape, class cohesion, import cycles).

## Usage

```bash
# Install (editable, with dev tools)
uv sync

# Analyze all Python files under a directory (recursive)
uv run py-code-metrics /path/to/project

# Or as a module
uv run python -m py_code_metrics /path/to/project
```

JSON is written to stdout. Pipe or redirect as needed:

```bash
uv run py-code-metrics . > metrics.json
```

## Metrics

The P0 suite below is the counterbalancing set from the research notes: gaming one axis tends to worsen another.

### Function / method

| Metric | Meaning |
| --- | --- |
| `cyclomatic` | McCabe `v(G)` — decision-point path count |
| `v_poly` | Dispatch-expanded complexity: `v(G)` plus `(|targets|-1)` at resolvable polymorphic call sites |
| `cognitive` | Sonar-style cognitive complexity (nesting-weighted) |
| `max_nesting` | Deepest control-flow nesting |
| `params` / `statements` / `returns` | Size / interface signals (method params exclude `self`/`cls`) |
| `fan_in` / `fan_in_ext` / `fan_in_rec` | Static call-site fan-in (total / external / recursive) |
| `body_tokens` / `header_tokens` / `mean_call_cost` | Token inputs to ETSPA |
| `S` / `etspa` | Effective tokens saved vs inlining: `S = (F-1)B - H - F·C` (`U=1`) |
| `car` | Call-to-assign ratio: `calls / (1 + assigns)` |
| `lmd` | Local mutation density: local/param stores ÷ body tokens |
| `cvr` | Combinator vocabulary hit rate (default allowlist + comprehensions) |
| `role` | `core` (high reuse), `leaf` (entrypoint / expressive), or `helper` |

### Class

| Metric | Meaning |
| --- | --- |
| `lcom4` | Hitz–Montazeri lack of cohesion (connected components over methods) |
| `wmc` | Weighted methods per class (sum of method cyclomatic complexities) |
| `nom` | Number of methods |

### Module / overall

| Metric | Meaning |
| --- | --- |
| Module rollups | `sum_S`, fractions with `S≤0` / `fan_in≤1`, max nesting/`v_poly`, role counts |
| Import graph | Corpus-local import edges and Tarjan SCCs (`cycles` when size > 1) |
| Overall | Corpus totals plus the same rollups |

Suggested thresholds (emitted under `thresholds`, not enforced as exit codes yet): nesting ≤ 3, params ≤ 5, `v_poly` ≤ 10–15, cognitive ≈ 15, statements ≈ 50, LCOM4 ≤ 1.

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

TCC, CBO, ATFD, God Class, RFC′, Martin package metrics, Halstead/ABC, layer contracts, delta/CI gates, exclude files, and `-m` symbol filters.
