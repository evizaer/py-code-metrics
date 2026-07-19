# Module-Level Metrics for Deep & Reusable Abstractions Layers

**Purpose.** Decide whether `py-code-metrics` should add **module-native** metrics (beyond rolling up callables), and which combination best drives:

1. **Deep modules** — Ousterhout’s *A Philosophy of Software Design*: maximize $\text{functionality} / \text{interface complexity}$.
2. **Reusable layered components** — Muratori’s [Designing and Evaluating Reusable Components (2004)](https://caseymuratori.com/blog_0024): eliminate *integration discontinuities* so clients can deepen integration gradually across tiers.

**Verdict.** Yes — add module metrics, but **not** as a second copy of function-complexity averages. Use a small complementary board: **interface depth**, **cross-module dependency shape**, and **integration-tier continuity**. Martin package metrics and import cycles remain architecture rails; alone they do not promote depth or gradual reuse. Prefer **delta / hotspot** use over “maximize module depth” global scores.

**Status (2026-07-19).** P1 implemented in-tree: per-module `depth` (MDI, PIW, PTR, import Ca/Ce/I/hub), corpus `overall.module_depth` (Σ PIW, `n_low_mdi`), CLI `module-board` + `board.module_depth` slice. P2 IC / package rollups and P3 layer contracts remain open. Dogfood notes: `[metrics-iteration-log.md](metrics-iteration-log.md)` Round 11.

---



## 1. Why module metrics (and why not only function metrics)

Today’s suite is strong at **callable** and **class** scale (complexity, `v_poly`, ETSPA/`S`, cohesion, DOU) and weak at **module / package** scale: import graph fields (`edge_count`, `cycle_count`, per-module `scc_id`) plus callable aggregates in `ModuleRollup` — no module-native depth/reuse board. See `[docs/metrics.md](metrics.md)` and `[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §4.


| Failure mode                                                    | Function metrics see?           | Module metrics needed                    |
| --------------------------------------------------------------- | ------------------------------- | ---------------------------------------- |
| Shallow “wrapper” module with a wide public API and tiny bodies | Partially (`S≤0`, roles)        | Yes — **module depth** and **API width** |
| Classitis / file-per-case fragmentation                         | Partially (NOM, unpaid helpers) | Yes — **module count × shallowness**     |
| Pass-through layers (same abstraction twice)                    | Weakly                          | Yes — **delegation / signature echo**    |
| Integration cliff (only coarse API, no finer tier)              | No                              | Yes — **granularity ladder** proxies     |
| Stable concrete packages / layer inversion                      | Cycles only                     | Yes — **Ca/Ce/I**, **layer contracts**   |
| Callback-forced / retained-mode-only APIs                       | No                              | Partially — **retention / flow** proxies |


Ousterhout: complexity is dominated by the **worst modules’ interfaces**, not average method CC — function gates can green while the module still leaks decisions.[^ouster-modular] Muratori: reuse fails from **API discontinuities** more than bad algorithms — a **module/API surface** problem (§2).[^muratori-blog][^muratori-notes]

---



## 2. Two philosophies, one target shape



### 2.1 Ousterhout — deep modules

A module is anything with an interface + implementation (function, class, package, subsystem).[^ouster-modular][^softeng-deep]

- **Depth** ≈ functionality / interface complexity (formal signatures + informal obligations: call order, side effects, error modes).
- **Information hiding** is the technique; **information leakage** (same design decision in multiple modules) is the red flag.
- Prefer **pulling complexity downward** so callers stay simple; interface simplicity beats implementation simplicity.
- **Red flags:** thin/shallow modules, classitis, pass-through methods, deep stacks that echo the same arguments, temporal decomposition that splits one decision across layers.[^ouster-modular][^peters-aposd]

General-purpose interfaces are usually deeper than feature-specific ones (book ch. 6); different layers must offer **different abstractions**, not re-exports (ch. 7).

### 2.2 Muratori — reusable components & integration levels

Reuse comes in three shapes:[^muratori-notes][^hecker-api]


| Shape                         | Idea                                                       | Failure mode                                          |
| ----------------------------- | ---------------------------------------------------------- | ----------------------------------------------------- |
| **Layer** (“leaf technology”) | Sits on a standard service (GPU, OS); game only calls down | Needs standards; layers can conflict over one service |
| **Engine**                    | You write a plugin into someone else’s control             | High coupling to their flow                           |
| **Component**                 | Integral subsystem with a **backchannel** to the host      | Hardest API; discontinuities waste work               |


Primary goal: **eliminate integration discontinuities** — cliffs where a small benefit increase requires a huge integration rewrite.[^muratori-notes]

Five observable API characteristics (with tradeoffs):[^hecker-api][^muratori-notes]


| Characteristic   | Pattern     | Direction of goodness                                                       |
| ---------------- | ----------- | --------------------------------------------------------------------------- |
| **Granularity**  | A *or* B+C  | Enough fine steps that coarse ops are not atomic prison                     |
| **Redundancy**   | A *or* B    | Orthogonal/convenient alternatives without forcing one path                 |
| **Coupling**     | A implies B | Always less                                                                 |
| **Retention**    | A mirrors B | Coarse tiers may retain; **finest tier should be immediate / non-retained** |
| **Flow control** | A invokes B | Prefer **caller (game) control**; avoid mandatory callbacks/inheritance     |


Checklist proxies (evaluative, not numerical): immediate-mode equivalents for retained constructs; non-callback equivalents for callback APIs; no forced proprietary datatypes; coarse ops decomposable into ~2–4 finer ops; optional resource/file managers.[^muratori-notes]

### 2.3 Compatible, not identical


| Tension                                                                            | Resolution for metrics                                                                                                                         |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Ousterhout hates shallow pass-through layers; Muratori wants multiple tiers        | **Tiers must change abstraction** (convenience vs primitives), not echo signatures. Measure pass-through separately from multi-granularity.    |
| Ousterhout: fewer, deeper modules; Muratori: more entry points at different grains | Reward **narrow public surface per tier** + **complete ladder**, not “more public functions.”                                                  |
| Clean Code–style tiny methods vs depth                                             | Already opposed by ETSPA/`S` in this project; module metrics must **not** reward file-splitting that creates shallow modules.                  |
| “Layers” in enterprise n-tier vs Muratori layers                                   | Enterprise layer *direction* (Martin / import-linter) is still useful. Muratori’s “layer” is a *reuse shape*. Use both vocabularies carefully. |


---



## 3. What existing literature measures at module/package scale



### 3.1 Martin package metrics (Ca, Ce, I, A, D)

Afferent/efferent coupling, instability $I = Ce/(Ca+Ce)$, abstractness $A$, distance from main sequence $D = |A+I-1|$.[^\wikipedia-pkg][^martin-ood]

Strong for **Stable Dependencies / Stable Abstractions** and zone-of-pain detection. Weak for Ousterhout depth (a stable abstract package can still be a shallow re-export) and for Muratori granularity/retention/flow (no API-tier notion). **Keep as architecture rails**, not the depth/reuse board.

### 3.2 Cycles, layers, skip/back calls

Import SCCs; layer/forbidden contracts (Import Linter, Deply, ArchUnitPython); academic measures of back-calls, skip-calls, cycles, and logical separation.[^import-linter][^arxiv-layers]

These enforce **directional layering**. They do **not** create deep modules — sinkhole / pass-through architectures can satisfy closed layers while violating Ousterhout ch. 7.[^ndepend-layered]

### 3.3 Henry–Kafura / fan-in×fan-out

Environmental complexity $\propto \textit{length} \times (\textit{fan-in} \times \textit{fan-out})^2$.[^\henry-kafura]

At module scale: hubs with high fan-in *and* high fan-out are risk. For depth/reuse prefer **high import Ca with low interface width** (optionally confirmed by high external call fan-in) — not “minimize all coupling.”

### 3.4 Ad-hoc “depth ratio” heuristics

Practitioners approximate Ousterhout depth as implementation size vs interface size (e.g. LOC ≫ interface description; few methods/params).[^wondelai-deep] Size alone is not depth — pair any size ratio with **API width** and **leakage**. Use **body tokens** for implementation mass, not LOC or statements (§4.2).

### 3.5 What this repo already approximates


| Existing signal                                | Relation to depth / reuse                                                |
| ---------------------------------------------- | ------------------------------------------------------------------------ |
| Per-callable `S` / ETSPA, `header_tokens`      | Local depth / amortization — closest to Ousterhout at function scale     |
| Roles `core` / `leaf` / `helper`               | Morphology of reuse vs orchestration                                     |
| Import `edge_count` / `cycle_count` / `scc_id` | Graph presence and cycles — not depth or API tiers                       |
| `ModuleRollup` means/sums                      | **Not** module-native; can hide wide shallow APIs behind “average CC OK” |


---



## 4. Proposed complementary module board

Design rule: **each metric must be hard to game without worsening another**, matching the Goodhart stance in `[anti-spaghetti-research.md](../anti-spaghetti-research.md)`.

### 4.1 Core combination (recommended)

Five axes — a **module board**, not one score:


| #   | Metric (working name)              | Intent                                      | Philosophy link                                                   |
| --- | ---------------------------------- | ------------------------------------------- | ----------------------------------------------------------------- |
| 1   | **Module Depth Index (MDI)**       | Functionality vs public interface cost      | Ousterhout depth                                                  |
| 2   | **Public Interface Width (PIW)**   | Formal interface complexity                 | Ousterhout interface; Muratori coupling surface                   |
| 3   | **Pass-Through Rate (PTR)**        | Same-abstraction echo / middle-man          | Ousterhout ch. 7; false “tiers”                                   |
| 4   | **Dependency Shape (Ca, Ce, hub)** | Responsibility vs fragility                 | Martin + Henry–Kafura                                             |
| 5   | **Integration Continuity (IC)**    | Coarse→fine ladder + flow/retention proxies | Muratori (four of five; Redundancy deferred — see open questions) |


Optional sixth (package/corpus): **layer-contract violations** (enforcement > metric). Corpus anti-split signals: **Σ PIW** and **count of low-MDI modules**.

### 4.2 Definitions (Python-operational)

Ousterhout’s “module” in §2 is conceptual (any interface+implementation unit). **From here on, module means one** `.py` **file** (current report unit), optionally rolled up to a **package** (directory) with the same formulas on the union of public exports and the package import graph. Classitis and “module count × shallowness” are counted at this file/package grain.

**Public membership (default).** Match existing resolve/`is_public`: a name is public iff it does not start with `_`, except dunders (`__x__`) count as public. Do not treat `__all__` as the primary membership rule in P1 (re-exports / `__all__` handling is a known risk — §8).

#### (1) Module Depth Index (MDI)

$$
\mathrm{MDI}(m) = \frac{F_{\mathrm{impl}}(m)}{1 + C_{\mathrm{iface}}(m)}
$$

| Symbol | Proxy |
| --- | --- |
| $C_{\mathrm{iface}}$ | $\sum_{\text{public } f} (1 + n_{\mathrm{params}}(f) + \mathbf{1}_{\mathrm{kwonly}})$ plus weight for public classes’ public methods; optional $+\gamma \cdot H_{\mathrm{public}}$ (header tokens) |
| $F_{\mathrm{impl}}$ | Body **tokens** behind public entrypoints (docstring-stripped `body_tokens`), helpers counted once. **Not** statement counts — compound packing games them. **Not** $\sum S(f)$ (`S` is reuse amortization). Report $\sum \max(S,0)$ on public symbols as a separate reuse check. |

**Interpretation.** High MDI ≈ deep. Low MDI + large PIW ≈ shallow / classitis. Low MDI + tiny $F_{\mathrm{impl}}$ + PIW≈0 ≈ leaf script — label by role, don’t demand library depth.

**Anti-Goodhart.** Don’t hide needed public APIs to raise MDI (pair with import Ca). Don’t pad dead private code (pair with reachability later).

MDI asks whether this file’s public surface buys enough hidden work; ETSPA/`S` asks whether an extract was paid.

#### (2) Public Interface Width (PIW)

$$
\mathrm{PIW}(m) = N_{\mathrm{public\ exports}} + \alpha \cdot \overline{n_{\mathrm{params}}}_{\mathrm{public}} + \beta \cdot N_{\mathrm{public\ types}}
$$

(Coefficients $\alpha$, $\beta$ — see open questions.)

**Interpretation.** Rising PIW without rising import Ca (or corpus Σ PIW exploding via file splits) is classitis / kitchen-sink. Ousterhout: few methods, few args, one-sentence description.[^wondelai-deep]

#### (3) Pass-Through Rate (PTR)

Fraction of public callables whose body is dominated by a single call (or thin wrapper) to another module/class with **high signature similarity** (same arity / overlapping param names / near-identical header tokens).

$$
\mathrm{PTR}(m) = \frac{\lvert \{ f \in \mathrm{Pub}(m) : \mathrm{passthrough}(f) \} \rvert}{\lvert \mathrm{Pub}(m)\rvert}
$$


**Interpretation.** High PTR = shallow layer / decorator theater / “different layer, same abstraction.”[^ouster-modular][^ndepend-layered]

**Muratori note.** A *convenience* tier that calls a *primitive* tier with **different** abstraction (e.g. `UpdateOrientation` → get/set primitives) is **not** pass-through if it encapsulates a real policy. Signature echo across modules is the smell.

#### (4) Dependency shape

Per module (and package). **P1 Ca/Ce are import-graph counts** (distinct modules that import this one / that this one imports). External **call** fan-in/out to public symbols is a related but separate optional signal — do not equate the two in gates.


| Metric                     | Definition                        | Want                                            |
| -------------------------- | --------------------------------- | ----------------------------------------------- |
| **Ca**                     | Distinct importers of this module | High for deep libraries                         |
| **Ce**                     | Distinct modules this one imports | Lower at stable cores                           |
| **I**                      | $Ce/(Ca+Ce)$                      | Cores → low I; apps → high I                    |
| **Hub risk**               | $Ca \times Ce$ (import)           | Don’t grow hubs without split                   |
| **Call fan-in (optional)** | External calls to public symbols  | Confirms Ca when imports undercount dynamic use |


Align with Stable Dependencies: dependencies should point toward **lower I**.[^\wikipedia-pkg]

For depth: prefer **high Ca + low PIW + high MDI** (Unix I/O shape) over **high Ca + high PIW** (popular god module).

#### (5) Integration Continuity (IC) — Muratori board

Static proxies (none replace reading the API; together they catch cliffs). **Redundancy** (Muratori’s fifth characteristic) has no reliable static proxy yet — deferred (open questions).


| Submetric                | Static proxy                                                                                                                                                                                                                                                               | Maps to            |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ |
| **Granularity ladder**   | A public callable is *composite* if it calls ≥K distinct non-public callables in the same package (name heuristics optional later). Ladder holds if each of those callees is also reachable via some other public entry in the same package (or is trivially an accessor). | Granularity        |
| **Coarse-only fraction** | Share of public composites that fail the ladder test                                                                                                                                                                                                                       | Discontinuity risk |
| **Retention pressure**   | Public APIs that register callbacks, require subclassing ABCs to use, or set process-global hooks as the *only* way to customize                                                                                                                                           | Retention + flow   |
| **Flow inversion**       | Ratio of “library calls client” (callback params, abstract methods invoked from lib) vs “client calls library” at the public surface                                                                                                                                       | Flow control       |
| **Coupling traps**       | Public functions that *require* prior calls to sibling setup APIs (detect via undocumented temporal coupling is hard; proxy: module-level mandatory init / ambient globals read on every public entry)                                                                     | Coupling           |


($K$ — see open questions.)

**IC score (optional composite):** penalize high coarse-only fraction, high retention-only customization, high flow inversion; reward convenience + primitive exports in the same package *without* high PTR.

### 4.3 Explicitly *not* in the primary board


| Metric                                        | Why defer / demote                                             |
| --------------------------------------------- | -------------------------------------------------------------- |
| Maintainability Index / average CC per module | Size-dominated; hides shallow wide APIs[^van-deursen]          |
| Raw LOC / statement counts as volume          | Size≠depth; splits and compound packing game them — use body tokens for $F_{\mathrm{impl}}$ |
| Abstractness $A$ alone                        | Python Protocols/ABCs undercount; easy to fake with empty ABCs |
| “Number of classes”                           | Incentivizes classitis (anti-Ousterhout)                       |
| Single “reusability %”                        | Unfalsifiable; Goodhart magnet                                 |


Martin **A** and **D** remain useful as **secondary** package diagnostics once Ca/Ce exist.

---



## 5. Effective combination by integration level

Muratori’s insight: the *right* tradeoff **changes** as integration deepens.[^muratori-notes] Metrics should be **tier-aware**, not one global minimum.

| Integration stage | Client need | Prefer | Metric emphasis |
| --- | --- | --- |
| **Bring-up** | Max benefit / min work | Low granularity, higher retention OK | Low PIW convenience API; MDI of façade; don’t demand primitives yet |
| **Productization** | Replace pieces | Medium granularity, less retention | Falling coarse-only fraction; PTR stays low |
| **Deep integration** | Full control | High granularity, **immediate-mode**, caller flow | IC: primitives exist; retention/flow penalties on *only* path; Ca on primitives |

**Agent policy:**

1. Do **not** fail a module for offering a retained convenience API.
2. **Do** fail (or hotspot) when the **only** customization path is callback/ABC/global retention, or when a coarse API has **no** finer public decomposition while Ce/Ca show it is a shared dependency.
3. Do **not** “fix” depth by inserting pass-through packages (PTR↑).

Measure **whether the common path stays narrow**, not whether advanced APIs exist (Ousterhout: infrequent features are fine if they don’t complicate the common path).[^ouster-modular]

---



## 6. Recommended suite for `py-code-metrics`



### 6.1 Scope and priorities


| Priority | Add                                                                                                                                                            | Role                         |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| **P1**   | PIW, MDI ($F_{\mathrm{impl}}$ = body tokens behind public entrypoints; `header_tokens`/`params` in $C_{\mathrm{iface}}$), module import Ca/Ce | Depth + responsibility board |
| **P1**   | PTR (pass-through / signature-echo)                                                                                                                            | Blocks fake layering         |
| **P1**   | Corpus Σ PIW + count of low-MDI modules (informational / soft)                                                                                                 | Anti file-split gaming       |
| **P2**   | Package rollups of the above + Martin I; hub risk; optional call fan-in                                                                                        | Architecture                 |
| **P2**   | IC submetrics (coarse-only, retention/flow proxies)                                                                                                            | Muratori continuity          |
| **P3**   | Declarative layer contracts (or ingest Import Linter)                                                                                                          | Directional layering         |
| **P3**   | Agent view: `module-board` / path-scoped board                                                                                                                 | Actionability                |


**Do not** replace callable ETSPA/`v_poly`/DOU gates. Module metrics **complement** them: local paid extracts can still create a shallow module if every extract is re-exported.

### 6.2 Agent / gate posture

Mirror existing philosophy (complementary board, delta-first):


| Gate style        | Candidates                                                                                                                                      |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hard (delta)**  | New import cycles; PTR↑ on touched modules with import Ca≥1; PIW↑ without Ca↑ (and without corpus Σ PIW explanation via intentional API growth) |
| **Soft**          | MDI↓ on high-Ca modules; Ce↑ on low-I packages; coarse-only fraction↑; rising low-MDI module count                                              |
| **Informational** | Full IC dashboard; Martin D; hub list; public $\sum S$ reuse check                                                                              |


Avoid a single “maximize MDI” objective — agents will hide exports or bloat private code.

### 6.3 Fit with current positive morphology

Existing target: **high-fan-in simple cores + expressive leaves** (`[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §2.11).


| Morphology                  | Module signature                                                                                    |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| Deep reusable component     | High Ca, low PIW, high MDI, low PTR, IC primitives available                                        |
| Application leaf package    | High I, may have high PIW entrypoints, high CAR and low LMD on leaves — don’t force “library depth” |
| Bad shallow framework layer | High PTR, medium PIW, low MDI, forces flow inversion                                                |


---



## 7. Worked intuition (not prescriptions)

**Unix file I/O** — few calls (`open`/`read`/`write`/`close`), enormous implementation: high MDI, low PIW, high Ca.[^ouster-modular]

**Java-style I/O classitis** — many types, each thin: high PIW corpus-wide, low MDI per type — Ousterhout’s shallow example.[^ouster-modular]

**Granny-style tiered component** — convenience update *and* get/set primitives; optional services (memory/file) not mandatory; immediate-mode at the bottom: high IC, low coupling traps.[^muratori-notes]

**Architecture sinkhole** — every layer forwards untouched: closed layers may pass Martin-style checks while PTR and Ousterhout ch. 7 fail.[^ndepend-layered]

---



## 8. Risks and anti-patterns for metrics authors

1. **Rewarding file splits** — PIW per file falls while system interface explodes; always report **corpus public surface** and **module count of low-MDI files**.
2. **Punishing façades** — a one-call bring-up API is good; pair façades with ladder metrics, don’t ban low granularity.
3. **Counting** `__all__` **wrong** — star-exports and re-export modules need explicit handling (re-export modules often high PTR by design — flag package, not every shim).
4. **Static blindness** — informal interface (ordering, performance, errors) won’t appear in AST; comments/docs are weak proxies. Keep IC as **hotspot hints**, not sole truth.
5. **Conflating Muratori “layer” with n-tier layers** — document vocabulary in UI strings.
6. **Goodhart on abstractness** — empty Protocol proliferation to improve Martin A/D.
7. **Statement-count volume** — don’t drive $F_{\mathrm{impl}}$/MDI with `statements`; compound packing cuts stmt count without cutting logic. Use body tokens; leave nest / cognitive / `v_poly` as the complexity board.

---



## Open questions



### OQ-1: What defaults should $\alpha$, $\beta$, $\gamma$, and $K$ take?

Possible answers:

- Start with $\alpha=\beta=1$, omit $\gamma$ until header-token noise is measured; $K=3$ (Muratori’s “2–4 finer ops” midpoint).
- Fit coefficients on a dogfood corpus so PIW ranks known kitchen-sink modules above known deep cores, then freeze.
- Keep PIW as unweighted export count only in P1; add weighted terms only after false-positive review.



### OQ-2: Should Muratori Redundancy get a static proxy, or stay checklist-only?

Possible answers:

- Defer permanently — orthogonal convenience vs forced single path needs human API reading.
- Weak proxy: count public symbol pairs with high body/callee overlap but divergent param types (alternate encodings).
- Ingest optional API docs / examples that demonstrate two paths for one task.



### OQ-3: How strict should “callee covered by another public entry” be for the granularity ladder?

Possible answers:

- Exact: every non-trivial callee of a composite must appear in some other public function’s call graph in the same package.
- Relaxed: ≥50% of callee set publicly reachable, or all callees with fan-in≥2.
- Name/export based: composite’s package must export a documented primitive set (manual allowlist) — metrics only check PTR and coarse-only against that set.

---



## References

[^muratori-blog]: Casey Muratori, [Designing and Evaluating Reusable Components (2004)](https://caseymuratori.com/blog_0024) — lecture context, layers vs components, integration discontinuity.

[^muratori-notes]: Community notes of the talk (five characteristics, tiering goal, evaluation checklist): [gist:vsapsai](https://gist.github.com/vsapsai/6f524c5095a7ae647f1746c762954f9f); also [gist:uucidl](https://gist.github.com/uucidl/495e7f1c2646fc8b5196). Recording: [YouTube](https://www.youtube.com/watch?v=ZQ5_u8Lgvyk).

[^hecker-api]: Chris Hecker, [API Design](https://chrishecker.com/API_Design) — executive summary of Muratori’s five characteristics.

[^ouster-modular]: John Ousterhout, [Modular Design](https://web.stanford.edu/~ouster/cgi-bin/cs190-spring16/lecture.php?topic=modularDesign) (CS 190) — functionality/interface complexity, information hiding, thick vs thin, red flags.

[^softeng-deep]: [Modules Should Be Deep!](https://softengbook.org/articles/deep-modules) — accessible summary of Ousterhout depth.

[^peters-aposd]: [A Philosophy of Software Design — notes](https://petersnotes.com/books/a-philosophy-of-software-design/) — leakage, shallow modules, better together/apart.

[^wondelai-deep]: [Deep modules reference](https://github.com/wondelai/skills/blob/HEAD/software-design-philosophy/references/deep-modules.md) — practical depth checklist / ratio heuristics.

[^wikipedia-pkg]: [Software package metrics](https://en.wikipedia.org/wiki/Software_package_metrics) — Martin Ca, Ce, I, A, D.

[^martin-ood]: Robert C. Martin, package design metrics (as used in JDepend / Clean Architecture tradition); see also project `[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §4.1.

[^henry-kafura]: Henry & Kafura, information-flow metrics (fan-in × fan-out); see `[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §4.3.

[^import-linter]: David Seddon / Import Linter — layers, forbidden, acyclic siblings; see `[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §4.4.

[^arxiv-layers]: *Redefining measures of Layered Architecture*, [arXiv:2106.03079](https://arxiv.org/pdf/2106.03079) — back-call, skip-call, cycle, logical separation measures.

[^ndepend-layered]: [Layered Architecture: Still a Solid Approach](https://blog.ndepend.com/layered-architecture-solid-approach/) — closed layers vs architecture sinkhole / pass-through.

[^van-deursen]: Critiques of Maintainability Index / averaged complexity; see `[anti-spaghetti-research.md](../anti-spaghetti-research.md)` §5.1.