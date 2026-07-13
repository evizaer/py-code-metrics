---
name: metrics-dogfood-reflect
description: >-
  Dogfood py-code-metrics on itself: self-analyze src/py_code_metrics, log how
  metrics guided or misled refactors, and capture product feedback in the
  iteration log. Use when changing this repository’s metrics, CLI, gates, or
  hotspot policy; after a metrics-guided campaign; or when the user asks to
  reflect on metric quality from self-analysis.
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
[`docs/metrics-iteration-log.md`](../../../docs/metrics-iteration-log.md):
intent, key symbol deltas, gate result, anything the metrics misled you about.

Template and gate semantics: [reference.md](reference.md).

## Product feedback loop

If metrics **misled**, **missed real debt**, or **rewarded a Goodhart move**,
record it under **Metrics feedback** in the log entry and consider whether the
tool needs a new flag, exemption, dashboard split, or gate tweak. Historical
rounds & tracker: the same iteration log.

## References

- Generic implement loop: [../metrics-guided-implement/SKILL.md](../metrics-guided-implement/SKILL.md)
- Agent CLI workflows: [docs/agent-cli-workflows.md](../../../docs/agent-cli-workflows.md)
- Board semantics: [README.md](../../../README.md)
- Research intent: [anti-spaghetti-research.md](../../../anti-spaghetti-research.md)
