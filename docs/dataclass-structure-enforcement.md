# Dict overuse → structured types (DOU)

**Status.** P0 implemented (L1 + impact + `dou`/`board`/`symbol`; `diff` emits
`n_dou_sites` only — **no** fail). Research item DOU in
[`TODO.md`](TODO.md).  
**Product frame.** `py-code-metrics` is a toolkit that steers agents toward
high-quality Python with **objective boards and exit codes**, not prompt essays
or subagent spam. DOU is how we propagate “prefer **dataclasses** for structured
data” to **every tree the tool analyzes** — the same way unpaid hotspots
propagate anti-spaghetti edits.  
**Companion.** [`metrics.md`](metrics.md) (complementary board),
[`agent-cli-workflows.md`](agent-cli-workflows.md) (views + gates),
[`metrics-guided-implement`](../.cursor/skills/metrics-guided-implement/SKILL.md)
(edit loop on any project), [`design-feedback.md`](design-feedback.md)
(escalation when local fixes are wrong).

Dogfooding this repo validates the metric; it is not the customer.

---

## Problem

Agents (and humans) default to `dict[str, Any]` / `list[dict[…]]` for anything
with more than one field. That style:

1. **Erases contracts** — callers use string keys; shape drift is runtime-only.
2. **Survives refactors** — complexity gates can go green while the codebase
   stays a bag of untyped maps.
3. **Does not travel** — house style in *this* repo does not change what agents
   do in `src/acme_app` unless the **toolkit** measures and gates it there.
4. **Burns context** — without a board row / hotspot / `diff` fail, the only
   recourse is long prompts (“please use dataclasses”) that agents ignore under
   deadline pressure.

We need a **measurable, complementary signal** that says: this parameter,
return value, or constructed blob should be a **dataclass** — and a **delta
gate** so “I made the dict flatter” is not a free win on the paths under edit.

---

## Product goal

When an agent runs the usual loop on **any** package:

```text
snapshot → edit → diff / board / hotspots
```

DOU should:

1. **Surface** callables (and optionally modules) that traffic in untyped
   structured mappings where a **dataclass** is the honest type.
2. **Rank** fix targets with an **impact assessment** so agents convert the
   highest-leverage bags first — small JSON, not a sermon.
3. **Gate on delta** — rising DOU debt on changed paths fails `diff` (not a
   whole-package legacy wall).
4. **Stay complementary** — never punish homogeneous indexes, wire ingest, or
   “one dict literal then coerce”; never merge with PIF or complexity into one
   scalar.

Skills stay thin: *read the board; if DOU rose on the delta, introduce a
dataclass and thread it; do not paste a style guide.*

---

## Goals / non-goals

### Goals

| Goal | Meaning |
| --- | --- |
| **Propagate style via metrics** | Target projects improve because the board says so, not because they copied our `model.py`. |
| **Objective signal** | Annotation + AST evidence a machine agrees on; same answer for agent and CI. |
| **Agent-cheap** | Compact view fields + delta gate; no new subagent role, no multi-page prompt. |
| **Dataclass-default fixes** | Agents introduce `@dataclass` (stdlib); not TypedDict as a halfway house. |
| **Prioritized conversions** | Each candidate carries impact so refactor order is objective. |
| **Allow legitimate dicts** | Indexes, graphs, counters, opaque JSON until coerce. |

### Non-goals

- Requiring every project to adopt `MappingMixin` or our serde conventions.
- Forcing TypedDict, NamedTuple, or Pydantic as the recommended fix (dataclass
  is the default guidance; other model libs may already clear a site if present).
- Replacing typecheckers (pyrefly/mypy/pyright) — DOU **points**; checkers
  **prove** field access after the type exists.
- Auto-rewriting dicts into dataclasses (agents implement; we measure).
- Flagging unannotated classes *as DOU* — if they are messy, complexity /
  cohesion / other axes should fire; DOU is about bag-typed structured data.
