# Metrics dogfood & reflect — reference

## Gate semantics

`py-code-metrics diff` (and `scripts/compare_self_metrics.py`):

- **FAIL** if `n_unpaid_hotspots` rises
- **FAIL** if `max_v_poly` rises on an unpaid, non-`reduction_like` max symbol
- **NOTE** (not fail) if max rises on paid / reduction-like

After a feature module lands, global `sum_S` may dip; judge ETSPA via
`helpers_cores`.

## Reflection log template

Append to `docs/metrics-iteration-log.md`:

```markdown
## Round N — <title>

**Intent:** …
**Snapshots:** `/tmp/pcm-before.json` → `/tmp/pcm-after.json`
**Gate:** PASS|FAIL (`diff` / `compare_self_metrics`)

### Board
| Metric | Before | After | Δ |
| --- | ---: | ---: | ---: |
| n_unpaid_hotspots | | | |
| max_v_poly | | | |
| helpers_cores.sum_S | | | |

### Moves kept / rejected
- Kept: …
- Rejected: … (why — F/S / Goodhart)

### Metrics feedback
- What guided well: …
- What misled: …
```

## Scale (this repo)

| Change size | Depth |
| --- | --- |
| Typo / comment / pure test fixture | pytest only |
| Small `src/` edit | Full gate once; log only if board moved |
| New module or hotspot campaign | Baseline → iterate until stop rule → **always log** |
