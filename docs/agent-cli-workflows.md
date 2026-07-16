# Agent CLI workflows

Target CLI surface for agents doing development work. Goal: tight baseline → edit → remeasure loops with **small, stable JSON** and **exit codes as policy**. Full hierarchical reports remain available for humans and archival; agents should almost never ingest them whole.

Companion docs: [metrics.md](metrics.md) (signal semantics), [metrics-iteration-log.md](metrics-iteration-log.md) (how metrics guided or misled — not a feature changelog), [design-feedback.md](design-feedback.md) (design-problem escalation), `.cursor/skills/metrics-guided-implement/` (procedural Goodhart rules for any project), `.cursor/skills/metrics-dogfood-reflect/` (self-analysis + causal reflection for this repo).

---

## Design principles

1. **Views over dumps** — every agent-facing command returns only the fields needed for one decision.
2. **One analyze, many queries** — optional snapshot file so remeasure does not force agents to re-parse megabytes; subcommands can read a saved report or re-run analysis.
3. **Exit codes are gates** — `0` pass / keep, `1` policy fail, `2` usage/IO. Agents must not infer pass/fail from prose.
4. **Structural and test modes stay parallel** — same workflow shapes, different predicates.
5. **Skills own judgment; CLI owns measurement** — complementary-board rules stay in the skill; the CLI emits facts and gate results.
6. **Stable schema** — bump `version` when agent view fields change; prefer additive changes.

---

## Proposed CLI shape

Keep today’s default (`py-code-metrics <path>` → full JSON) for compatibility. Add focused subcommands (or equivalent flags) as the agent primary path:

| Command | Purpose | Default payload |
| --- | --- | --- |
| `board <path>` | Complementary rollups only | `complexity`, `etspa.helpers_cores`, `expression.leaves`, `dou`, `roles`, import `cycle_count` |
| `hotspots <path>` | Ranked unpaid debt | Hotspot list + counts; no per-module trees |
| `dou <path>` | Ranked dict-overuse sites | `n_dou_sites`, impact-ranked `dou_hotspots[]` |
| `symbol <path> <qname>` | Single callable (or class) | That symbol’s metrics + light neighbors (callers/callees counts or names) |
| `diff <before> <after>` | Gate + board delta | Text summary for humans; JSON mode for agents; exit `1` on regression |
| `snapshot <path> -o FILE` | Persist full report once | Write full JSON; subsequent views read `-f FILE` |
| `tests …` | Test-quality findings (oracles, SFC, optional coverage/mutation) | Compact finding lists, not full trees |

Shared filters (all structural views):

| Flag | Effect |
| --- | --- |
| `--paths FILE…` / `--delta` | Restrict to listed or git-changed `*.py` paths (structural parity with test `--delta`) |
| `-f FILE` | Read an existing snapshot instead of re-analyzing |
| `--json` / default JSON on stdout | Machine-readable; `diff` may default to text for humans |
| `--limit N` | Cap hotspot / finding lists |

---

## Workflow 1 — Implement and reflect (default edit loop)

**When.** Any non-trivial `src/` change. Highest frequency; optimize this first.

```text
baseline → implement → remeasure + gate → keep / tweak / rollback → escalate or stop-annotate → (optional) causal log
```

On this repo, when you log: record **metrics-caused** moves and misleads
(`metrics-dogfood-reflect`), not a summary of what shipped.

### Agent steps

```bash
# 1. Baseline (once per change set)
py-code-metrics snapshot src/py_code_metrics -o /tmp/pcm-before.json

# 2. Implement (smallest change; skill owns tactics)

# 3. Remeasure + gate
py-code-metrics snapshot src/py_code_metrics -o /tmp/pcm-after.json
py-code-metrics diff /tmp/pcm-before.json /tmp/pcm-after.json --json
# exit 0 → keep; exit 1 → inspect hotspots / symbol and revise

# 4. On failure or ambiguity (small payloads only)
py-code-metrics hotspots -f /tmp/pcm-after.json
py-code-metrics board -f /tmp/pcm-after.json
py-code-metrics symbol -f /tmp/pcm-after.json some.module.fn
```

### Design-bound stop → escalate

When local tactics are exhausted and remaining unpaid hotspots are
**design-bound**, **scope-blocked**, or still **ambiguous**, the skill
**escalates to the human** (short packet with one ask) and stops local
edits — it does not dust-shard, silent-stop while the goal is incomplete, or
redesign without consent. Inherent / already-paid cases get a brief
stop-annotate only.

The CLI still only **measures** (`diff` / `hotspots` / `symbol` as evidence).
There is no “design fail” exit code; judgment stays in
`metrics-guided-implement` ([design-feedback.md](design-feedback.md)).

