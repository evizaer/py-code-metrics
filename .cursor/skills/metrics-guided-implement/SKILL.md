---
name: metrics-guided-implement
description: >-
  Metrics-guided implement loop with py-code-metrics: baseline any package,
  make the smallest change, remeasure with agent views, keep only complementary
  wins, reject unpaid fragmentation. Also covers test-quality loops (oracles,
  state-field coverage, scoped mutmut campaigns) so agents turn survivors and
  weak oracles into strong tests. Use when editing production Python,
  refactoring, fixing hotspots, improving tests, or when the user asks to
  implement with metrics guidance in any project that has py-code-metrics
  available.
---

# Metrics-guided implement

Do **not** ship structural edits without a before/after metrics pass.
Optimize the **complementary board**, never a single scalar.

Prefer agent CLI views (`board`, `hotspots`, `dou`, `symbol`, `diff`, `tests`); do
**not** open full JSON reports wholesale. Workflow detail: the project's
`docs/agent-cli-workflows.md` if present, else `py-code-metrics --help`.

Set `SRC` to the package or tree under edit (e.g. `src/mypkg`).

## Workflow (every non-trivial change)

Copy and track:

```
- [ ] 1. Baseline
- [ ] 2. Implement (smallest change that fits existing style)
- [ ] 3. Remeasure + gate
- [ ] 4. Keep, tweak, or roll back
- [ ] 5. Stop-annotate or escalate design problems
- [ ] 6. Test-quality pass (when behavior or tests changed)
```

Design escalation detail: project's `docs/design-feedback.md` when present
(taxonomy, packet, attempt budget).

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

Gate must **PASS** (exit 0). Failures: rising `n_unpaid_hotspots`, rising
`max_v_poly` on an unpaid non-`reduction_like` symbol, or rising
`n_dou_sites_on_delta` (L1 DOU on changed paths only — inferred from the
snapshot pair, or scoped with `diff --paths` / `diff --delta`).

On failure or ambiguity (small payloads only):

```bash
uv run py-code-metrics hotspots -f /tmp/pcm-after.json
uv run py-code-metrics board -f /tmp/pcm-after.json
uv run py-code-metrics dou -f /tmp/pcm-after.json
uv run py-code-metrics symbol -f /tmp/pcm-after.json some.module.fn
```

Also check the board by eye via `board` / `hotspots` / `dou` (not the full snapshot):

| Watch | Prefer |
| --- | --- |
| `n_unpaid_hotspots` / unpaid nest & v_poly counts | Flat or down |
| `helpers_cores.sum_S` / `helpers_cores.frac_fan_in≤1` | Better or stable (ignore global `sum_S` noise from tiny new leaves) |
| `expression.leaves` CAR | Not collapsing into mutation-heavy helpers |
| `n_dou_sites_on_delta` (in `diff`) | Flat or down — corpus `dou.n_dou_sites` alone is not the gate |
| New symbols in `hotspots` | None that you introduced unpaid |

If `n_dou_sites_on_delta` rose: introduce a **`@dataclass`** (frozen when immutable), thread it, pick the highest-impact `dou_hotspots[]` row on the delta paths first. Do **not** remediate with TypedDict or a one-field `data: dict[str, Any]` wrapper.

If you only touched tests with no production-code change, skip the structural
gate; still run the project's tests, then the **Test-quality pass** below.

### 4. Keep / tweak / roll back

| Outcome | Action |
| --- | --- |
| Gate PASS + board stable/better | Keep |
| Local `v_poly` win via **F=1 S≤0** extract | **Inline** the extract |
| Paid core (F≥2, S≫0) now “looks hot” on raw v_poly | **Leave it** — not a hotspot under unpaid predicate |
| Only fix left is design-level | **Escalate** (packet) and stop local edits; do not dust-shard or redesign without human choice |

### 5. Stop-annotate or escalate design problems

After step 4, if unpaid hotspots remain that **blocked the task** or a campaign
stop rule fired, classify each relevant symbol and hand off — do not keep
dust-sharding or invent a redesign.

