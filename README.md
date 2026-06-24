# MyLibrary

Home of the **`knowledge-library`** agent skill — a reusable abstraction of the one-off
MyBooks pipeline.

It turns a growing pile of self-contained, article-sized text units (Zhihu saves, video/podcast
summaries, web clippings, research reports, book-chapter summaries) into a **browsable,
topic-linked Obsidian library**: a config-driven Python toolkit (`librarian/`) designs a
library-model taxonomy, labels every item with parallel LLM agents, builds a topic knowledge
graph, and materializes a clean vault — plus an autonomous **steady-state** mode that pulls and
files new items on a schedule.

## Layout

- [`knowledge-library/`](knowledge-library/) — the skill itself: `SKILL.md` (orchestrator),
  the `librarian/` Python toolkit, `references/`, `templates/`, and `schedule/` (launchd wrapper
  for steady-state runs).
- [`docs/specs/`](docs/specs/) — the design spec (source of truth).
- [`docs/superpowers/plans/`](docs/superpowers/plans/) — the executed implementation plans.

## Two operating modes

- **Bootstrap** (one-time, interactive): design taxonomy → wave-label the corpus → three design
  gates → first materialize.
- **Steady-state** (recurring, unattended): new items that don't fit the canon are labeled
  best-fit, flagged for review, and filed without halting the run.
- **Semantic search** (optional): natural-language retrieval over the materialized library via a
  local Qwen3-Embedding model (Ollama); index with `python -m librarian.update index`, query with
  `python -m librarian.update search`, or expose as an MCP tool for Claude.

## Day-to-day: adding new articles

### Fully automatic (recommended)

A launchd agent (`adopt/com.kunwu.knowledge-library.plist`) runs the pipeline every Friday at 10:00. Empty inbox = zero LLM cost.

**Install once:**

```sh
# Verify it works by hand first
KNOWLEDGE_LIBRARY_CONFIG=/Users/kunwu/Workspace/MyLibrary/adopt/config.yaml \
LIBRARY=/Users/kunwu/Obsidian/知乎收藏_v2 \
bash knowledge-library/schedule/wrapper.sh

# Install the agent
cp adopt/com.kunwu.knowledge-library.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.kunwu.knowledge-library.plist
```

After that: drop articles into `adopt/inbox/` and the pipeline runs on its own.

```sh
# Watch the logs
tail -f knowledge-library/logs/launchd.out.log

# Check run history and queue sizes anytime
KNOWLEDGE_LIBRARY_CONFIG=adopt/config.yaml python -m librarian.update status
```

**Disable:**

```sh
launchctl unload ~/Library/LaunchAgents/com.kunwu.knowledge-library.plist
```

### Manual trigger (one-off)

```sh
KNOWLEDGE_LIBRARY_CONFIG=/Users/kunwu/Workspace/MyLibrary/adopt/config.yaml \
LIBRARY=/Users/kunwu/Obsidian/知乎收藏_v2 \
bash knowledge-library/schedule/wrapper.sh
```

### Natural language prompt (to Claude Code)

```
New zhihu articles have been added to adopt/inbox/. Run steady-state ingest and update the semantic search index.
```

## Status

**Complete and merged to `main`; live in production.** Plans 1–5 (toolkit de-hardcode, ingest
path + adapters, materialize `--lang en|zh` + localization, state/run tracking, steady-state
Python) plus skill packaging are all implemented and merged. The skill has been run against a real
~2,200-file Obsidian vault, with subsequent pilot-driven bug fixes.

- Design spec: [`docs/specs/2026-06-13-knowledge-library-skill-design.md`](docs/specs/2026-06-13-knowledge-library-skill-design.md)

## Tests

Run from `knowledge-library/`:

```sh
pytest
```

Use the bare `pytest` command (it resolves to a Python 3.11 env with pytest); `python -m pytest`
will fail because the default `python` is 3.14 without pytest installed.
