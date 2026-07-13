# Metrics dogfood & reflect — reference

## Gate semantics

`py-code-metrics diff` (and `scripts/compare_self_metrics.py`):

- **FAIL** if `n_unpaid_hotspots` rises
- **FAIL** if `max_v_poly` rises on an unpaid, non-`reduction_like` max symbol
- **NOTE** (not fail) if max rises on paid / reduction-like

After a feature module lands, global `sum_S` may dip; judge ETSPA via
`helpers_cores`.

## Reflection log purpose

`docs/metrics-iteration-log.md` evaluates **whether the metrics guided agent
work well** — volume and quality of edits caused by the board/gate, plus
misleads, wasted probes, and undesirable pushes.

It is **not** a feature changelog. Do not use the verdict to restate what
shipped or what is next; put that in commits / PRs.

## Reflection log template

Append to `docs/metrics-iteration-log.md`:

```markdown
## Round N — <title>

**Intent:** one line (context only — not the point of this entry)
**Snapshots:** `/tmp/pcm-before.json` → `/tmp/pcm-after.json`
**Gate:** PASS|FAIL (`diff` / `compare_self_metrics`)

### Board (evidence)
| Metric | Before | After | Δ |
| --- | ---: | ---: | ---: |
| n_unpaid_hotspots | | | |
| max_v_poly | | | |
| helpers_cores.sum_S | | | |

### Metrics-caused moves
List only work the board/gate/hotspots *made happen* (or blocked):
- Kept because metrics agreed: … (F/S / unpaid / leaf vocabulary)
- Rejected or rolled back because metrics disagreed: … (F=1 dust, Goodhart, …)
- Left alone on purpose: … (false debt / paid / inherent)
- Probes that wasted time: … (what looked hot, what you tried, why it was a dead end)

### Metrics feedback
- Guided well: …
- Misled / noisy / counter-productive: …
- Product change? flag / exemption / dashboard / gate — or none

### Verdict
2–5 sentences answering: Did the complementary suite steer desirable structure
for this change set? Where did it help vs thrash or lie? **Do not** summarize
the feature. **Do not** end with “Next: …”.
```

## Scale (this repo)

| Change size | Depth |
| --- | --- |
| Typo / comment / pure test fixture | pytest only |
| Small `src/` edit | Full gate once; log only if board moved **or** metrics misled |
| New module or hotspot campaign | Baseline → iterate until stop rule → **always log** with causal reflection |