| Class | Escalate? | Agent action |
| --- | --- | --- |
| **Design-bound** | Yes | Emit escalation packet; pause redesign until human decides |
| **Inherent** | No | Leave alone; brief stop note (visitor/Tarjan/reduction_like/intentional leaf vocab) |
| **Already paid** | No | Do not “fix”; if still in unpaid `hotspots`, treat as metric bug → dogfood feedback on this repo |
| **Blocked by scope** | Yes | Packet lists out-of-scope move; do not expand scope unilaterally |
| **Tactics exhausted, ambiguous** | Yes (soft) | Escalate with evidence; ask which fork |

**Attempt budget before escalating:** small production edit — at most one honest
local pass after a gate fail; hotspot campaign — flatten and/or one paid extract
per hotspot, then classify; ambiguous — soft escalate after two failed local
approaches. Escalation is a success mode (correct stop), not agent failure.

Skip this step when the gate PASSed and the user’s goal is fully met, even if
unrelated baseline hotspots remain.

**Escalation packet** (required in the agent reply when escalating):

```text
## Design escalation

**Blocked goal:** <what the user asked that cannot finish via local edits>
**Class:** design-bound | scope | ambiguous
**Primary symbols:** <qualified_name> (path) — key metrics: v_poly / nest / cog / F / S / unpaid
**Tried locally:** <1–3 bullets: flatten / extract / rollback>
**Why local won’t pay:** <one short paragraph>
**Design forks (options, not a plan):**
  1. …
  2. …
  3. leave as accepted debt
**Ask:** <single decision question for the human>
**Evidence (optional CLI):** diff / hotspots / symbol ids only — no full snapshot
```

Rules: two or three forks max; one ask; metrics as evidence not verdict; no
drive-by redesign until the human answers. On this repo, optionally log a
one-liner in `docs/metrics-iteration-log.md` when self-analysis stops on
design-bound symbols — that does not replace the human ask.

**vs dogfood:** this skill escalates **code design** problems. Metric false debt /
Goodhart on `src/py_code_metrics` goes to `metrics-dogfood-reflect`. If both
apply, file both.

### 6. Test-quality pass

Run whenever you added/changed production behavior **or** tests. Skills own
judgment; `tests` emits findings. See [reference.md](reference.md) for the
survivor → oracle decision tree.

**Always (cheap, static):**

```bash
# Mid-PR / touched paths:
uv run py-code-metrics tests . --delta
# Or full tree when the change set is broad:
uv run py-code-metrics tests .
```

Act on findings in this order:

1. **High smells** — `NO_ORACLE`, `TAUTOLOGY`, `SWALLOWED_ERROR`, `EMPTY_BODY`
2. **Weak oracles** — replace truthiness / `is not None` with specific values, boundaries, typed `raises`, or state checks
3. **`unchecked_state_field` / low `mean_state_field_coverage`** — assert the uncovered fields (or public observables that imply them), not setup-only touches
4. Optional **`--coverage`** (with contexts) — kill `weak_oracle_covered_lines` / `unchecked_covered_callables`

**Mutation campaign (selective, not every edit):**

Run only when at least one applies:

- Touched a **critical / unpaid-hotspot** production module and claim stronger tests
- New behavioral surface where coverage alone would look fine
- Explicit user/test-quality campaign
- Static board is green but you suspect theater (strong-looking asserts that miss faults)

Do **not** run full-package mutation on every typo fix.

**Scope intelligently** (mutmut example — configure `[tool.mutmut]` or equivalent):

| Knob | Intelligent default |
| --- | --- |
| `source_paths` | Only the production file(s) you changed or that own the hotspot |
| `pytest_add_cli_args_test_selection` | Tests that exercise those modules (not the whole suite) |
| Duration | Prefer < few minutes locally; widen only for CI campaigns |