- Merging DOU with **PIF** (pure-core / impure-shell) — related design themes,
  **separate metrics** (see [Decisions](#decisions)).
- A “design fail” exit code for “this API should be a richer model” — that stays
  escalation ([design-feedback.md](design-feedback.md)).

---

## What “should be a dataclass” means (portable rule)

A value is **structured-record debt** when **all** hold:

1. **Closed key set** — keys are a fixed vocabulary (field names), not open
   entity ids alone.
2. **Heterogeneous roles** — values are not a single homogeneous `T` (or the
   annotation is `Any` / missing).
3. **Cross-boundary lifetime** — appears in a parameter type, return type,
   annotated attribute, or is built and returned / passed across functions.
4. **Not declared structured** — annotation is `dict[str, Any]`,
   `dict[str, object]`, bare `dict`, `Mapping[str, Any]`, `list[dict[…]]`, or
   an untyped dict literal used as a record — **not** `dict[str, UserId]`,
   `dict[str, CallableMetrics]`, etc.

**Fix guidance (skill / agent):** introduce a **`@dataclass`** (frozen when
immutable) and thread it. Do **not** recommend TypedDict as the remediation —
it is a half-way house we do not need.

**Already-clear sites** (DOU does not fire): annotation already names a
dataclass, or another concrete record type already in the tree (e.g. existing
Pydantic model). Detection may recognize those so we do not false-positive; the
*prescribed* conversion remains dataclass for new types.

**Rule of thumb for agents (one line for the skill):**  
*If callers need two or more string keys on the same value, introduce a
dataclass; keep `dict[K, V]` only for indexes.*

---

## Taxonomy (emitted categories)

| Category | Example | DOU? | Agent action |
| --- | --- | --- | --- |
| **Record param/return** | `def f(cfg: dict[str, Any]) -> dict[str, Any]` | **Yes** | Introduce `Cfg` / result **dataclass**; thread it |
| **Record list** | `-> list[dict[str, Any]]` | **Yes** | `list[Row]` dataclass |
| **Half-shell** | dataclass with `payload: dict[str, Any]` field bag | **Yes** | Promote keys to fields |
| **Homogeneous index** | `dict[str, int]`, `dict[str, MyDc]` | No | Leave |
| **Scratch / local** | locals only, never annotated as API | No | Leave unless returned |
| **Wire then coerce** | `raw: dict[str, Any]` → `Foo(...)` / `from_dict` in same function | No (or exempt) | Keep boundary |
| **Foreign JSON API** | `json.load`, httpx `.json()` → dataclass ASAP | Exempt at load site | Coerce within one hop |
| **Unannotated class** | class with no annotations, no bag typing | No | Out of scope for DOU; other metrics if messy |

False positives to design out early: `**kwargs` typed loosely; `vars(obj)`;
`asdict` / `.dict()` **at a serializer boundary**; enum/str→str maps.

---

## Objective signals (detection layers)

Prefer **annotation truth** first (cheap, stable, agent-obvious).

### L1 — Annotation sites (primary)

Per callable / class attribute, flag when a param, return, or annotated field
uses an untyped structured mapping (`dict[str, Any]`, `list[dict[str, Any]]`,
… per taxonomy).

Emit something like:

```text
dou_kind: "record_annotation"
site: "param" | "return" | "attr"
annotation: "dict[str, Any]"
impact: { ... }   # see Impact assessment
```

This is the **clear objective signal**: the type says “bag,” the metric says
“introduce a dataclass.”

### L2 — Dict literal field bags (secondary, optional)

Dict displays with ≥ N string keys that are returned or passed across a
boundary. Use only if L1 is insufficient on real trees; weight lower. Not a
substitute for nagging unannotated classes into typing.

### L3 — Subscript churn (optional, later)

Many distinct string-constant subscripts on the same loose-dict param —
reinforces L1; alone is noisier.

### Explicit non-signals

- Count of `dict(` / `{` literals (Goodhart → micro-dicts).
- “Number of `.get` calls.”
- Missing annotations on ordinary classes (other axes).
- Suggesting TypedDict as an equally good fix.

---

## Impact assessment (prioritization)

Each DOU candidate should carry a compact **impact** object so agents (and
humans) convert high-leverage bags first instead of random drive-bys.

### Proposed fields

| Field | Meaning |
| --- | --- |
| `fan_out_sites` | Call sites / modules that consume this bag (approximate) |
| `key_vocab_size` | Distinct string keys observed (literals + known subscripts) |
| `cross_module` | Whether the bag crosses module boundaries |
| `on_public_api` | Param/return of an obvious export (no leading `_`, or `__all__`) |
| `churn_hint` | Optional: appears in current delta / recently touched paths |

### Ranking heuristic (view order)

Prefer higher impact first, e.g.:

1. Cross-module + large `fan_out_sites` + large `key_vocab_size`
2. Public API record returns
3. Local half-shell fields with repeated subscript churn

Emit on `dou_hotspots[]` / `symbol` so prioritization is **data**, not prompt
text. Exact formula can stay simple (sort keys) until dogfood says otherwise;
avoid a single opaque “impact score” that agents game.

---

## Fit on the complementary board

```text
Local complexity / unpaid hotspots
        ↕ tension ↕
Reuse (S, fan_in)                         ← don’t shatter one dict into 12 one-key helpers
        ↕ tension ↕
DOU (untyped structured mappings)         ← don’t “simplify” by returning dict bags
        ↕ tension ↕
Expression (CAR/LMD on leaves)            ← orchestration stays expressive once types exist

PIF (pure / impure)                       ← separate axis; do not fold into DOU
```

**Paid DOU fix:** introduce a dataclass, thread it through the impacted call
sites, drop string-key traffic.  
**Unpaid DOU “fix”:** rename keys, wrap `dict` in a one-field dataclass
(`class Foo: data: dict[str, Any]`), introduce TypedDict instead of a
dataclass, or split one bag into many F=1 dict builders to game a count.

Prefer **counts** (`n_dou_sites`, delta-scoped) and ranked **`dou_hotspots[]`**
with impact fields over a single scalar “dict score.”

---

## Agent surface (minimal prompt weight)

| Surface | Role |
| --- | --- |
| `board` | Compact DOU rollups (`n_dou_sites`, maybe delta vs baseline) |
| `hotspots` or `dou` view | Ranked candidates + **impact** fields + annotation snippet |
| `symbol` | DOU flags + impact for that callable |
| `diff` | Gate on **delta paths only**: fail if DOU sites on changed files rose |
| Skill | On DOU regression: introduce a **dataclass**, thread it; pick highest-impact candidate when several exist |

No dedicated “dataclass subagent.” Measurement + delta gate + impact ranking
replace prompt crafting.

---

## Gate policy (proposed, phased)

| Phase | Behavior |
| --- | --- |
| **P0** | Emit L1 + impact + `dou_hotspots[]`; **no** `diff` fail |
| **P1** | `diff` fails if L1 DOU count **on delta paths** rose (changed `*.py` only) |
| **P2** | Half-shell fields; optional L2; wire-module allowlist |

**Delta-first is mandatory for the gate.** Whole-package DOU remains available
on `board` / `dou` for campaigns; it must not block unrelated legacy when an
agent edits three files.

Do **not** gate L2 until false-positive rate is known. Do **not** fail on
homogeneous `dict[str, T]`.

---

## Portable structured-type recognition

Detection must work on target repos that never heard of this project:

1. `@dataclass` / `dataclasses.is_dataclass` — primary clear + prescribed fix
2. Other concrete record types already in use (Pydantic `BaseModel`, attrs,
   msgspec `Struct`, `NamedTuple`) — recognize so L1 does not false-positive;
   **new** types from agents should still be dataclasses
3. Do **not** steer agents toward TypedDict as remediation

Wire exemption heuristic: same-function `dict` → dataclass (or existing model)
constructor / `from_dict` / `model_validate`. Prefer precision over recall.

---

## Decisions

Resolved from open questions:

| Topic | Decision |
| --- | --- |
| **TypedDict vs dataclass** | **Dataclass by default.** TypedDict is a half-way house we do not need; skills must not recommend it as the fix. |
| **Gate scope** | **Delta paths only** for `diff` fail. Whole-tree views OK for planning. |
| **Prioritization** | Emit **impact assessment** per candidate (`fan_out_sites`, key vocab, cross-module, public API, …) so conversions are ranked objectively. |
| **Unannotated classes** | **Out of DOU scope.** No inherent problem; if messy, other metrics should flag them. |
| **PIF** | **Separate axis.** Structuring data ≠ isolating side effects / purifying business logic. Related themes, **different metrics** — never one blended score. |

---

## Dogfood (this repo) — secondary

1. Finish remaining internal bag fields so our own board is honest.
2. Run DOU on `src/py_code_metrics`; expect serde + ingest exempt, not zeros.
3. Log whether impact ranking caused high-leverage dataclass introductions vs
   TypedDict spam or unpaid fragmentation.

House lint may harden **this** package; downstream projects get the **metric**.

---

## Rollout

| Step | Deliverable | Done when |
| --- | --- | --- |
| 1 | Spec L1 grammar + exemptions + impact fields | Documented in metrics.md draft |
| 2 | Analyzer + `dou`/`board` + impact on hotspots | Stable `version` bump |
| 3 | Skill: dataclass default + pick by impact | Agents act without new prompts |
| 4 | Dogfood + 1–2 external packages | Iteration-log false-positive notes |
| 5 | `diff` gate on **delta** L1 rise (P1) | Exit `1` only for changed-path debt growth |
| 6 | Optional L2 | Only if L1 insufficient |

---

## Anti-patterns (product)

| Anti-pattern | Why it fails the toolkit mission |
| --- | --- |
| **Prompt-only enforcement** | Doesn’t propagate; dies under context pressure |
| **Whole-package DOU gate** | Blocks legacy; fights the agent delta workflow |
| **TypedDict as the recommended fix** | Half-way house; weak runtime story we don’t need |
| **Gate on raw dict literal counts** | Agents emit micro-dicts and dust helpers |
| **No impact ranking** | Agents convert random bags; wasted churn |
| **DOU nagging unannotated classes** | Wrong axis; dilutes the signal |
| **Blending DOU + PIF** | Confuses structure with purity; Goodhart soup |
| **One-field dict wrappers** | Goodhart; still untyped inside |
| **Silent style preference in skill prose** | If it matters, it is on the board or in `diff` |

---

## Verdict

DOU is a **portable complementary metric**: detect untyped structured mappings,
rank them by **impact**, expose them on agent views, and **delta-gate**
regressions so agents on *any* codebase introduce **dataclasses** instead of
`dict[str, Any]` — with almost no extra prompting. Style propagates because the
toolkit scores and prioritizes it, not because consumers read this document.
PIF and unannotated-class hygiene stay on their own axes.
