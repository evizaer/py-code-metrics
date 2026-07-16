# Adopting py-code-metrics in your project

Two phases: **obtain the package**, then **wire the project**. Do not conflate them.

## Happy path (team)

When the package is on PyPI:

```bash
uv add --dev py-code-metrics
uv run py-code-metrics --install-for-project .
```

Until PyPI publish, use git or a local path (below), then the same `--install-for-project` line.

`--install-for-project ROOT` is **post-package setup**. Today it copies the Cursor skill `metrics-guided-implement` into `ROOT/.cursor/skills/`. Commit that skill so agents on the repo share the same implement loop. Re-run with `--force` after upgrading the package if the skill text changed.

### Verify

```bash
uv run py-code-metrics --help
ls .cursor/skills/metrics-guided-implement/SKILL.md
```

## Obtain the package

### PyPI (stable)

```bash
uv add --dev py-code-metrics
# or: pip install --user py-code-metrics
```

Optional CLI helpers (still run `--install-for-project` afterward):

```bash
uv run py-code-metrics --uv-dev      # uv add --dev py-code-metrics
uv run py-code-metrics --pip-user    # pip install --user py-code-metrics
```

### Git (shared tip / CI before PyPI)

```bash
uv add --dev "git+https://github.com/<org>/py-code-metrics.git"
# optional: @v0.1.0 or @main
uv run py-code-metrics --install-for-project .
```

### Editable path (hack on the tool against a bigger project)

```bash
uv add --dev --editable /path/to/py-code-metrics
# or: uv run py-code-metrics --editable /path/to/py-code-metrics
uv run py-code-metrics --install-for-project .
```

Edit the metrics checkout; the consumer sees CLI changes immediately via editable install. Skill files are **copies** — after skill text changes, refresh with:

```bash
uv run py-code-metrics --install-for-project . --force
```

One-off without editing `pyproject.toml`:

```bash
uv run --with /path/to/py-code-metrics py-code-metrics snapshot src/mypkg -o /tmp/pcm.json
```

## Project vs user skill install

| Command | Destination | Use when |
|---------|-------------|----------|
| `--install-for-project ROOT` | `ROOT/.cursor/skills/metrics-guided-implement/` | Team default; commit the skill |
| `--install-for-user` | `~/.cursor/skills/metrics-guided-implement/` | Personal use across repos |

```bash
uv run py-code-metrics --install-for-project .
uv run py-code-metrics --install-for-project . --dry-run
uv run py-code-metrics --install-for-project . --force
uv run py-code-metrics --install-for-user
```

Never writes under `~/.cursor/skills-cursor/` (Cursor builtins).

## Day-one metrics loop

Docs and judgment live in the installed skill. Prefer agent views; do not open full JSON wholesale.

### Structural

```bash
SRC=src/mypkg   # tree under edit
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-before.json
uv run py-code-metrics board -f /tmp/pcm-before.json
uv run py-code-metrics hotspots -f /tmp/pcm-before.json
# … edit …
uv run py-code-metrics snapshot "$SRC" -o /tmp/pcm-after.json
uv run py-code-metrics diff --json /tmp/pcm-before.json /tmp/pcm-after.json
```

### Test quality

```bash
uv run py-code-metrics tests . --delta
uv run py-code-metrics tests .
# optional: --coverage / --mutation (see README)
```

With the skill installed, Cursor agents should use **metrics-guided-implement** when editing production Python, refactoring, or improving tests.

## What you get / what stays in the metrics repo

| Artifact | Adopter |
|----------|---------|
| CLI + metrics / views / `diff` gate | Yes |
| `metrics-guided-implement` (+ `reference.md`) | Yes (via `--install-for-*`) |
| `metrics-dogfood-reflect` | No (tool-maintainer dogfood only) |
| Full research / iteration-log docs | No |

## Refresh after upgrade

```bash
uv sync   # or bump the dependency
uv run py-code-metrics --install-for-project . --force
```
