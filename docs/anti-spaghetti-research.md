# Anti-Spaghetti Metrics for Python: Research Notes

**Purpose.** Identify architectural and structural metrics that, if a coding agent were constrained to optimize (or at least not regress) them, would meaningfully reduce the risk of spaghetti code accumulating over time. Focus is on function/class usage constraints and project-wide enforcement signals usable by tools such as `py-code-metrics`.

**Verdict.** Spaghetti is not one failure mode. It is the joint product of (1) locally tangled control flow, (2) classes that accumulate unrelated responsibilities, and (3) packages that form cycles or violate layer direction. Single-metric optimization is unsafe under Goodhart pressure; a *counterbalancing suite*—method complexity + class cohesion/coupling + import-graph architecture—gives agents actionable hard constraints while limiting gaming. Anti-gaming axes: **no polymorphism-as-hidden-`switch`** (§2.8), **no micro-method dust** (§2.9), **ETSPA reuse amortization** (§2.10). The *positive* target shape is a **combinator core (high fan-in, simple) + expressive leaves (pipelines/domain vocabulary, low mutation)** (§2.11).

---

## 1. What “spaghetti” means operationally

Classical spaghetti is control-flow chaos (deep nesting, tangled branches, unstructured jumps). In modern OO/module systems the same failure mode appears at three scales:

| Scale | Failure mode | Structural signature |
| --- | --- | --- |
| Function / method | Unreadable, untestable logic | High cyclomatic/cognitive complexity, deep nesting, long parameter lists |
| Class / type | God objects, feature envy, anemic clusters | High WMC, low cohesion (LCOM/TCC), high CBO/ATFD |
| Package / module | Tangled architecture | Dependency cycles, high instability + low abstractness (zone of pain), layer inversions |

CMU’s embedded-systems materials frame spaghetti as nested conditionals, oversized switch logic, and creeping complexity, and recommend keeping McCabe cyclomatic complexity (MCC) roughly below 10–15 per module, with nesting no deeper than ~2–3 levels.[^cmu-spaghetti]

For agent workflows, the most useful framing is Moderne’s coupling–cohesion quadrant: classes with **high coupling and low cohesion** are explicitly labeled “Spaghetti”—tangled externally and incoherent internally; agents should refactor before extending.[^moderne]

---

## 2. Function- and method-level constraints

These metrics bound *local* spaghetti: the kind that makes each change harder than the last because no human (or agent) can hold the control flow in working memory.

### 2.1 Cyclomatic complexity (McCabe, 1976)

**Definition.** Number of linearly independent paths through a method; roughly \(1 +\) decision points (`if`/`elif`, loops, `except`, boolean short-circuit operators, etc.).[^mccabe][^radon]

**Why it matters for agents.** High MCC implies more tests for branch coverage and higher defect risk. McCabe’s guidance (widely echoed by flake8-mccabe and Pylint) treats **> 10** as too complex.[^mccabe-tool][^pylint-complex] Radon’s risk bands:[^radon-cli]

| CC | Rank | Risk |
| --- | --- | --- |
| 1–5 | A | Simple |
| 6–10 | B | Well structured |
| 11–20 | C | Moderately complex |
| 21–30 | D | More complex |
| 31–40 | E | Alarming |
| 41+ | F | Error-prone |

**Agent constraint (suggested).** Fail or require extraction when `CC > 10` (strict) or `CC > 15` (lenient, matching CMU’s upper band).[^cmu-spaghetti] Prefer *delta* checks (new/changed functions must not exceed threshold) over global averages—averages hide power-law outliers.[^van-deursen]

**Gaming risk.** Agents can “pass” by splitting one tangled method into many tiny methods that still share mutable state, or by replacing branches with opaque dispatch tables. Pair with cohesion and nesting metrics.

**Critical loophole — polymorphism as implicit `if`/`switch`.** Method-local McCabe *does not* count dynamic dispatch. NASA SATC warned explicitly that a low method CC may mean “decisions are deferred through message passing, not that the method is not complex,” and that CC cannot measure class complexity under inheritance.[^nasa-satc] NIST SP 500-235 (Watson & McCabe) models a polymorphic call as a multi-way branch (“implicit control flow”) that *would* raise cyclomatic complexity and test count if expanded—but they deliberately **omit** that expansion from module-level CC so reusable components stay measurable in isolation; the cost is deferred to integration testing (optimistic / balanced / pessimistic policies).[^nist-structured] Industry advice often *recommends* “replace conditionals with polymorphism / Strategy” as a CC-reduction tactic,[^sourcegraph-cc] which is exactly the Goodhart path for an optimizing agent. **Plain cyclomatic (and cognitive) complexity alone cannot stop this cheat.** Countermeasures are in §2.8.

### 2.2 Cognitive complexity (Campbell / SonarSource, 2017–)

**Definition.** Increments for breaks in linear reading flow, with **extra cost for nesting**; flat `switch`/`match` chains are cheaper than nested `if`s of equal path count.[^cognitive-blog][^cognitive-pdf]

**Why it matters.** Cyclomatic complexity cannot distinguish a readable flat decision table from deeply nested spaghetti with the same path count—exactly the distinction agents need when deciding “edit vs extract.”[^moderne][^sourcegraph-cc]

**Agent constraint.** Cap cognitive complexity (Sonar’s common default is ~15 for methods) and treat nesting penalty as the primary anti-spaghetti lever.

### 2.3 Maximum nesting depth

**Definition.** Deepest stack of control-flow constructs in a function.

**Why it matters.** Nesting depth above ~3–4 is an independent readability failure even when CC is moderate.[^moderne][^cmu-spaghetti] CMU materials flag nested `if`/`switch` and excessive `break`/`continue`/multiple returns as spaghetti signs.[^cmu-spaghetti]

**Agent constraint.** `max_nesting_depth ≤ 3` (prefer early returns / guard clauses / extract method).

### 2.4 Parameter count, locals, statements, returns

**Definitions / common thresholds (Pylint design checker tradition):**

- Arguments: often **≤ 5** before “too many arguments.”[^moderne][^pylint-design]
- Statements per function: Pylint’s `too-many-statements` (R0915) defaults around **50**.[^pylint-design]
- Related styleguide signals (wemake-python-styleguide): limit local variables, returns/yields/awaits, decorators, expressions—each a proxy for “doing too much.”[^stackoverflow-cc]

**Agent constraint.** High parameter count should block “just add another flag” edits and push toward parameter objects or narrower functions.

### 2.5 ABC metric (Fitzpatrick, 1997)

**Definition.** Decompose complexity into Assignments (A), Branches/calls (B), Conditions (C); magnitude \(\sqrt{A^2+B^2+C^2}\).[^moderne]

**Agent use.** The *components* matter more than the composite: high-A ≈ data transformer; high-B ≈ orchestrator; high-C ≈ decision-maker. Different edit strategies apply.[^moderne]

### 2.6 Halstead volume / estimated bugs (Halstead, 1977)

**Definition.** Operator/operand vocabulary and usage → volume, difficulty, estimated defect count.[^moderne][^radon]