### Efficiency rules

- Prefer `snapshot` + `-f` so `board` / `hotspots` / `symbol` / `diff` do not re-walk the tree.
- Agents read **`diff` then `hotspots`**, never the full after report, unless debugging the tool itself.
- Pure `tests/` edits with no `src/` change: skip structural gate; use Workflow 3
  (static findings; mutation only if explicitly improving oracle power).

### Gate policy (encode in `diff`)

Primary fail: `n_unpaid_hotspots` rose.  
Secondary fail: `max_v_poly` rose on an unpaid, non-`reduction_like` symbol.  
DOU fail: `n_dou_sites_on_delta` rose (L1 sites on changed `*.py` only — inferred from the snapshot pair, or `diff --paths` / `--delta`). Corpus `n_dou_sites` is informational.  
Informational only: global `sum_S` noise from new tiny leaves; prefer `helpers_cores.*`.

Promote today’s `scripts/compare_self_metrics.py` into `diff` (same semantics, first-class exit codes + `--json`).

---

## Workflow 2 — Hotspot campaign (targeted cleanup)

**When.** Explicitly reducing unpaid spaghetti, not shipping a feature.

```text
list hotspots → pick one → symbol detail → edit → diff → repeat until stop rule
```

### Agent steps

```bash
py-code-metrics hotspots src/ --limit 10
py-code-metrics symbol src/ pkg.mod.worst_fn
# edit: prefer in-place flatten, then paid extract (skill)
py-code-metrics diff /tmp/pcm-before.json /tmp/pcm-after.json --json
```

### Efficiency rules

- One hotspot per iteration when possible; remeasure after each keep/tweak.
- Stop when remaining top hotspots are design-bound, inherent (visitor/Tarjan), or already paid (should not appear in the unpaid list).
- On **design-bound** (or scope / ambiguous after the attempt budget): **escalate**
  with a skill packet and stop that hotspot — do not Strategy-split or keep
  unpaid extracts. CLI still only measures; see [design-feedback.md](design-feedback.md).
- Do not chase raw high `v_poly` on paid cores (`unpaid=false`).

### Payload focus

Each hotspot entry should already carry enough to decide without a second call when possible: `qualified_name`, `path`, complexity fields, `fan_in_ext`, `S`, `role`, `unpaid`, `reduction_like`, `dispatch_exempt`. `symbol` adds callers/callees only when planning an extract.

---

## Workflow 3 — Test-quality loop

**When.** Adding or changing tests; verifying oracle strength and SUT linkage;
turning mutation survivors / uncovered state fields into stronger tests.

```text
static findings → fix smells/weak oracles/SFC gaps
  → optional coverage floors
  → (selective) scoped mutation campaign → kill survivors with strong oracles
  → delta-scoped recheck
```

Skills own the judgment mill (`.cursor/skills/metrics-guided-implement/`);
this workflow is the measurement path.

### Agent steps — static (every test-touching change)

```bash
py-code-metrics tests . --delta          # changed paths; default mid-PR
py-code-metrics tests .                  # full tree for campaigns
py-code-metrics tests . --coverage coverage.json --delta
```

Act on compact findings in order: high smells → weak oracles →
`unchecked_state_field` → coverage weak-lines / unchecked callables.

### Agent steps — mutation (selective)

Run **only** for critical/hotspot modules, new behavioral surfaces, explicit
campaigns, or when static signals look too clean (suspected theater). Never as
the default step for typo-sized edits.

```bash
# Scope mutmut (or Cosmic Ray) to the production files under edit + related tests.
# Example config: [tool.mutmut] source_paths = ["src/.../changed.py"]
uv run --with mutmut mutmut run
uv run --with mutmut mutmut export-cicd-stats
py-code-metrics tests . --mutation mutants/mutmut-cicd-stats.json
# Survivor rows in findings need PCM v1 or Cosmic Ray dump (CICID is score-only).
```

For each survivor: `mutmut show <id>` → add a **requirement-oriented** strong
oracle that fails under the mutant → re-run **scoped** mutation. Do not freeze
mutant behavior as the expected value. Leave equivalent/low-value survivors;
do not chase 100% score.

### Efficiency rules

- Pass **project root** so SUT resolve / SFC see production modules.
- Default agent output: smells / weak oracles / survivors / uncovered state —
  not every test’s full metric blob (`--full` only when debugging the tool).
- `--delta` mid-PR; full-suite scan for campaigns or CI.
- Coverage contexts (`--show-contexts`) only when chasing weak-oracle-only lines.
- Mutation: narrow `source_paths` + test selection; `mutants/` is discovery-skipped.
- Prefer static SFC as the cheap always-on mutation proxy between campaigns.

