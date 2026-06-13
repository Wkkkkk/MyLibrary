# Design: `knowledge-library` skill

**Date:** 2026-06-13
**Status:** Approved design — pending implementation plan
**Origin:** Abstracted from the MyBooks project (`~/workspace/playground/mybooks`), which labeled and materialized the 知乎收藏 vault (2095 articles, 86 topics) into a clean library-model Obsidian vault.

---

## 1. Purpose

Turn a growing pile of self-contained, article-sized text units into a **browsable, topic-linked Obsidian library** — not search-only storage. The skill abstracts the MyBooks methodology *and* a de-hardcoded, config-driven copy of its toolkit into a reusable, self-contained package, with a documented extension point for new sources.

### The deciding property (when this skill applies)

The corpus must be **a growing pile of self-contained, article-sized text units you want to browse by subject.** Three per-unit requirements:

1. **Article-sized** — one unit ≈ one thing you'd read in a sitting and summarize in a paragraph.
2. **Self-contained** — classifiable on its own, without its neighbours.
3. **Accumulating** — hundreds to thousands, arriving over time. Below ~50 units the gates and topic graph earn nothing.

### Fits / doesn't fit

- **Native fit:** Zhihu/forum/blog posts, video & podcast transcript summaries, saved web clippings, newsletter issues, RSS reads, paper abstracts, meeting/fleeting notes, research reports.
- **Fits after a chunking step:** books, long PDFs/reports, full papers, documentation sites, course transcripts — anything where one file is too big to be one node. Pre-split into chapter/section summaries.
- **Does NOT fit (the skill should decline):** relational/structured data (contacts, transactions, inventory — that's a database); lookup references (dictionaries, API docs — you *search*, not browse); real-time streams/chat logs (no stable unit); raw media without text (must be summarized first).

---

## 2. Key decisions (locked)

| Decision | Choice |
|---|---|
| Scope | Methodology + extension point, **self-contained** (bundles a config-driven toolkit) |
| Packaging | **Approach A** — one orchestrator skill wrapping a config-driven `librarian/` toolkit |
| Code linkage | Bundle a de-hardcoded, config-driven port of the `mybooks/` modules |
| Autonomy (bootstrap) | Orchestrate the wave loop end-to-end, **pause at the 3 design gates** for sign-off |
| Autonomy (steady-state) | **Autonomous, non-blocking** — accumulate proposals/review into a queue, never halt |
| Sibling-skill coupling | **Loose** — document producers/companions in `references/` + ship 1–2 recipes; no hard calls |
| Scheduling | **Local launchd**, LLM step gated behind "new articles exist" |

---

## 3. Architecture (Approach A)

```
knowledge-library/                 # the skill
├── SKILL.md                       # lean orchestrator: when-to-use + the gated pipeline
├── references/
│   ├── library-model.md           # schema: 1 primary_category + topics + tags + article_type + summary/confidence; the "why"
│   ├── source-adapters.md         # normalized-node contract + producer recipes + chunker note + fits/doesn't-fit test
│   ├── gates.md                   # the 3-gate playbook (audit / triage / review) + heuristics + pause protocol
│   └── lessons.md                 # pitfalls carried from MyBooks (see §8)
├── templates/
│   ├── config.yaml                # the config contract (see §4)
│   └── taxonomy_rules.md          # user fills with their categories
├── schedule/
│   ├── wrapper.sh                 # the steady-state one-command trigger (also the manual entry point)
│   └── com.user.knowledge-library.plist  # launchd template
└── librarian/                     # de-hardcoded, config-driven port of mybooks/
    ├── config.py                  # loads config.yaml → replaces every schema.py constant
    ├── {tsv,manifest,registry,batches,validate,store,cooccur,
    │     hubgen,frontmatter,refile,verify,audit,update,proposals,reconcile}.py
    ├── orchestrate/               # build_wave, ingest_wave, materialize, steady_state, status
    ├── adapters/                  # base.py (contract) + zhihu.py (lead recipe) + markdown_passthrough.py
    └── tests/                     # ported, parameterized by config
```

**Why A:** cohesive, self-contained, good progressive disclosure (the big toolkit is not inlined into `SKILL.md`); each reference/template/module is independently understandable.

---

## 4. The two contracts (the heart of "config-driven + extension point")

### Config contract (`config.yaml`)

Everything currently hardcoded in `mybooks/schema.py` becomes config:

- `corpus_path` (inbox) and `library_path` (output vault)
- locked `categories` list (the primary_category canon)
- `hub_dir`, `hub_min_articles`, `split_threshold`, `skip_dirs`
- topics delimiter, NFC normalization on/off
- labeling knobs: agents-per-wave, articles-per-agent, model
- per-source frontmatter import-field mapping (worked example: Zhihu — see §6)

### Normalized-node contract (adapter output)

Each node = one Markdown file + frontmatter:

- `title`
- `source`
- **stable `source_id` / `url`** — the dedup key. **Not** `content_hash` (it breaks on re-fetch + frontmatter rewrite). This is the MyBooks `manifest.read_url` lesson.
- `interaction_time` / `created`
- body text

Every adapter's only job is to map a source into this shape. This is the extension point: a new source = one small normalizer.

---

## 5. The gated pipeline (SKILL.md workflow — bootstrap mode)

0. **Configure** — fill `config.yaml` + `taxonomy_rules.md`. No canon yet? Derive a starter from the pilot.
1. **Ingest** — run a source adapter/recipe → normalized nodes; chunk books/long docs; build manifest.
2. **Pilot** — label a small sample, seed the topic canon, confirm it.
3. **Wave loop** — `build_wave` → dispatch N parallel labeling agents (read full text + current canon + rules, **self-write JSON**, warned against the 3 recurring slips) → `ingest_wave` + validate → promote good proposed topics. Repeat.
4. **🚦 GATE 1 — 25% taxonomy audit** — pause; revise canon once (splits/merges); sign-off.
5. Finish waves → 100%.
6. **🚦 GATE 2 — proposals triage** — pause; accept/reject/merge proposed topics; sign-off.
7. **🚦 GATE 3 — review queue** — pause; resolve `needs_review` to zero; sign-off.
8. **Materialize (non-destructive)** — frontmatter → category folders (refile) → topic hubs (hubgen) → optional Base view → verify (0 ghosts/0 gaps). Writes a **new** vault; source untouched.

The wave loop's dispatch follows the `dispatching-parallel-agents` pattern.

---

## 6. Composition (loose coupling)

`references/source-adapters.md` documents:

- **zhihu-fetcher** (`~/workspace/playground/zhihu`) — the **lead adapter recipe**. It is the producer that created the original 知乎收藏 corpus, so its output maps 1:1 onto the node contract (`author / url / voteup / interaction_time` frontmatter; `url` = dedup key). Treated as an opaque producer ("scripts never modified, only docs") — referenced, not forked.
- **youtube-watcher** — video/podcast transcript summaries → nodes (second recipe).
- **deep-research** — cited research reports → nodes.
- **book-to-skill** — the book case; used as a **chunker** (chapter/section summaries), since its native output is a skill, not nodes.
- **obsidian-vault** — the post-materialize **companion** for browse/search/wikilinks. Operates on the output; not called during the build.

No hard calls — a missing skill never breaks the pipeline. The Zhihu frontmatter mapping is the worked example in `config.yaml`'s per-source section.

---

## 7. Two operating modes

### Bootstrap (one-time, interactive)

Taxonomy design → wave labeling → the 3 gates → first materialize. "Orchestrate, pause at gates." Run once per library.

### Steady-state (recurring, unattended)

Autonomous and **non-blocking**: when a new article doesn't fit the canon, the run does **not** halt — it labels best-fit, records `proposed_topics` + sets `needs_review`, and moves on. Proposals/review accumulate into a queue you drain interactively on your own cadence (the deferred gate). The recurring job (single `update-library` entry point):

```
1. zhihu-fetcher → inbox        # breakpoint-resume: only pulls new; cookie keep-alive
2. librarian diff --out <lib>   # net-new by url only → zero new = clean no-op, no LLM spend
3. label new (parallel agents)  # only if diff > 0; read current canon + rules
4. file → regen affected hubs → verify (0 ghosts/gaps)
5. emit digest: "N new · M proposed · K flagged"  (from the run ledger, §9)
```

Idempotent (2nd run = 0 new), non-destructive. LLM cost is bounded to net-new; empty pulls cost nothing.

---

## 8. Invariants, error handling, lessons carried over

- `validate.check`: exactly one `primary_category` from canon; topics ∈ active canon; **no category-name-in-topics, no article_type-in-topics** (the 3 recurring agent slips); topic names free of `/ \ :`; enum checks (confidence, bool, topic status).
- `verify`: 0 ghosts (label without file), 0 gaps (file without label), label-count == manifest.
- `materialize` refuses to overwrite (non-destructive); `reconcile` refuses to write unless labels close exactly against the library.
- **NFC-normalize** at every disk↔TSV seam (CJK paths).
- **Frontmatter fence bug** fix: match an exact `---` fence line (`\n---[ \t]*(?:\n|$)`), not `text.find("\n---")` — a multi-line quoted title with `------` was splitting frontmatter and orphaning import meta.
- Deterministic `cooccur` ordering (sort by -weight then name).
- Collision-safe `_N` dest with **move-by-url** semantics.

---

## 9. State & run tracking

**Problem:** today three disjoint ledgers exist and none answers "what did *this run* pull": the fetcher's `history.json` (fetch-side), the library `manifest.tsv` + ephemeral diff, and `progress.tsv` (ingest-batch log, no date/run-id). `labeled_at` is per-row date granularity only.

**Solution — three pieces:**

1. **Run ledger** (`data/runs.tsv`, append-only, one row per steady-state run):
   ```
   run_id · started_at · finished_at · source · fetched · new · labeled · proposed_topics · flagged · status
   ```
   `status` ∈ `ok | nothing_new | auth_failed | error` — surfaces the cookie-expiry caveat as data, not just a log line. The §7 digest = "render the latest ledger row."

2. **Provenance field** — add `first_seen_run` to the label schema, tracing every article back to the run that introduced it. (`labeled_at` = label timing; `interaction_time` = Zhihu save-time — three distinct timestamps.)

3. **`librarian status` command** — reads ledger + manifest + queues, prints on demand:
   ```
   Library: 2095 articles · canon 86 topics
   Last run: 2026-06-13  +3 new, 0 flagged   [ok]
   Pending: 4 proposed topics · 2 needs-review
   History: 14 runs since 2026-05-01 (last auth_failed: never)
   ```

The two lower layers (fetcher history, manifest dedup) stay as-is — they prevent re-download and re-label respectively; the ledger sits above them as the human-facing status.

---

## 10. Scheduling

A bundled `schedule/` with a launchd plist template + a wrapper script:

```
wrapper.sh:  zhihu-fetcher → inbox
             librarian diff --out <library>          # pure Python, no LLM
             [ new>0 ] && claude -p "run update-library steady-state"   # headless, only if new
             write digest → logs/<date>.md  (from run ledger)
```

- Runs **locally** (where the Zhihu cookie lives); empty pulls cost zero LLM.
- `references/lessons.md` flags the **cookie-expiry caveat** + how the digest/run-ledger `status` surfaces a re-auth-needed signal so a silent failure doesn't rot the schedule.
- The wrapper *is* the manual one-command trigger; the launchd plist just calls it on a timer — run by hand until trusted, then enable the plist.

---

## 11. Testing

- Port the existing ~88 MyBooks tests, **parameterized by config** (no hardcoded vault).
- Add **adapter-contract tests** (a node that violates the contract is rejected).
- Add a small **synthetic end-to-end fixture corpus** (~20 nodes) that runs the full pipeline through materialize + verify in a sandbox.
- Add run-ledger / `status` tests (run rows accumulate; `first_seen_run` set on ingest; digest renders).

---

## 12. Build plan composition (how we construct it)

`writing-plans` → `test-driven-development` + `subagent-driven-development` to de-hardcode the modules → `superpowers:writing-skills` / `skill-creator` to assemble the package → `verification-before-completion` + `requesting-code-review` to land it. **Biggest single chunk of work:** threading `config.py` through every module and porting the tests.

---

## Open questions / deferred

- Exact `config.yaml` field names and defaults — settle during implementation.
- Whether `status` and `update-library` are subcommands of one `librarian` CLI or separate entry points — settle during implementation.
- Second shipped adapter recipe: youtube-watcher vs deep-research — pick during implementation.
