# Source adapters — the node contract and producer recipes

A **source adapter** maps some producer's output into the normalized-node contract. That's its only job. A new source = one small normalizer; everything downstream (manifest, labeling, materialize, verify) is source-agnostic.

## The fits / doesn't-fit test

Apply BEFORE adapting a source (see SKILL.md "When to Use" for the full criteria). The unit must be **article-sized, self-contained, and accumulating**. If a source produces units that need their neighbours to classify (chat logs), or that you *search* rather than *browse* (API docs), or that are structured records (transactions) — **decline**, or pre-chunk (books/long PDFs → chapter/section summaries) until each piece is a standalone node.

## The normalized-node contract

Each node = one Markdown file + YAML frontmatter. Required fields (`librarian/adapters/base.py` `REQUIRED_FIELDS`):

- `title`
- `source` — the producer name (doubles as the inbox subfolder)
- **`url`** — the stable identity and **dedup key**. NOT a `content_hash` (a hash breaks on re-fetch + frontmatter rewrite; the url survives). This is the central MyBooks `manifest.read_url` lesson.

Recommended: `interaction_time` / `created` (a timestamp). The body is the Markdown after the frontmatter. `ingest_to_inbox` validates every node, NFC-normalizes names + bodies, dedups by `url` across the whole inbox (idempotent re-runs), and appends `_N` on a same-name/different-url collision — a node that violates the contract is rejected, never written.

## Shipped adapters (`librarian/adapters/`)

- **`zhihu.py` (lead recipe).** The zhihu-fetcher (`~/workspace/playground/zhihu`) already emits the contract verbatim (`title / author / source: zhihu / url / voteup / interaction_time` frontmatter, `url` = dedup key), so this adapter is a pure pass-through over its output directory. Treat the fetcher as an **opaque producer** — referenced, never forked.
- **`markdown_passthrough.py` (generic).** Any directory of frontmatter'd Markdown. Injects `source: <name>` when absent; everything else (notably `url`) must already satisfy the contract or the node is rejected.

## Adding a new source

Write a subclass of `adapters.base.Adapter`: set `name` (the inbox subfolder) and implement `nodes(src_dir)` yielding `(filename, text)` pairs where `text` is a full node Markdown string. Run it through `base.ingest_to_inbox(adapter, src_dir, cfg)`. Map source-specific fields to the contract in `nodes()`; let `ingest_to_inbox` enforce validity.

## Companion recipes (documented, not bundled)

- **youtube-watcher / deep-research** — video/podcast transcript summaries and cited research reports → nodes (each is a thin normalizer like zhihu).
- **book-to-skill** — the book case as a **chunker**: chapter/section summaries become nodes (its native output is a skill, not nodes).
- **obsidian-vault** — the post-materialize **companion** for browse/search/wikilinks. Operates on the output vault; not called during the build.

No hard calls — a missing companion never breaks the pipeline.