## Workflow 4 — Scoped / PR gate

**When.** CI, pre-commit, or “did this PR make the board worse?”

```text
analyze changed paths (or full package) → diff vs main baseline → fail closed
```

### Agent / CI steps

```bash
# On main or merge-base:
py-code-metrics snapshot src/ -o pcm-base.json

# On the branch:
py-code-metrics snapshot src/ -o pcm-head.json
py-code-metrics diff pcm-base.json pcm-head.json --json
```

Optional later: `hotspots --delta` for review comments without a stored baseline (weaker than `diff`, useful for “what should I look at”).

### Efficiency rules

- CI stores or regenerates the base snapshot; agents should not invent gate thresholds per run.
- Structural `--delta` filters **findings/hotspots**, not the meaning of corpus-level rollups — document clearly so agents do not treat path-filtered `max_v_poly` as a global claim.

---

## Workflow 5 — Symbol-local check (cheapest mid-edit probe)

**When.** Agent is mid-refactor on one function and wants a pulse without a full board read.

```bash
py-code-metrics symbol src/ pkg.mod.fn
# or after snapshot:
py-code-metrics symbol -f /tmp/pcm-after.json pkg.mod.fn
```

Still require Workflow 1’s `diff` before declaring success — local improvement can be unpaid fragmentation.

---

## Suggested agent payload shapes

Compact, versioned envelopes (illustrative):

**`board`**

```json
{
  "version": 2,
  "view": "board",
  "complexity": {},
  "etspa": {"helpers_cores": {}},
  "expression": {"leaves": {}},
  "dou": {"n_dou_sites": 0, "n_dou_callables": 0},
  "roles": {},
  "imports": {"cycle_count": 0}
}
```

**`hotspots`**

```json
{
  "version": 2,
  "view": "hotspots",
  "n_unpaid_hotspots": 0,
  "hotspots": []
}
```

**`dou`**

```json
{
  "version": 2,
  "view": "dou",
  "n_dou_sites": 0,
  "n_dou_callables": 0,
  "dou_hotspots": []
}
```

**`diff --json`**

```json
{
  "version": 2,
  "view": "diff",
  "pass": true,
  "failures": [],
  "deltas": {
    "n_unpaid_hotspots": [0, 0],
    "max_v_poly": [0, 0],
    "n_dou_sites": [0, 0],
    "n_dou_sites_on_delta": [0, 0]
  },
  "hotspots_added": [],
  "hotspots_removed": [],
  "dou_delta_paths": []
}
```

Full report (`snapshot` / default CLI) stays the archival / deep-dive format; agent skills should point at views above.

---

## Implementation priority

| Priority | Deliverable | Why |
| --- | --- | --- |
| P0 | `diff` (promote compare script) + `--json` + exit codes | Unblocks every edit loop |
| P0 | `hotspots` and `board` views | Stops full-report ingestion |
| P1 | `snapshot` + `-f` reuse | Cuts repeat analyze cost in one session |
| P1 | `symbol` | Extract / flatten decisions without scanning modules |
| P1 | Structural `--delta` / `--paths` | PR-scoped attention |
| P2 | Compact `tests` finding view | Align test mode with the same discipline |
| P2 | Neighbor hints on `symbol` | Better paid-extract planning |
| Later | Optional MCP facade over the same views | Only if warm-cache / discoverability still hurts |

---

## Explicit non-goals (for this CLI pass)

- Replacing the skill’s Goodhart / keep-tweak-rollback judgment with more metrics.
- MCP-first packaging (CLI views are the contract; MCP would wrap them).
- Teaching agents to `jq` full reports as the happy path.
- Soft thresholds as exit codes beyond the unpaid-hotspot / unpaid-`max_v_poly` gate already used in self-analysis.

---

## Measuring success

Primary success metric: **bytes (and lines) an agent must read from tool output** to finish a workflow—not analyze wall time, and not the size of snapshot files written to disk but never opened.

Snapshots may stay large on disk; that is fine. What matters is **interrogated payload**: stdout or files the agent loads into context to decide keep / tweak / rollback.

### What we measure

| Metric | Definition |
| --- | --- |
| **Interrogated bytes** | Sum of byte sizes of every CLI result the agent is expected to read in that workflow path |
| **Interrogated lines** | Same, counted as `\n`-separated lines (indent=2 JSON) |
| **Tool calls** | Number of metric CLI invocations that return agent-facing payload (snapshot writes with no read do not count) |
| **Gate clarity** | Pass/fail available from exit code alone (`diff`) without parsing prose |

