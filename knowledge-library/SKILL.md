---
name: knowledge-library
description: Use when turning a growing pile of self-contained, article-sized text units (Zhihu/blog/forum posts, video & podcast transcript summaries, saved clippings, newsletter issues, RSS reads, paper abstracts, meeting notes) into a browsable, topic-linked Obsidian library — not search-only storage. Triggers: hundreds-to-thousands of accumulating notes you want to browse by subject; "organize my saved articles", "build a topic library", "label and file my notes", "knowledge base from my reading".
---

# Knowledge Library

## Overview

Turn a growing pile of **self-contained, article-sized text units** into a **browsable, topic-linked Obsidian library**. A bundled config-driven Python toolkit (`librarian/`) does the deterministic work — manifest, validation, wave labeling, materialize, verify, run-ledger; this skill orchestrates it and **pauses at three design gates** for your sign-off.

**Core idea:** classify each unit into one locked `primary_category` (English-canonical) + reusable `topics` + free `tags`, then materialize a non-destructive vault of category folders + topic hub-notes. Labels are written by parallel LLM agents reading full text; the toolkit enforces every invariant.

## When to Use

The corpus must be **a growing pile of self-contained, article-sized text units you want to browse by subject.** Three per-unit requirements:

1. **Article-sized** — one unit ≈ one thing you'd read in a sitting and summarize in a paragraph.
2. **Self-contained** — classifiable on its own, without its neighbours.
3. **Accumulating** — hundreds to thousands, arriving over time. Below ~50 units the gates and topic graph earn nothing.

- **Fits:** Zhihu/forum/blog posts, video/podcast transcript summaries, saved web clippings, newsletter issues, RSS reads, paper abstracts, meeting/fleeting notes.
- **Fits after chunking:** books, long PDFs/reports, papers, docs sites, course transcripts — pre-split into chapter/section summaries first.
- **Does NOT fit (decline):** relational/structured data (contacts, transactions — that's a database); lookup references (dictionaries, API docs — you *search*, not browse); real-time streams/chat logs (no stable unit); raw media without text (summarize first).

See `references/source-adapters.md` for the fits/doesn't-fit test + the node contract.

## Two operating modes

- **Bootstrap** (one-time, interactive): design taxonomy → wave-label the corpus → the 3 gates → first materialize. Run once per library. The gated pipeline below.
- **Steady-state** (recurring, unattended): a new article that doesn't fit the canon does **not** halt the run — it's labeled best-fit, records `proposed_topics` + `needs_review`, and the queue is drained on your own cadence. See `schedule/` + the Steady-state section below.

## Setup (once)

1. Copy `templates/config.yaml` → `config.yaml`; fill `corpus_path` (inbox), `library_path` (output vault), `data_dir`, and the locked English-canonical `categories`. Set `export KNOWLEDGE_LIBRARY_CONFIG=/abs/path/config.yaml`.
2. Copy `templates/taxonomy_rules.md` → a `rules/taxonomy_rules.md` next to your `data_dir`; fill in your category boundaries. No canon yet? Derive a starter from the pilot (step 2 of the pipeline).
3. Ingest a source into the inbox with an adapter (`references/source-adapters.md`): the lead recipe is the zhihu-fetcher; a generic Markdown directory uses `markdown_passthrough`.

All commands below assume `KNOWLEDGE_LIBRARY_CONFIG` is set and you run from the skill root.

## The gated pipeline (bootstrap)

Run the wave loop; **stop and get sign-off at each 🚦 gate** (the playbook is `references/gates.md`).

1. **Inventory** — confirm an adapter has populated the inbox. The wave builder scans it directly (`manifest.build`), so bootstrap needs no manifest snapshot; `python -m librarian.update status` shows library/canon size anytime.
2. **Pilot** — build one small wave, label it, seed the topic canon, confirm it.
3. **Wave loop** — repeat until 100% labeled:
   - `python -m librarian.orchestrate.build_wave <wave_no>` → per-agent assignment files in `data/wave_assign/`.
   - **Dispatch N parallel labeling agents** (N = `agents_per_wave`; one per assignment file), each reading the full article text + the active canon + `taxonomy_rules.md`, self-writing a JSON array to `data/wave_out/` (one object per article: `relative_path, primary_category, topics, tags, article_type, summary, confidence, needs_review, review_reason, proposed_topics`). Follow `superpowers:dispatching-parallel-agents`. Use the model in `config.label_model`.
   - `python -m librarian.orchestrate.ingest_wave` → validates against the canon + merges. Off-canon/fabricated rows block the whole wave (fix + re-ingest).
4. **🚦 GATE 1 — 25% taxonomy audit** — pause; revise the canon ONCE (splits/merges); sign-off. Then finish the waves.
5. **🚦 GATE 2 — proposals triage** — `python -m librarian.update proposals` lists pending; accept good ones with `--accept`; sign-off.
6. **🚦 GATE 3 — review queue** — resolve `needs_review` rows to zero; sign-off.
7. **Materialize (non-destructive)** — `python -m librarian.update materialize --write [--out <library>] [--lang en|zh]`: frontmatter → category folders → topic hubs → verify. Writes a **new** vault; source untouched. `--lang en` (default) renders the English canon verbatim; `--lang zh` localizes folders + hub names + section headers. Then `python -m librarian.update verify` must report **0 ghosts / 0 gaps**.

## Steady-state (recurring)

The bundled `schedule/wrapper.sh` is the one-command trigger (also runs by hand): zhihu-fetcher → inbox; `python -m librarian.update diff --out <library>` (net-new by url, no LLM); if new>0, dispatch a labeling wave + run `orchestrate.steady_state.finish` (ingest → materialize → verify → append a run-ledger row); write a digest from the ledger. Empty pulls cost zero LLM. Enable on a timer via `schedule/com.user.knowledge-library.plist` once trusted. **Cookie-expiry caveat:** see `references/lessons.md` — the run-ledger `status` surfaces a re-auth signal so a silent fetch failure doesn't rot the schedule. Check `python -m librarian.update status` anytime.

## Invariants (the toolkit enforces; never bypass)

Exactly one `primary_category` from the locked English canon; topics ∈ active canon (or declared in `proposed_topics`); no category-name or article_type in topics; materialize never overwrites; verify closes 0 ghosts / 0 gaps / label-count == manifest. Full list + the "why": `references/library-model.md` and `references/lessons.md`.

## References

- `references/library-model.md` — the label schema + why one primary_category + topics + tags.
- `references/source-adapters.md` — the normalized-node contract + producer recipes + chunker note + fits test.
- `references/gates.md` — the 3-gate playbook, heuristics, and pause protocol.
- `references/lessons.md` — pitfalls carried from the MyBooks build (dedup by url, NFC, fence bug, cookie expiry).
- `templates/config.yaml`, `templates/taxonomy_rules.md` — fill-in contracts.
- `schedule/wrapper.sh`, `schedule/com.user.knowledge-library.plist` — steady-state trigger + launchd timer.
