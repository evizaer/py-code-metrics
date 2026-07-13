---
name: metrics-dogfood-reflect
description: >-
  Dogfood py-code-metrics on itself: self-analyze src/py_code_metrics, and log
  causal reflection — volume/quality of work the metrics caused, plus misleads
  and wasted probes — into the iteration log (not a feature changelog). Use when
  changing this repository’s metrics, CLI, gates, or hotspot policy; after a
  metrics-guided campaign; or when the user asks to reflect on metric quality.
---

# Metrics dogfood & reflect (this repo)

Use **after** (or alongside) [metrics-guided-implement](../metrics-guided-implement/SKILL.md)
when working on **py-code-metrics itself**. That skill owns the generic
baseline → edit → gate loop; this skill owns **self-analysis targets**,
**known false debt**, and **iteration-log reflection**.

## When to invoke

- Editing `src/py_code_metrics`, agent CLI views, or gate policy
- Finishing a hotspot campaign on this codebase
- Metrics seemed wrong, noisy, or gamed — capture product feedback
- User asks to reflect / log a metrics round

Do **not** use this skill as the default implement loop for arbitrary
third-party trees; use `metrics-guided-implement` alone there.

## Self-analysis target

Always measure the tool’s own package:

```bash
SRC=src/py_code_metrics
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-before.json
# … implement via metrics-guided-implement …
uv run pytest -q
uv run ruff check src tests && uv run ruff format src tests
uv run pyrefly check
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-after.json
uv run py-code-metrics diff --json /tmp/pcm-before.json /tmp/pcm-after.json
```

Legacy gate script (same predicates as `diff`): `scripts/compare_self_metrics.py`.

## Known false debt (do not “fix”)

| Pattern | Why metrics lie |
| --- | --- |
| `ast.NodeVisitor.visit_*` | Polymorphic dispatch → F=0; LCOM4 looks splitty |
| Tarjan `strongconnect` nested fn | Algorithm shape |
| `to_dict` / report assemblers | Ceremonial leaves |
| Flat aggregation (`reduction_like`) | High `v_poly` from many reductions, low nesting |
| Analyze pipeline steps | Intentional F=1 leaf vocabulary |

## Paid vs unpaid examples (this corpus)

| Keep (paid / intentional) | Roll back / avoid |
| --- | --- |
| `_callable_stats` F=2 S≫0 | `_resolve_named_receiver` F=1 S≪0 |
| `strip_docstring_body` F=3 S>0 | identity/membership split of `_classify_compare` |
| `_classify_compare` high v, S≫0 | Strategy per resolve callee shape |
| `_combine_oracle_hits` cliff cut | Micro-helpers solely to green parent `v_poly` |

## Reflect

When the change moved the board (feature drop, hotspot cleanup, or intentional
leave-alone), append a short note to
[`docs/metrics-iteration-log.md`](../../../docs/metrics-iteration-log.md).

### Purpose of the log (read this every time)

The iteration log is **not** a changelog of what shipped. Feature intent and
files belong in commits / PR text. The log exists to evaluate the **metrics
product as a guide for agent work**:

1. **Causal volume** — how much edit effort happened *because* the board / gate /
   hotspot views steered you (flatten, paid extract, rollback, leave-alone)?
2. **Causal quality** — did that guidance produce desirable structure, or only
   greener numbers?
3. **Failure modes** — where did metrics **mislead**, **waste time**, or push
   **counter-intuitive / undesirable** changes?

Board tables are evidence for those questions, not the deliverable.

### Verdict must answer (not “what we shipped”)

Write the **Verdict** / **Metrics feedback** sections so a reader learns:

| Ask | Good answer shape |
| --- | --- |
| What did the suite make the agent do? | Specific moves: inline unpaid extract, flatten until gate flat, skip visitor “debt”, … |
| Did that pay off? | Desirable structure vs cosmetic / relocated complexity |
| Where did guidance fail? | False debt, Goodhart temptation, thrash, missed real debt, wasted probes |
| What should the product change? | Flag / exemption / dashboard / gate tweak — or “none this round” |

### Hard no’s for log entries

- Summarizing completed work (“P2 lands… Next: P3”) as the verdict
- Restating the intent / file list without causal reflection
- Celebrating gate PASS alone without saying *how* metrics shaped the path
- Omitting rejected / rolled-back moves (those are the highest-signal lessons)

Gold-standard shape: Round 2 (“How well the metrics guided…”) in the same log.
Thin board-only notes are fine for tiny edits; campaigns and feature drops
**always** need causal reflection.

Template and gate semantics: [reference.md](reference.md).

## Product feedback loop

If metrics **misled**, **missed real debt**, or **rewarded a Goodhart move**,
record it under **Metrics feedback** (mandatory for campaigns) and consider
whether the tool needs a new flag, exemption, dashboard split, or gate tweak.
Historical rounds & tracker: the same iteration log.

## References

- Generic implement loop: [../metrics-guided-implement/SKILL.md](../metrics-guided-implement/SKILL.md)
- Agent CLI workflows: [docs/agent-cli-workflows.md](../../../docs/agent-cli-workflows.md)
- Board semantics: [README.md](../../../README.md)
- Research intent: [anti-spaghetti-research.md](../../../anti-spaghetti-research.md)