Secondary (track, do not gate the CLI design on them yet): analyze latency for `src/py_code_metrics`; accidental full-report reads in agent transcripts.

### Targets (Workflow 1 — implement and reflect)

| Path | Interrogated bytes | Notes |
| --- | --- | --- |
| Pass (no ambiguity) | ≤ ~1 KB | `diff --json` only |
| Fail / inspect | ≤ ~5 KB | `diff` + `hotspots` + one `symbol` |
| Never | Full hierarchical report | Except tool debugging |

Qualitative bar (unchanged): exit code decides the gate; skill decides tactics.

### Baseline method

```bash
uv run python scripts/measure_agent_payloads.py
```

Uses real subcommand stdout when available. Keep the original 2026-07-12 baseline row for comparison; append dated post-implementation rows below.

### Baseline — 2026-07-12 (`src/py_code_metrics`, 26 files)

**Single payloads**

| Payload | Bytes | Lines | How measured |
| --- | --- | --- | --- |
| Full structural report (today’s default CLI) | 254 779 | 8 871 | `py-code-metrics src/py_code_metrics` |
| `overall` skim only (best-case `jq` of same report) | 4 372 | 171 | Extract `overall` complexity/etspa/expression/hotspots/roles/imports |
| Proposed `board` | 868 | 40 | Extract rollups only |
| Proposed `hotspots` (10 unpaid) | 2 906 | 127 | Extract `overall.hotspots` |
| Proposed `symbol` (one hotspot callable) | 808 | 37 | Extract one callable dict |
| Proposed `diff --json` (identical before/after) | 575 | 38 | Simulated gate JSON |
| `compare_self_metrics.py` text (today) | 765 | 18 | Script stdout |
| Full `--tests .` report | 42 665 | 1 437 | `py-code-metrics --tests .` |
| Proposed tests findings view | 3 631 | 148 | Weak/none oracle + smell rows only |

**Workflow totals (bytes the agent must read)**

| Workflow | Current (today) | Proposed | Reduction |
| --- | --- | --- | --- |
| W1 pass — implement and reflect | **510 323** (2× full report + diff text), or **9 509** if agent perfectly skims `overall` twice | **575** (`diff --json` only; snapshots written, not read) | ~99.9% vs full; ~94% vs optimistic skim |
| W1 fail — inspect then revise | Same as pass + more full-report grepping | **4 289** (`diff` + `hotspots` + `symbol`) | Orders of magnitude |
| W2 — hotspot campaign (list + one symbol) | **509 558** (2× full) | **3 714** | ~99.3% |
| W3 — test-quality scan | **42 665** (full tests report) | **3 631** (findings view) | ~91% |

Notes on the then-current W1 number:

- An earlier implement-and-reflect skill told agents to write full JSON to `/tmp` and skim `overall.*`. If the agent opened the files wholesale (common), cost was ~2× full report.
- Even a careful `jq` skim was ~17× larger than `board` and still left gate logic in a separate text script.

### Measured — 2026-07-12 post-implementation (`src/py_code_metrics`, 28 files, 10 unpaid hotspots)

Real subcommand stdout via `scripts/measure_agent_payloads.py` (simulated rows superseded).

**Single payloads**

| Payload | Bytes | Lines | Source |
| --- | --- | --- | --- |
| Full structural report | 291 203 | 10 195 | cli |
| `board` | 870 | 40 | cli |
| `hotspots` | 3 226 | 137 | cli |
| `symbol` | 975 | 42 | cli |
| `diff --json` | 423 | 26 | cli |
| Full `--tests .` | 52 114 | 1 761 | cli |
| `tests` findings | 4 682 | 191 | cli |

**Workflow totals vs baseline**

| Workflow | Baseline (naive) | Measured | Target | Status |
| --- | --- | --- | --- | --- |
| W1 pass | 510 323 | **423** | ≤ ~1 KB | Met |
| W1 fail | full-report greps | **4 624** | ≤ ~5 KB | Met |
| W2 | 509 558 | **4 201** | ≤ ~4 KB | Met (~band) |
| W3 | 42 665 | **4 682** | ≤ ~4 KB | Met (~band; ~91% vs full tests) |

Gate clarity: `diff` exit code alone decides pass/fail. Skill updated to snapshot + views; agents should not open full reports.

### How we re-check

1. `uv run python scripts/measure_agent_payloads.py`
2. Append a dated row if corpus or view schema moves materially.
3. Spot-check agent transcripts: sum bytes of metric outputs actually loaded.

### Out of scope for the success score

- Size of `-o` snapshot files (archival).
- Human-readable full reports.
- Model quality of the refactor (skill / eval territory).