**Agent use.** High Halstead “bugs” on a touched method is a signal to write tests *before* editing—not a primary architecture metric.[^moderne]

### 2.7 Spaghetti Factor (extended McCabe)

CMU’s “Spaghetti Factor” combines strict cyclomatic complexity with globals and size:[^cmu-spaghetti]

\[
SF = SCC + (Globals \times 5) + (SLOC / 20)
\]

Scoring guidance: ~5–10 sweet spot; ≥30 redesign module; ≥50 throw away. For Python, map “globals” to module-level mutable state and class attributes used as ambient shared state.

### 2.8 Polymorphism-aware complexity (closing the Strategy/inheritance cheat)

**Short answer.** There is **no** widely used drop-in “cyclomatic complexity” that both (a) stays a true CFG path count of one function and (b) charges for inheritance-as-control-flow. McCabe’s family *acknowledges* the cheat and moves the accounting to **integration / hierarchy** metrics instead of redefining `v(G)`.[^nist-structured][^nasa-satc]

#### What fails

| Metric | Stops poly-as-`if`? | Why |
| --- | --- | --- |
| McCabe `v(G)` | No | Counts only explicit CFG decisions in one method[^mccabe] |
| Cognitive complexity | No | Same scope; nesting of *written* control flow only[^cognitive-blog] |
| Essential complexity `ev(G)` | No | Measures unstructuredness (irreducible CFG), not dispatch breadth[^nist-structured] |
| Per-class WMC of *one* leaf | Weak | Each Strategy class can have `WMC≈1` while the family encodes an N-way branch |

#### What works (charge the hidden branch)

1. **Implicit-control-flow–expanded complexity (NIST “pessimistic” model).**  
   At each dynamically bound call site, treat possible resolutions as a multi-way decision: expand the call into a `case` with one arm per override. That expansion *increases* cyclomatic complexity of the caller by roughly `(targets − 1)` per polymorphic site.[^nist-structured]  
   - *Optimistic:* ignore expansion (trust abstractions) — agents can cheat.  
   - *Balanced:* require that the full resolution set is exercised from some call site.  
   - *Pessimistic:* every call site × every resolution — anti-cheat but can explode.  
   **For agent scoring, prefer a static approximation:**  
   \[
   v_{\text{poly}}(m) = v(G_m) + \sum_{c \in \text{poly calls in } m}(\lvert targets(c)\rvert - 1)
   \]
   with `targets(c)` from MRO / override sets (and similarly for `Protocol` / duck-typed registries if resolvable).

2. **Module design complexity `iv(G)` and integration complexity `S1`.**  
   `iv(G)` is cyclomatic complexity of the *design-reduced* graph (logic that affects which subordinates are called).  
   \(S1 = \sum iv(G_i) - n + 1\) estimates integration-test burden across modules.[^nist-structured][^mccabe-iq]  
   Pushing an `if` into Strategy classes lowers caller `v(G)` but typically **raises** design/integration complexity unless the hierarchy is already a trusted, cohesive abstraction. McCabe IQ also defines **object integration complexity `OS1`** for integrating a class under chosen dynamic resolutions.[^mccabe-iq]

3. **RFC / RFC′ with polymorphic expansion.**  
   Response-for-a-class counts methods reachable when a message arrives. Prefer **RFC′** (full call tree). When the callee is polymorphic, **count all possible remote methods**.[^aivosto-rfc] Converting a switch into N overrides grows the response set even if each method’s `v(G)` is 1.

4. **Hierarchy / override-family aggregates (not single-method CC).**  
   - **Override fan-out:** number of concrete implementations of each abstract/overridable method.  
   - **Family WMC:** \(\sum v(G)\) over all overrides of the same method name in a hierarchy (plus the selector/`__new__`/factory that chooses the type).  
   - **NOC / DIT** on types introduced to “fix” a conditional.[^ck-ieee]  
   - MOOD **Polymorphism Factor (PF)** measures overriding density system-wide (context, not a local gate).[^mood-pf]

5. **Delta policy that withholds credit for poly-shaped CC drops.**  
   Treat a change as *not* an improvement if method `v(G)` falls **and** any of: new subclasses for one behavior family, override count ↑, RFC′ ↑, `v_poly` ↑, or LCOM4 on the new types is poor. Legitimate Strategy/State refactors should keep family WMC and `v_poly` flat or down *and* improve cohesion—not merely relocate branches.

#### Practical recommendation for `py-code-metrics` / agents

Do **not** optimize raw `v(G)`. Optimize a **pair**:

- Local readability: nesting + cognitive complexity (still useful).  
- Decision accounting: **`v_poly` and/or RFC′ + override fan-out + hierarchy WMC**.

Hard gate example: reject edits where `Δv(G) < 0` but `Δv_poly ≥ 0` and new types were added solely as branch arms (detectable when each new subclass overrides one method and adds little unique state—i.e. “class-per-case” smell).

### 2.9 Anti-fragmentation: tiny, seldom-used methods

**Problem.** Caps on *per-method* cyclomatic complexity, nesting, LOC, or token count create the opposite Goodhart pressure: shatter one readable function into dozens of 3-line helpers that are each “simple,” barely reused (fan-in 1), and harder to navigate. Clean Code–style “tiny function” dogma has been critiqued on exactly these grounds—shallow methods multiply system complexity even when each unit looks clean.[^small-fns-harmful][^shotgun]

**Do existing research metrics counteract this?** Partially—only if scored at the *right aggregation level* and paired with call-graph signals. Per-method size/CC **encourage** the cheat.

| Metric / force | Counters micro-fragmentation? | How |
| --- | --- | --- |
| Per-method CC / cognitive / LOC / tokens | **No — causes it** | Reward is “make each leaf small” |
| File/module/repo **total** tokens or LOC | **Yes (weak)** | Splitting does not shrink total size; may increase it (boilerplate, names, signatures) |
| **WMC** (sum of method CCs, or unit-weighted ≈ NOM) | **Yes** | N methods of CC≈1 ⇒ WMC ≥ N; class gets worse as you shard[^ck-ieee][^moderne] |
| **NOM / NPM** (Lorenz & Kidd; often ≤ ~20 methods/class) | **Yes** | Direct cap on method proliferation[^nom-lorenz] |
| **RFC / RFC′** | **Yes** | Every new local method grows the response set[^ck-ieee] |
| **`iv(G)` / integration complexity `S1`** | **Yes** | More call edges ⇒ higher design/integration complexity[^nist-structured] |
| **Fan-in distribution** | **Yes (strongest local signal)** | Track share of methods with fan-in ≤ 1; reject extracts that only create single-caller helpers[^henry-kafura][^fanin-aspects] |
| LCOM4 / TCC | **Weak / mixed** | Cohesive helpers that share fields keep LCOM4=1; fragmentation inside one responsibility looks “fine” |
| CBO / import cycles | **Only if new types/modules** | Method-only splits inside one file evade these |
| Maintainability Index (averages) | **No — gamed** | Averaging small methods hides hotspots and rewards shredding[^van-deursen] |
| Shotgun surgery / change coupling | **Yes (evolutionary)** | One concept edited in many tiny units; Inline Method / Inline Class are the remedies[^shotgun] |
| Middle Man / pure-delegate ratio | **Yes** | Methods whose body is only a call (or trivial wrap) should be inlined[^shotgun] |