```bash
uv run --with mutmut mutmut run
uv run --with mutmut mutmut export-cicd-stats
uv run py-code-metrics tests . --mutation mutants/mutmut-cicd-stats.json
# Prefer PCM v1 / Cosmic Ray dump when you need survivor rows in findings:
# uv run py-code-metrics tests . --mutation /tmp/pcm-mutmut-v1.json
```

**Turning survivors into better tests** (grist for the mill):

| Signal | Do this | Do **not** |
| --- | --- | --- |
| Surviving mutant (e.g. `or`→`and`) | Add a **requirement-oriented** strong oracle that fails under the mutant (`mutmut show <id>`) | Freeze the buggy/mutated behavior as the expected value |
| Score ≪ ~0.85 on a scoped critical path | Strengthen oracles / state checks; re-run **scoped** mutmut | Assert `True`, pile weak truthiness, or explode micro-tests for coverage % |
| `overlap_flags: weak_oracle_covered_line` | That line is executed only by weak/none tests — upgrade those oracles | Add another smoke call |
| Uncovered state field | Assert the field (or its public observable) in an existing strong test | Read the field only in arrange/setup |
| Equivalent / low-value survivor | Leave or document; do not thrash | Chase 100% mutation score |

Positive test shape: **coverage floor** + **strong oracles** tied to behavior +
**localized** tests for complex cores + treat **survivors as debt questions**,
not auto-expected values.

## Hotspot predicate (what to “fix”)

Refactor candidates are symbols that are **complex and unpaid**:

- Above soft gates (`v_poly` / nesting / cognitive), **and**
- `unpaid` (`fan_in_ext≤1` or `S≤0`), **and**
- not `dispatch_exempt`, not a healthy paid core

Do **not** chase raw high `v_poly` on paid helpers (F≥2, S≫0).
Do **not** treat high `statements` / token counts as a reason to split when those soft gates are fine—length is context, not a hotspot driver.

## Hard no’s (Goodhart)

**Production**

- Strategy / class-per-case to lower method CC while `v_poly` stays flat or rises
- Split `visit_*` / fix visitor LCOM4 with fake coupling (`dispatch_exempt` / `lcom4_gate_exempt`)
- Maximize average ETSPA by deleting intentional leaf steps or visitors
- Optimize `frac_fan_in≤1` or function count in isolation
- Extract F=1 shards solely to relocate branches out of a parent
- Extract or shrink bodies to green a statements/LOC/token budget when nesting / cognitive / `v_poly` are already acceptable

**Tests**

- Optimize coverage % or test count without oracle strength
- Kill mutants by encoding implementation accidents or buggy snapshots
- Smoke / `assert True` theater to green mutation or coverage gates
- Skip mutation scoping (whole-monorepo `mutmut run` as a default edit step)

## Stopping rule

Stop iterating when every remaining top unpaid hotspot is one of:

1. **Design-bound** (needs a different algorithm/architecture) — **escalate**
   with a packet when it blocks the current goal (not only a quiet stop),
2. **Inherent** (graph algorithms, visitor dispatch, etc.) — stop-annotate,
3. **Already paid** (should not appear in `hotspots`) — stop-annotate; metric
   bug if still listed unpaid.

For tests: stop when high smells are gone on touched tests, strong oracles
cover behavioral symbols you changed, and (if you ran mutation) remaining
survivors are equivalent/low-value or explicitly deferred—not ignored green bars.

## Scale

| Change size | Depth |
| --- | --- |
| Typo / comment / pure test fixture | tests only (+ `tests --delta` if oracles changed) |
| Small production edit | Full structural gate once + static `tests --delta` |
| Hotspot / critical-path campaign | Structural gate + static tests + **scoped** mutmut |
| New module | Baseline → iterate until stop rule; mutation optional until behavior stabilizes |

## References

- Extract decision tree, escalate-vs-continue, test-oracle mill: [reference.md](reference.md)
- Design escalation (full taxonomy / detection): `docs/design-feedback.md` when present
- Metric meanings: project README / `docs/metrics.md` when present
- Agent CLI workflows: `docs/agent-cli-workflows.md` when present
