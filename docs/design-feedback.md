# Design problem escalation (generic implement skill)

**Status.** Shipped in `.cursor/skills/metrics-guided-implement/` (step 5 +
reference escalate tree) and Workflow 1/2 notes in [agent-cli-workflows.md](agent-cli-workflows.md).
P2 optional “accepted design debt” project list still open.  
**Companion.** [agent-cli-workflows.md](agent-cli-workflows.md) (measure/gate), [metrics-guided-implement](../.cursor/skills/metrics-guided-implement/SKILL.md) (edit loop), [metrics-dogfood-reflect](../.cursor/skills/metrics-dogfood-reflect/SKILL.md) (this-repo metric product feedback).  
**TODO origin.** Was `docs/TODO.md` RDP — cleared; this doc is the canonical design.

---

## Problem

The generic implement skill already has a **stopping rule**: stop when remaining unpaid hotspots are design-bound, inherent, or already paid. In practice that stop is under-specified:

1. Agents often **keep dust-sharding** after local tactics fail (guards, paid extracts, leaf vocabulary), because “stop” is quiet and metrics still look red.
2. Or they **stop silently** — the human never learns that the remaining debt needs an architecture/algorithm decision, not another micro-refactor.
3. Or they **invent a redesign** without consent, which is out of scope for the implement loop.

Metrics and gates answer “did this edit make the complementary board worse?” They do **not** answer “should we change the design?” That judgment needs a human (or an explicit product decision). Escalation is the missing handoff.

Skills own judgment; CLI owns measurement ([agent-cli-workflows.md](agent-cli-workflows.md)). Escalation stays in the skill. The CLI may later emit compact evidence for the handoff packet, but it must not invent “design fail” exit codes.

---

## Goals

1. **Identify** when further local edits are the wrong tool (design / inherent / already paid).
2. **Escalate** design-bound cases to the human with a small, actionable packet — not a full report dump.
3. **Stop** the implement loop cleanly: no further unpaid extracts, no Strategy/poly games, no silent abandonment of the user’s goal.
4. **Distinguish** design escalation (human product/architecture choice) from **metrics product feedback** (tool false debt / Goodhart) owned by dogfood-reflect on this repo.

## Non-goals

- Auto-approving or auto-implementing redesigns.
- New gate failures for “design debt exists” (baselines already have unpaid hotspots; that is normal).
- Replacing dogfood’s iteration-log / metrics-feedback tracker.
- Teaching the CLI to classify “design-bound” with high confidence (heuristics only; human confirms).

---

## Taxonomy (stop reasons)

When the agent hits the stopping rule, classify each remaining top unpaid hotspot (or blocked change) as exactly one of:

| Class | Meaning | Escalate to human? | Agent action |
| --- | --- | --- | --- |
| **Design-bound** | Local flatten/extract cannot pay; needs different algorithm, API shape, data model, or module boundary | **Yes** | Emit escalation packet; pause redesign until human decides |
| **Inherent** | Shape is correct for the domain (visitor dispatch, Tarjan nested `strongconnect`, flat reduction leaves, intentional pipeline vocabulary) | No (unless human asked to redesign it) | Leave alone; cite class in stop note |
| **Already paid** | High local complexity amortized by F≥2 / S≫0; should not be in unpaid `hotspots` | No | Do not “fix”; if it still appears, treat as metric bug → dogfood feedback |
| **Blocked by scope** | Fix is clear but outside the current task / files the user allowed | **Yes** (scope escalate) | Packet lists out-of-scope move; do not expand scope unilaterally |
| **Tactics exhausted, still ambiguous** | Board still red after 1–2 honest local attempts; not sure design vs more flatten | **Yes** (soft) | Escalate with evidence; ask human which fork |

Only **design-bound**, **scope**, and **ambiguous** produce a formal escalation. Inherent and already-paid produce a short stop annotation in the agent reply (and, in this repo, optionally the iteration log).

---

## Detection criteria (skill judgment)

No single metric proves “design-bound.” Use this checklist after gate failure or after a hotspot campaign iteration that did not improve the unpaid board:

### A. Local tactics already tried (or clearly inapplicable)

Prefer order from the skill: in-place flatten → paid extract (expected F≥2, S>0) → named leaf subproblem that cuts a cognitive cliff. Escalation is premature if none of these were attempted on the target symbol when they still apply.

### B. Evidence that further local moves are unpaid or harmful

Any of:

- Candidate extract is F=1 and S≤0 (or would be), and inlining is the only honest rollback.
- Parent `v_poly` / nesting only improves by relocating branches (Goodhart / dust).
- Complementary board worsens when “simplifying” (`helpers_cores` fragmentation, new unpaid hotspots, CAR collapse on expressive leaves).
- Symbol already flattened once; remaining complexity is case fan-out or algorithm structure, not nesting cliffs.

### C. Positive signs of design-bound debt

Any of:

- Correctness or completeness requires a richer model (e.g. resolve needs a real type/environment story; not another `if` on callee shape).
- Fix implies new public API, persistence shape, or cross-package boundary.
- Multiple hotspots share one root cause that a local edit cannot name without a design doc.
- Human or prior log already marked the symbol design-bound (reuse that label; do not rediscover forever).

### D. Inherent (do not escalate as design)

Known patterns (extend per project via dogfood “false debt” tables):

- Visitor `visit_*` / `generic_visit` (polymorphic dispatch; F≈0 and high LCOM4 by design)
- Graph algorithms with nested recursion helpers
- `reduction_like` aggregators
- Intentional F=1 pipeline steps under a high-CAR leaf

If the only “fix” is gaming these, stop without design escalation.

### E. Attempt budget