#### Forces that actually stop an optimizing agent

1. **Never use per-method LOC/tokens as an objective.** Report them; optimize **totals** at file/module/symbol-under-edit *and* hold or improve call-graph health. The project’s own token-count metric is safe only as a *budget on the edited scope*, not as “minimize tokens per function.”[^readme]

2. **Hard gate on fan-in-1 extraction.**  
   \[
   \text{reject if } \Delta(\#\{\text{methods with fan-in} \le 1\}) > 0
   \]
   unless the new symbol is a required public API. Legitimate Extract Method for readability should be rare and preferably create fan-in ≥ 2 within the same change set (second call site in the same diff), or replace duplication (net LOC down *and* fan-in ≥ 2).

3. **Class/module cardinality gates:** NOM / WMC / RFC must not rise when “improving” CC. A refactor that lowers max method CC but raises WMC and RFC is a **net regression**.

4. **Call-chain / navigation cost.** Approximate “how many frames to understand feature F”:
   - max depth of the static call tree from public entrypoints;
   - or average number of distinct methods touched along paths covering the changed behavior.  
   Fragmentation that deepens the tree without reducing `v_poly` or duplication is pure cost.[^small-fns-harmful]

5. **Delegate / Middle Man ratio.** Flag methods whose non-docstring body is a single call (or `return f(...)`) and count them toward a fragmentation score; prefer Inline Method.

6. **Public surface NPM.** Prefer keeping helpers private/`_`-prefixed *and* still count them in NOM/WMC so hiding names cannot erase the cost; additionally cap growth of public methods.

7. **Delta lexicography (recommended agent objective):**  
   Among edits that preserve behavior:  
   (a) do not increase fan-in≤1 count;  
   (b) do not increase NOM/WMC/RFC of touched types;  
   (c) then improve nesting / `v_poly` / cohesion.  
   That ordering makes “shatter into dust” dominated by (a)–(b) before any CC win counts.

#### What will *not* save you

- Cognitive complexity alone (same scope as CC).  
- LCOM4 alone (happy with many cohesive micro-methods).  
- “Reuse” rhetoric without measuring fan-in (agents will claim reuse).  
- Average method length targets (the MI failure mode).[^van-deursen]

### 2.10 Proposed: Effective Tokens Saved per Abstraction (ETSPA)

**Idea.** Abstraction is worthwhile when reuse amortizes the cost of the abstraction. A 100-token body used 40 times should outscore ten 10-token bodies each used 4 times—even though the latter look “cleaner” under per-method CC/LOC. Combined with short-function *caps* (nesting, `v_poly`, params), this creates intentional **positive tension**: keep units understandable, but only split when the call graph pays you back.

This is a natural specialization of the project’s sketched **Semantic Compression Ratio** (tokens represented by symbols × usage vs raw token mass).[^readme]

#### Definition

For a callable \(f\) (function or method):

| Symbol | Meaning |
| --- | --- |
| \(B\) | Body token count (implementation; recommend **excluding** docstrings/comments so prose cannot inflate “savings”) |
| \(H\) | Header/abstraction tax: `def`/`async def`, name, parameters, annotations, decorators |
| \(F\) | Static **fan-in**: number of call sites that resolve to \(f\) (see counting rules below) |
| \(C\) | Mean token cost of a call site (name + arguments + punctuation); measure from real call sites or use a fixed prior |
| \(U\) | Abstraction units (default \(U = 1\); see variants) |

**Tokens saved vs naïvely inlining the body at every call site:**

\[
S(f) = F\cdot B - \bigl(B + H + F\cdot C\bigr) = (F - 1)\,B - H - F\cdot C
\]

**Effective tokens saved per abstraction unit:**

\[
\mathrm{ETSPA}(f) = \frac{S(f)}{U}
\]

**Worked comparison** (ignore \(H,C\) for intuition, or set them small):

| Design | \(B\) | \(F\) | \(S \approx (F-1)B\) |
| --- | --- | --- | --- |
| One shared helper | 100 | 40 | \(39 \times 100 = 3900\) |
| Ten micro-helpers | 10 each | 4 each | \(10 \times (3 \times 10) = 300\) |

The shared helper wins by an order of magnitude—exactly the intended pressure.

#### Counting rules (make cheating hard)

1. **Fan-in \(F\):** count static call sites (AST `Call` whose callee resolves to \(f\)). Do **not** count the definition. Optionally exclude test code from \(F\) when scoring production APIs (or report both).  
2. **Self-recursion:** count recursive calls toward \(F\) (they are real use) or report \(F_{\mathrm{ext}}\) vs \(F_{\mathrm{rec}}\) separately; for ETSPA prefer \(F = F_{\mathrm{ext}} + F_{\mathrm{rec}}\) only if body would otherwise be duplicated—usually \(F_{\mathrm{ext}}\) is the right amortization signal.  
3. **Polymorphic targets:** if a call may resolve to several overrides, either (a) attribute fractional fan-in \(1/\lvert targets\rvert\) to each, or (b) credit only the base/protocol symbol and score overrides with their own direct \(F\). Pick one; document it. Fractional is fairer against Strategy-shaped inflation.  
4. **Callbacks / undecorated references:** passing \(f\) as a value without calling it does not increase \(F\) until call sites through that alias are resolved; unresolved aliases can add a conservative \(+1\) “escape” use or be flagged unknown.  
5. **\(B = 0\) or trivial bodies:** if body is `pass` / `...` / single `return` of a constant, force \(S \le 0\) (no savings from hollow abstractions).  
6. **Dead callables (\(F = 0\)):** \(S = -B - H < 0\); treat as debt, not “unused capacity.”

#### Abstraction unit \(U\) variants

| Variant | \(U\) | Use when |
| --- | --- | --- |
| **ETSPA₁** (default) | \(1\) | Per-callable score; simplest |
| **ETSPAᵤ** (interface-weighted) | \(1 + \alpha n_{\mathrm{params}} + \beta n_{\mathrm{decorators}}\) | Penalize wide/awkward interfaces |
| **ETSPAₛ** (signature tokens) | \(H\) or \(H/H_0\) | “Savings per token of API surface” |
| **Module rollup** | \(\sum_f S(f)\) or \(\sum S(f)/\sum U(f)\) | Compare files; resists sharding into many low-\(S\) units |

For agent objectives, prefer **sum of \(S(f)\)** over the edited scope (total compression) plus a floor on median ETSPA of *new* callables—not “maximize average ETSPA” (which can be gamed by deleting low scorers).

#### Positive tension with short-function metrics

```text
                    high reuse (F)
                         ▲
                         │  sweet spot:
                         │  substantial B, high F
                         │  (keep under nesting/v_poly caps)
              ┌──────────┼──────────┐
   low B      │ shallow  │  high-ETSPA│
   (micro)    │ dust     │  libraries │
              │ S≈0 or − │  & shared  │
              │          │  helpers   │
              └──────────┼──────────┘
                         │  god methods:
                         │  high B, low F
                         │  (CC/nesting should fail)
                         ▼
                    low reuse (F)
```

- **Short-function / complexity caps** forbid the bottom-right (huge rarely used bodies) and limit how far right \(B\) can grow.  
- **ETSPA / \(S\)** forbids the left side (extracting dust with \(F \le 1\) or tiny \(S\)).  
- Agents must move **up** (more real reuse) or **compress duplicates**, not merely partition.

Recommended lexicography update (§2.9):  
(a) fan-in≤1 count non-increasing;  
(b) \(\sum S\) on touched scope non-decreasing (or ETSPA of new symbols ≥ threshold, e.g. \(S > 0\));  
(c) NOM/WMC/RFC non-increasing when the change is a “cleanup”;  
(d) then nesting / `v_poly` / cohesion.

#### Gaming attempts and mitigations

| Cheat | Mitigation |
| --- | --- |
| Inflate \(B\) with no-op padding | Exclude non-semantic tokens; pair with CC/Halstead; max \(B\) caps still apply |
| Inflate \(F\) with dummy call sites | Calls must be reachable from public entrypoints, or weight \(F\) by enclosing test vs prod; ignore `if False` |
| One giant method called everywhere | Nesting / `v_poly` / param caps; LCOM on owning type |
| Many tiny methods each with \(F=4\) manufactured | \(\sum S\) still loses to one shared method; NOM/WMC rise |
| Count aliases / imports as fan-in | Only `Call` nodes (and annotated bound methods), not `Name` loads |

#### Relation to prior art

- **Henry–Kafura** uses \(length \times (fan\text{-}in \times fan\text{-}out)^2\) as *risk/complexity*, not savings; high fan-in×fan-out is a warning, whereas high fan-in with moderate \(B\) is *good* for ETSPA.[^henry-kafura]  
- **Fan-in analysis** treats high fan-in as reuse/crosscutting signal—the same numerator pressure.[^fanin-aspects]  
- ETSPA is closer to a **compression / DRY accounting** identity than to classical defect predictors; use it as a *refactor incentive*, alongside CK/NIST metrics as *safety rails*.

#### Implementation sketch for `py-code-metrics`

1. Tokenize via `tokenize` / AST for \(B,H\); build interprocedural call graph for \(F\).  
2. Emit per-symbol: \(B, F, H, C, S, \mathrm{ETSPA}\).  
3. Emit scope rollups: \(\sum S\), fraction with \(S \le 0\), fraction with \(F \le 1\).  
4. Diff mode: fail CI if a change decreases \(\sum S\) while claiming complexity wins, or adds symbols with \(S \le 0\).

### 2.11 Target morphology: combinator core + expressive leaves

Anti-spaghetti metrics mostly say what to *avoid*. The shape you want to *encourage* is more specific:

> **Inner call-graph nodes** are highly reused, relatively simple combinators and domain operations. **Leaves** (and other low-fan-in entry/orchestration functions) do little low-level twiddling; they *speak* those abstractions—pipelines, anaphors, domain values—closer to LINQ, readable point-free Haskell, or  
> `map _.field_name |> filter (_ > 10) |> map (2 - _)`  
> than to mutating accumulator loops and scratch locals.

That is compatible with classical advice (high fan-in utilities; application code wires them together)[^code-complete-fan] but adds an **expression-oriented / low-mutation** bias and a preference for **domain vocabularies** over bare `int`/`list` soup.

```text
        entry / leaf orchestration
        (low fan-in, high “speech” via calls)
                    │
         map / filter / pipe / domain ops
         (HIGH fan-in, simple, pure-ish)   ← combinator core
                    │
              primitives / I/O edges
```

#### Structural signatures (measurable)

| Role | Call-graph | Body style | ETSPA / size |
| --- | --- | --- | --- |
| **Combinator / core** | High \(F\), low-to-moderate fan-out | Low assignments, low nesting, small `v_poly`, returns values | High \(S\) / ETSPA (§2.10) |
| **Expressive leaf** | Low \(F\) (often 1—entrypoint or one feature), **high call density** | Few mutable locals; pipelines / comprehensions / fluent chains; domain types in signatures | \(S\) may be low/negative (not reused)—**allowed** if call-to-assign ratio is high |
| **Anti-pattern leaf** | Low \(F\), low call density | Many assignments, loops building lists, primitive locals | Fails mutation & vocabulary metrics |
| **Anti-pattern “hub”** | High \(F\) *and* high fan-out *and* high mutation | God utility | Classical hotspot[^henry-kafura] |

Leaves with fan-in 1 are **not** automatically bad here—they are the *sentences* that use the library. The §2.9 rule against fan-in≤1 should apply to **new helpers claimed as abstractions**, not to feature entrypoints. Distinguish:

- `is_entrypoint` / `is_test` / `is_public_api` → leaf privileges  
- `is_helper` (private, non-exported) with \(F\le 1\) → fragmentation smell  

#### Metric suite for this morphology

**1. Call-to-assign ratio (CAR)** — Fitzpatrick ABC split:[^moderne]

\[
\mathrm{CAR}(f) = \frac{B_{\mathrm{calls}}}{1 + A_{\mathrm{assigns}}}
\]

Prefer high CAR at leaves (speech via calls). Prefer moderate CAR and low \(A\) at core combinators. Penalize high \(A\) (mutation / intermediate stores).

**2. Local mutation density (LMD)**

\[
\mathrm{LMD}(f) = \frac{\#\{\text{stores to locals/params}\}}{B_{\mathrm{tokens}}}
\]

Count `=`, `+=`, `append`/`extend` on locals, etc. Pipelines and comprehensions score low; accumulator loops score high.

**3. Pipeline / fluent score (PFS)**

Count maximal chains of the form `f(...).g(...)`, `x |> f |> g`, or nested `map(filter(...))` / comprehension depth. Higher PFS at leaves is good *when* chain steps are named combinators—not when chains are opaque getters.

**4. Combinator vocabulary hit rate (CVR)**

Fraction of calls whose callee is in an allowlisted “combinator / domain ops” set (project-configured): e.g. `map`, `filter`, `reduce`, `pipe`, `compose`, query helpers, anaphoric `map _`, domain `Money.add`, etc. Leaves should have high CVR; a leaf that only calls `list.append` / raw arithmetic has low CVR.

**5. Domain-type density (DTD)** — inverse of primitive obsession

\[
\mathrm{DTD}(f) = \frac{\text{annotations/values of non-primitive domain types}}{\text{all annotated/used value types}}
\]

Encourage manipulating `OrderLine`, `NonEmptyList[UserId]`, etc., over bare `int`/`dict`.

**6. Role-conditioned objectives**

| If classified as… | Optimize / gate |
| --- | --- |
| Core (\(F \ge F_{\min}\), not entrypoint) | Maximize \(S\); cap nesting & `v_poly`; LMD low; keep CAR healthy |
| Leaf (entrypoint or \(F\) low + high fan-out) | Maximize CAR, PFS, CVR, DTD; cap LMD; **do not** demand high ETSPA |
| Unclassified helper \(F\le 1\) | Inline or justify; \(S\le 0\) fails |

**7. Portfolio shape ratios**

- Share of tokens in high-\(F\) core vs leaves  
- Median \(F\) of non-entrypoint callables (want a fat mid-layer)  
- Leaf mean CAR / core mean \(S\) as a “dialect health” dashboard  

#### How this tensions with earlier gates

| Earlier pressure | Refined by §2.11 |
| --- | --- |
| Ban fan-in≤1 (§2.9) | Ban for *helpers*; allow for *leaves* with high CAR/CVR |
| Maximize \(\sum S\) (§2.10) | Maximize on **core**; leaves judged on expression metrics |
| Cap method size / CC | Still applies—combinators stay small; leaves stay short *because* they delegate |
| Avoid polymorphism-as-`switch` (§2.8) | Combinators should be data/function composition, not deep class hierarchies per case |

Ideal agent lexicography (replacing §2.9 item 7):

1. Architecture contracts / cycles.  
2. No unpaid poly (§2.8).  
3. Helpers: no new \(F\le 1\) / \(S\le 0\); core \(\sum S\) non-decreasing.  
4. Leaves: LMD non-increasing; CAR/CVR/DTD non-decreasing on touched entrypoints.  
5. Then nesting / `v_poly` / LCOM4.

#### Python / tooling notes

Python lacks C# LINQ/`_` anaphors in the language; the *metric* still applies if the project standardizes on:

- generator expressions / comprehensions over imperative accumulate loops;  
- libraries (`toolz`, `pipe`, `returns`, custom `|>` / anaphor DSL);  
- fluent domain objects.  

CVR’s allowlist is how you encode “this is our LINQ.” Without an allowlist, CAR+LMD+PFS still push away from mutation loops toward call-heavy expression style.

#### Ideal micro-example (what “good” scores like)

```python
# core: high F, low LMD, solid S
field = lambda key: (lambda row: row[key])
gt = lambda n: (lambda x: x > n)
sub_from = lambda n: (lambda x: n - x)

# leaf: low F, high CAR/PFS/CVR, low LMD
result = (
    rows
    |> map(field("field_name"))
    |> filter(gt(10))
    |> map(sub_from(2))
)
```

vs an explicit mutate-and-append loop: higher LMD, lower CAR/CVR, more temps—even if both have similar raw token counts.

---

## 3. Class- and type-level constraints

Function limits alone do not stop God classes: agents happily add “one more method” to the nearest large type. Class metrics enforce **single responsibility** and **low coupling**.

### 3.1 Chidamber–Kemerer (CK) suite (1994)

Foundational OO design metrics:[^ck-ieee][^ck-pdf]

| Metric | Meaning | Anti-spaghetti role |
| --- | --- | --- |
| **WMC** | Sum of method complexities (or method count if unit weights) | Caps “how much is going on” in one type |
| **DIT** | Depth of inheritance tree | Deep hierarchies increase understanding cost |
| **NOC** | Immediate subclasses | High NOC ⇒ wide blast radius of parent changes |
| **CBO** | Distinct coupled classes | High CBO ⇒ fragile, tangled edits |
| **RFC** | Size of response set (local + called methods) | Large RFC ⇒ hard to reason about behavior |
| **LCOM** | Lack of cohesion among methods | High LCOM ⇒ candidate to split |

Empirical and tooling literature treat CK metrics as predictors of maintainability and defect-proneness when used with thresholds, not in isolation.[^ck-cast]

### 3.2 LCOM4 (Hitz & Montazeri, 1995) — highest leverage for agents

**Definition.** Build an undirected graph: methods are nodes; edge if they share an instance field *or* one calls the other. **LCOM4 = number of connected components.**[^lcom4-aivosto][^lcom4-sharma]

| LCOM4 | Interpretation |
| --- | --- |
| 1 | Cohesive — keep |
| ≥ 2 | Split into that many classes |
| 0 | No methods — usually bad |

**Agent constraint.** If `LCOM4 ≥ 2`, forbid adding methods that would create a new component; require split-first. Moderne highlights LCOM4 as the most actionable class metric for agents because the score *is* the refactoring prescription.[^moderne]

### 3.3 Tight Class Cohesion (TCC)

**Definition.** Fraction of method pairs that share at least one instance attribute (directly connected). Range \([0,1]\); higher is more cohesive.[^moderne][^lanza-marinescu]

**Agent use.** Continuous complement to LCOM4. Very low TCC (e.g. \< 0.33) flags incoherent types even when LCOM4 is ambiguous.[^moderne]

### 3.4 Coupling Between Objects (CBO) and the coupling–cohesion quadrant

**CBO:** count of distinct external types referenced via fields, parameters, returns, calls, constructors.[^ck-ieee][^moderne]

Plot **CBO × TCC**:[^moderne]

| | Low CBO | High CBO |
| --- | --- | --- |
| **High TCC** | Healthy | Hub (coherent but fragile) |
| **Low TCC** | Island (messy but isolated) | **Spaghetti** (worst) |

**Agent policy.** Spaghetti quadrant → refactor before feature work. Hub → minimize API surface changes. Island → low-risk cleanup.

### 3.5 God Class, Feature Envy, Data Class (Marinescu / Lanza detection strategies)

Composite thresholds from *Object-Oriented Metrics in Practice* (widely implemented, e.g. PMD GodClassRule):[^lanza-marinescu][^pmd-god][^moderne]

**God Class** when all hold:

- `WMC ≥ 47` (very high)
- `ATFD > 5` (access to foreign data — “few”)
- `TCC < 1/3`

**Feature Envy** (method in wrong type): foreign attribute accesses ≥ 5 and foreign ≫ own (e.g. ≥ 2×).[^moderne]

**Data Class:** mostly getters/setters; behavioral WMC very low — often paired with Feature Envy elsewhere.[^moderne]

These composites are better *optimization targets* than raw WMC alone: they name the design flaw and the usual refactor (Extract Class, Move Method).

### 3.6 Response for a Class (RFC) and inheritance (DIT / NOC)

High RFC means many possible execution paths from a message—hard for agents to safely modify.[^ck-ieee] Very deep DIT or huge NOC increases “change amplification.” Prefer composition over deep inheritance in Python; measure DIT/NOC to catch accidental hierarchy spaghetti.

---

## 4. Module-, package-, and architecture-level constraints

Local cleanliness cannot fix a cyclic import graph. Architecture metrics are the strongest long-horizon anti-spaghetti controls for multi-file Python projects.

### 4.1 Afferent / efferent coupling and instability (Martin)

For a package/category:[^martin-ood]

- **Ca** (afferent): outsiders that depend on this package  
- **Ce** (efferent): packages this one depends on  
- **Instability** \(I = Ce / (Ca + Ce)\) ∈ \([0,1]\)  
  - \(I = 0\): stable (many dependents, few dependencies)  
  - \(I = 1\): unstable (depends on many, few depend on it)

**Abstractness** \(A =\) abstract types / total types. **Distance from main sequence** \(D = |A + I - 1|\) (or normalized form). Packages should lie near the main sequence \(A + I = 1\); corners are:

- **Zone of Pain** \((A≈0, I≈0)\): stable yet concrete — hard to change  
- **Zone of Uselessness** \((A≈1, I≈1)\): abstract and unused  

[^martin-ood][^moderne]

**Agent constraint.** New dependencies should not push stable concrete packages deeper into the Zone of Pain; prefer depending on abstractions at stable boundaries.

### 4.2 Dependency cycles (strongly connected components)

Cycles make independent testing/deployment impossible and are a primary architectural spaghetti signal. Tarjan SCC on the import graph surfaces them; in one large portfolio study, nearly half of packages were cyclic despite existing quality tooling.[^moderne]

**Agent constraint (hard):** zero new cycles; existing cycles only shrink. This is one of the few metrics that is both binary and hard to game without making the graph honestly acyclic.

### 4.3 Information-flow / fan-in × fan-out (Henry & Kafura, 1981)

Procedure complexity \(\propto length \times (fan\text{-}in \times fan\text{-}out)^2\); environmental connectivity predicted change-proneness on UNIX.[^henry-kafura]

**Python mapping.** Fan-in/out of functions and modules (importers × importees, or callers × callees). High fan-in *and* high fan-out “hubs” are structural bottlenecks—agents should not enlarge them without splitting.

**Anti-fragmentation use of fan-in.** The dual failure mode is a swarm of **fan-in ≤ 1** helpers: extracted only to shrink per-method CC/LOC, never reused. High fan-in is evidence of real reuse (and sometimes crosscutting concerns worth centralizing);[^fanin-aspects] a rising share of fan-in-1 methods is evidence of metric gaming. See §2.9.

### 4.4 Layered architecture and forbidden imports (enforcement, not just measurement)

Declarative contracts beat after-the-fact metrics:

| Mechanism | What it enforces |
| --- | --- |
| **Import Linter** layers / forbidden / independence / acyclic_siblings | Directional layering, no cycles between sibling packages, exhaustive layer membership[^import-linter][^seddon-acyclic] |
| **Deply** | YAML-defined layers and cross-layer rules for CI[^deply] |
| **ArchUnitPython** | Dependency direction, cycles, LCOM, abstractness/instability/distance metrics in pytest[^archunit] |

David Seddon’s framing: Python has no built-in dependency-flow language; without contracts, separated packages “creep inexorably together.”[^seddon-meet] An `acyclic_siblings` contract is described as minimal “six lines” to prevent package-level spaghetti.[^seddon-acyclic]

**Agent constraint.** Treat import contracts as *non-negotiable acceptance tests*. Metric optimization without layer rules still allows “clean” modules that violate the intended architecture.

---

## 5. Composite / portfolio signals

### 5.1 Maintainability Index (Oman & Hagemeister, 1992)

Combines Halstead volume, cyclomatic complexity, and LOC into a 0–100 score (Visual Studio variant drops comment term).[^van-deursen][^radon]

**Caution.** Critiqued as size-dominated, averaged in ways that hide hotspots, and inferior to inspecting LOC/complexity distributions directly.[^van-deursen] Prefer as a *dashboard summary*, not an agent primary objective.

### 5.2 Moderne composite debt score

Weighted combination of normalized method metrics to rank refactoring ROI; consumed by agents via repo-local context files rather than remote dashboards.[^moderne]

### 5.3 Test-gap risk

\(\text{risk} \propto \text{complexity} \times \text{callers}\) on untested non-trivial methods.[^moderne] Untested high-CC hubs are where agent edits create production incidents.

---

## 6. Python-specific adaptation notes

| Concern | Recommendation |
| --- | --- |
| Functions vs classes | Many Python codebases are function-first; apply WMC/LCOM analogs to **modules** (cohesion via shared module state / call graph components) as well as classes |
| `match` / `case` | Prefer cognitive complexity over raw CC so flat pattern matches are not punished like nested `if`s[^cognitive-blog][^radon] |
| Duck typing | CBO/ATFD undercount coupling through untyped attributes; supplement with import graph + attribute-access graphs where possible |
| Protocols / ABCs | Count toward abstractness \(A\) in Martin metrics[^martin-ood][^archunit] |
| Dynamic imports | Static tools miss them; ArchUnitPython notes dynamic-import rules as part of the rule surface[^archunit] |
| Existing analyzers | Radon (CC, MI, Halstead), Pylint/mccabe, import-linter, Deply, ArchUnitPython, Pymetrica (layer-aware metrics)[^radon][^pymetrica] |

---

## 7. Recommended constraint suite for agent optimization

Designed to be **multi-objective** so gaming one axis worsens another (see §8).

### Tier A — hard gates (CI / agent must not regress)

1. **No new import cycles**; acyclic sibling packages.[^moderne][^import-linter]  
2. **Layer / forbidden-import contracts** pass.[^import-linter][^deply]  
3. **Changed functions:** `nesting_depth ≤ 3`, `params ≤ 5`, and prefer **`v_poly` (implicit-dispatch–expanded CC) ≤ 10–15** over raw `v(G)` alone; raw CC may still be reported but must not be the sole gate.[^mccabe-tool][^nist-structured][^cmu-spaghetti]  
4. **No unpaid polymorphism:** reject diffs where raw `v(G)` drops but `v_poly`, RFC′, or override fan-out rises via new class-per-branch types (§2.8).  
5. **No unpaid fragmentation:** reject new *helpers* with \(F\le 1\) or \(S\le 0\); do not lower per-method CC while raising NOM/WMC/RFC or lowering core \(\sum S\) (§2.9–2.10). Entrypoint leaves are exempt from the \(F\le 1\) ban when CAR/CVR stay high (§2.11).  
6. **Leaf expression quality:** on touched entrypoints/leaves, LMD non-increasing and CAR (or CVR) non-decreasing (§2.11).  
7. **Changed classes:** do not increase `LCOM4` above 1; do not enter God Class thresholds.[^lcom4-aivosto][^lanza-marinescu]

### Tier B — soft gates (warn / require justification)

8. CBO and TCC quadrant: block growth deeper into high-CBO/low-TCC.[^moderne]  
9. Package \(D\) (distance from main sequence) and Ce growth on stable packages.[^martin-ood]  
10. Fan-in×fan-out hubs must not grow without split; grow the *high-\(F\) simple core* instead of hubs.[^henry-kafura][^code-complete-fan]  
11. Feature Envy / ATFD; Middle Man; domain-type density regressions.[^moderne][^lanza-marinescu][^shotgun]

### Tier C — context for agents (not raw maximize/minimize)

12. Role labels (core vs leaf) + ETSPA / CAR / LMD / PFS / CVR dashboards (§2.10–2.11).  
13. Explicit smell labels (“Inline helper”, “Extract combinator”, “Replace loop with pipeline”) over opaque scores.[^moderne][^shotgun]

### Suggested objective for an optimizing agent

Prefer **lexicographic / constrained optimization**:

1. Satisfy Tier A.  
2. Minimize regressions on Tier B.  
3. Among feasible edits, minimize touch of high debt / high test-gap symbols.

Do **not** maximize Maintainability Index or minimize LOC alone.

---

## 8. Goodhart’s law: why a suite beats a single metric

When a measure becomes a target, it ceases to be a good measure. Agentic loops compress that failure into a single session: tireless optimizers satisfy the literal proxy (specification gaming) or manipulate the scorer (reward tampering).[^goodhart-agent][^goodhart-countdown][^goodhart-tianpan]

**Implications for anti-spaghetti metrics:**

- **Counterbalance.** Low CC + high CBO still spaghetti; low CBO + LCOM4=5 still spaghetti.  
- **Prefer structural boolean constraints** (cycles, layer violations, LCOM4≥2) over smooth scores that can be nudged with cosmetics.  
- **Delta and hotspot metrics** over averages.[^van-deursen]  
- **Keep scorers and contracts read-only** to the agent; enforce via CI hooks, not prompt text alone.[^goodhart-agent]  
- **Human review** on architecture contract changes and God-class splits.

---

## 9. Mapping to `py-code-metrics`

Given this repo’s goal—an executable that scores Python at repo/file/symbol granularity for humans and agents[^readme]—high-ROI additions follow the tiers above:

| Priority | Metric / rule | Level |
| --- | --- | --- |
| P0 | Cyclomatic + **`v_poly` (dispatch-expanded)** + cognitive + nesting | function |
| P0 | **Fan-in + ETSPA on core**; **CAR/LMD/CVR on leaves** (§2.10–2.11) | function / module |
| P0 | Parameter / statement counts (not per-method token minimization) | function |
| P0 | Import graph cycles (SCC) | module |
| P1 | Override fan-out, hierarchy/family WMC, RFC′ | class hierarchy |
| P1 | LCOM4 + TCC + WMC + **NOM** | class (and module analog) |
| P1 | CBO + ATFD; God Class / Feature Envy composites | class / method |
| P1 | Ca, Ce, I, A, D | package |
| P2 | ABC components, Halstead | function |
| P2 | Fan-out / hub detection; call-chain depth | function / module |
| P2 | Emit import-linter–compatible contract stubs | architecture |

Emit machine-readable reports (JSON/CSV) *in-repo* so agents read constraints before editing—the pattern Moderne argues for over remote dashboards.[^moderne]

---

## 10. Summary table: constraints that most reduce spaghetti risk

| Constraint | Prevents | Classic source |
| --- | --- | --- |
| CC / cognitive / nesting caps | Local control-flow spaghetti | McCabe; Campbell; CMU[^mccabe][^cognitive-blog][^cmu-spaghetti] |
| **`v_poly` / RFC′ / override fan-out** | **Inheritance-as-implicit-`switch` gaming** | NIST SP 500-235; NASA SATC[^nist-structured][^nasa-satc] |
| **Fan-in≤1 helpers, NOM/WMC/RFC, ETSPA \(\sum S\)** | **Micro-method fragmentation** | §2.9–2.10 |
| **CAR / LMD / PFS / CVR / DTD (role-conditioned)** | **Imperative twiddling; missing combinator dialect** | §2.11; ABC; Code Complete[^moderne][^code-complete-fan] |
| Param/size caps | Kitchen-sink functions | Pylint / practice[^pylint-design] |
| LCOM4 = 1, TCC high | God / schizophrenic classes | Hitz–Montazeri; Bieman–Kang (TCC)[^lcom4-aivosto][^moderne] |
| CBO bounded; quadrant policy | Tangled types | CK; Moderne[^ck-ieee][^moderne] |
| God Class / Feature Envy rules | Responsibility concentration / misplaced behavior | Lanza & Marinescu[^lanza-marinescu] |
| Acyclic imports + layers | Architectural spaghetti | Martin; Import Linter[^martin-ood][^import-linter] |
| Instability–abstractness fit | Rigid concrete cores | Martin[^martin-ood] |
| Fan-in/out discipline | Hub modules *and* fan-in≤1 dust | Henry & Kafura[^henry-kafura] |

---

## References

[^readme]: Project README, `py-code-metrics` — metrics CLI for constraining human and agentic development.

[^cmu-spaghetti]: Carnegie Mellon University, 18-642 *Avoiding Spaghetti Code* lecture slides — MCC/SCC thresholds, nesting guidance, Spaghetti Factor. <https://course.ece.cmu.edu/~ece642/lectures/09_SpaghettiCode.pdf>

[^mccabe]: Thomas J. McCabe, “A Complexity Measure,” *IEEE Transactions on Software Engineering*, 1976.

[^mccabe-tool]: PyCQA `mccabe` / flake8 — default guidance that complexity beyond 10 is too complex. <https://github.com/pycqa/mccabe>

[^radon]: Radon documentation — cyclomatic complexity definition for Python ASTs, Maintainability Index, Halstead. <https://radon.readthedocs.io/en/master/intro.html>

[^radon-cli]: Radon command-line docs — CC and MI rank tables. <https://radon.readthedocs.io/en/master/commandline.html>

[^pylint-complex]: Pylint `too-complex` / R1260 — McCabe rating default threshold 10. <https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-complex.html>

[^pylint-design]: Pylint design checker messages (`too-many-arguments`, `too-many-statements`, etc.) and common defaults.

[^cognitive-blog]: G. Ann Campbell / Sonar, “Cognitive Complexity, Because Testability ≠ Understandability.” <https://www.sonarsource.com/blog/cognitive-complexity-because-testability-understandability>

[^cognitive-pdf]: SonarSource, *Cognitive Complexity* guide (2023). <https://assets-eu-01.kc-usercontent.com/886afe32-410a-0136-0267-0f7515a29063/39475230-c3ff-4e73-8ab3-fe0c9f21e9dd/Cognitive_Complexity_Sonar_Guide_2023.pdf>

[^sourcegraph-cc]: Sourcegraph, “Cyclomatic complexity: What it is and how to reduce it” — nesting vs CC; cognitive complexity gap; also documents “replace conditionals with polymorphism” as a CC-reduction pattern. <https://sourcegraph.com/blog/cyclomatic-complexity-what-it-is-and-how-to-reduce-it>

[^nasa-satc]: Linda H. Rosenberg (NASA SATC), “Applying and Interpreting Object Oriented Metrics” — low method CC may mean decisions deferred via message passing; CC inadequate alone under inheritance. <https://www.cs.purdue.edu/homes/apm/courses/BITSC461-fall03_SoftwareEngineering/metrics-slides/nasa-rosenberg-study.html>

[^nist-structured]: Arthur H. Watson and Thomas J. McCabe, *Structured Testing: A Testing Methodology Using the Cyclomatic Complexity Metric*, NIST Special Publication 500-235 (1996) — module design complexity `iv(G)`, integration complexity `S1`, object integration complexity, and optimistic/balanced/pessimistic treatment of polymorphic implicit control flow. <https://www.nist.gov/publications/structured-testing-testing-methodology-using-cyclomatic-complexity-metric> (PDF: <https://www.eng.auburn.edu/~kchang/comp6710/readings/Integration.Testing.McCabe.NIST.pdf>)

[^mccabe-iq]: McCabe IQ metrics glossary — `iv(G)`, `S1`, `OS1`, and OO polymorphism-related measures. <https://www.mccabe.com/iq_research_metrics.htm>

[^aivosto-rfc]: Aivosto Project Metrics — RFC / RFC′; polymorphic callees include all possible remote methods. <https://www.aivosto.com/project/help/pm-oo-ck.html>

[^mood-pf]: Fernando Brito e Abreu et al., MOOD metrics — Polymorphism Factor (PF) as system-level overriding density (surveyed in Rodríguez et al., “A Survey of Metrics for OO Design”). <https://www.cc.uah.es/drg/b/RodHarRama00.English.pdf>

[^moderne]: Moderne, “Code Quality Metrics AI Coding Agents Can Actually Use” — method/class/package metrics, coupling–cohesion quadrant, smell thresholds, agent consumption. <https://www.moderne.ai/blog/code-quality-metrics-that-ai-coding-agents-can-actually-use>

[^ck-ieee]: S. R. Chidamber and C. F. Kemerer, “A Metrics Suite for Object Oriented Design,” *IEEE TSE*, 1994. <https://doi.org/10.1109/32.295895>

[^ck-pdf]: Chidamber & Kemerer metrics suite lecture reprint. <https://www.cs.kent.edu/~jmaletic/cs63901/lectures/Chidamber94.pdf>

[^ck-cast]: CAST documentation summarizing WMC, DIT, NOC, CBO, RFC, LCOM. <https://doc.castsoftware.com/export/TG/CMS+Assessment+Model+-+Information+-+CAST+Enforce+Object+Oriented+Metrics+-+Chidamber+and+Kemerer+Metrics+Suite>

[^lcom4-aivosto]: Aivosto Project Metrics — LCOM4 (Hitz & Montazeri) definition and interpretation. <https://www.aivosto.com/project/help/pm-oo-cohesion.html>

[^lcom4-sharma]: Tushar Sharma, “Revisiting LCOM” — LCOM variants including Hitz–Montazeri connected components. <https://www.tusharma.in/revisiting-lcom.html>

[^lanza-marinescu]: Michele Lanza and Radu Marinescu, *Object-Oriented Metrics in Practice*; Marinescu detection strategies (God Class: WMC, TCC, ATFD). See also presentation notes: <https://www.ptidej.net/courses/ift6251/fall05/presentations/050921/050921%20-%20Detection%20Strategies,%20Metrics-Based%20Rules%20for%20Detecting%20Design%20Flaws.pdf>

[^pmd-god]: PMD `GodClassRule` — implements WMC≥47, ATFD>5, TCC<1/3. <https://pmd.sourceforge.io/pmd-5.3.5/pmd-java/xref/net/sourceforge/pmd/lang/java/rule/design/GodClassRule.html>

[^martin-ood]: Robert C. Martin, “OO Design Quality Metrics” — Ca, Ce, Instability, Abstractness, Distance from main sequence. <http://objectmentor.com/resources/articles/oodmetrc.pdf>

[^henry-kafura]: Sallie Henry and Dennis Kafura, “Software Structure Metrics Based on Information Flow,” *IEEE TSE*, 1981. <https://doi.org/10.1109/TSE.1981.231113>

[^fanin-aspects]: Marius Marin, Arie van Deursen, and Leon Moonen, “Identifying Crosscutting Concerns Using Fan-In Analysis,” *ACM TOSEM*, 2007 — high fan-in as reuse/crosscutting signal (inverse: low fan-in is weak reuse). <https://doi.org/10.1145/1314493.1314496>

[^nom-lorenz]: Mark Lorenz and Jeff Kidd, *Object-Oriented Software Metrics* (1994) — Number of Methods (NOM); common guidance on the order of ≤20 methods per class (as summarized in metric catalogues).

[^shotgun]: Fowler / Beck code smells — Shotgun Surgery and Inline Method / Inline Class as remedies for over-split concepts. Overview: <https://deviq.com/code-smells/shotgun-surgery/>

[^small-fns-harmful]: Cindy Sridharan, “Small Functions considered Harmful” — critique of tiny-function dogma and shallow APIs (drawing on Ousterhout’s *A Philosophy of Software Design*). <https://copyconstruct.medium.com/small-functions-considered-harmful-91035d316c29>

[^code-complete-fan]: Steve McConnell, *Code Complete* — high fan-in desirable for lower-level utilities; low-to-medium fan-out elsewhere (commonly cited design rule of thumb). Discussion: <https://stackoverflow.com/questions/4092228/design-principle-high-fan-in-vs-high-fan-out>

[^import-linter]: Import Linter documentation — forbidden, layers, independence, acyclic_siblings contracts. <https://import-linter.readthedocs.io/en/stable/>

[^seddon-meet]: David Seddon, “Meet Import Linter” (2019). <https://seddonym.me/2019/05/20/meet-import-linter/>

[^seddon-acyclic]: David Seddon, “Six lines of code to prevent Python spaghetti” (2025) — `acyclic_siblings` and layering. <https://seddonym.me/2025/11/12/six-lines-of-code/>

[^deply]: Deply — layer-based architectural enforcement for Python. <https://github.com/vashkatsi/deply>

[^archunit]: ArchUnitPython — architecture tests including dependency rules and LCOM / Martin distance metrics. <https://github.com/LukasNiessen/ArchUnitPython>

[^pymetrica]: Pymetrica — AST metrics with layer-aware coupling/instability analysis. <https://github.com/juanjfarina/pymetrica>

[^van-deursen]: Arie van Deursen, “Think Twice Before Using the Maintainability Index” (2014). <https://avandeursen.com/2014/08/29/think-twice-before-using-the-maintainability-index/>

[^stackoverflow-cc]: Discussion of Python CC practice and broader complexity signals (wemake-python-styleguide). <https://stackoverflow.com/questions/38354633/cyclomatic-complexity-metric-practices-for-python>

[^goodhart-agent]: Discussion of agents gaming metrics in optimization loops (Karpathy autoresearch #322). <https://github.com/karpathy/autoresearch/discussions/322>

[^goodhart-countdown]: *Countdown-Code* (arXiv:2603.07084) — reward hacking / Goodhart in code-agent settings. <https://ar5iv.labs.arxiv.org/html/2603.07084>

[^goodhart-tianpan]: Tian Pan, “The Agent Optimized Exactly What You Measured: Goodhart's Law in Agentic Loops” (2026). <https://tianpan.co/blog/2026-05-17-agent-specification-gaming-agentic-loops>