| Context | Before escalating |
| --- | --- |
| Small production edit (Workflow 1) | At most **one** honest local pass after a gate fail; then escalate or rollback |
| Hotspot campaign (Workflow 2) | Per hotspot: flatten and/or one paid extract; if unpaid board does not improve, classify and stop that hotspot |
| Ambiguous | Escalate soft after **two** failed local approaches (not infinite tweak loops) |

Escalation is a **success mode** for the skill (correct stop), not a failure of the agent.

---

## Escalation protocol

### When to fire

Fire a **design escalation** when:

1. The user’s goal still requires touching a design-bound area, **or** a campaign stop leaves design-bound unpaid hotspots that block a stated quality goal, **and**
2. Detection criteria A–C (or E soft path) hold, **and**
3. The agent will not proceed with a redesign without an explicit human decision.

Do **not** fire merely because unpaid hotspots exist at baseline and the current change already gate-PASSes without needing them.

### What to produce (escalation packet)

Keep it short — same discipline as agent CLI views: small payload the human can act on.

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

Rules for the packet:

- **Options, not a full redesign.** Two or three forks max; include “accept debt” when that is honest.
- **One ask.** The human should be able to reply with a choice or a constraint, not another research project.
- **Metrics as evidence, not the verdict.** Cite unpaid hotspot / board deltas; do not claim the tool “detected architecture failure.”
- **No drive-by redesign** after sending the packet until the human answers (unless they already authorized a specific fork).

### Where it surfaces

| Surface | Role |
| --- | --- |
| **Agent reply (required)** | Escalation packet is the primary handoff |
| **Skill checklist** | New step after keep/tweak/rollback: escalate or stop-annotate |
| **This repo only** | Optional one-liner in `docs/metrics-iteration-log.md` when self-analysis stops on design-bound symbols (not a substitute for the human ask) |
| **CLI (optional later)** | Compact `hotspots` fields or a `stop_reasons` hint — never a hard fail |

### Relationship to rollback

| Situation | Action |
| --- | --- |
| Gate FAIL and local fix would be dust | Rollback unpaid extracts; escalate if the original goal still needs the design change |
| Gate PASS but goal incomplete (feature needs design) | Keep the honest local work; escalate the remainder |
| Gate FAIL and rollback restores baseline | Report failure + escalation; do not leave the tree worse to “show progress” |

---

## Skill integration (`metrics-guided-implement`)

Landed as workflow steps 5–6 (escalate, then test-quality). Canonical copy:
skill step 5 + reference “Escalate vs continue”. Summary:

1. Classify remaining blocked hotspots (taxonomy above).
2. **Inherent / already paid** → stop-annotate; do not escalate.
3. **Design-bound / scope / ambiguous** → escalation packet; stop local iteration.
4. Skip when gate PASSed and the goal is fully met (unrelated baseline hotspots OK).

**Dogfood boundary:** implement escalates **code design**; dogfood-reflect records
**metric product** feedback on this repo. File both when a measurement lie and a
design block coexist.
---

## Optional CLI support (later, not required to ship skill text)

| Idea | Purpose | Priority |
| --- | --- | --- |
| Document stop classes in skill only | Unblocks escalation without schema work | **Done (P0)** |
| `hotspots` entries include prior human tags if present in a project file | Avoid re-discovering known design-bound symbols | P2 |
| Agent view `diff` / `hotspots` stay evidence-only | Preserve “skills own judgment” | — |
| Exit code for “design escalation needed” | Rejected — conflates measurement with product decision | Non-goal |

No CLI change is required for the first skill revision.

---

## Worked example (this corpus)

From the iteration log: `resolve.resolve_call` remained unpaid and complex after flatten/extract attempts; further improvement needs a richer resolution design.

**Correct agent behavior under this proposal:**

1. Try flatten / reject unpaid F=1 extracts (already validated in Round 1–2).
2. Classify **design-bound**.
3. If the user’s task required simplifying resolve further → emit escalation with forks (e.g. explicit env/types vs accept plateau vs scoped rewrite), ask which fork.
4. Do not Strategy-split callee shapes to green `v_poly`.

**Incorrect:** silent stop while claiming the refactor is “done,” or shipping a large resolve redesign unasked.

---

## Success criteria

| Signal | Pass |
| --- | --- |
| Dust-shard rate | After skill update, agents stop proposing F=1 S≤0 extracts once classified design-bound |
| Human visibility | When a goal is blocked by design debt, the reply contains an escalation packet with a single ask |
| Scope discipline | No redesign landed without human choice in the packet thread |
| Payload size | Escalation cites `diff` / `hotspots` / `symbol` only — no full snapshot ingestion |
| Separation of concerns | Metric false-debt items still go to dogfood log, not mislabeled as product redesign |

---

## Implementation plan

1. ~~**P0 — Skill text**~~ — Done: step 5, taxonomy, packet template in `metrics-guided-implement`; escalate-vs-continue tree in reference.md.
2. ~~**P0 — Workflow doc**~~ — Done: Workflow 1/2 escalate subsections in [agent-cli-workflows.md](agent-cli-workflows.md).
3. ~~**P1 — Clear TODO**~~ — Done: RDP line in `docs/TODO.md` links here.
4. **P2 — Optional** — Project-local “accepted design debt” list (qualified names + rationale) that the skill must read before campaigning, so known design-bound symbols escalate only when the user reopens them.

---

## Open questions

1. Should ambiguous escalations be mandatory after two failed attempts, or only when the user opted into a hotspot campaign?
2. For multi-symbol design roots, one packet per root cause or one packet listing all blocked symbols?
3. In non-interactive/CI agent runs, should escalation become a non-zero **process** exit (wrapper), while `py-code-metrics diff` stays measurement-only?
