# Lessons carried from the MyBooks build

Hard-won pitfalls from materializing the original 知乎收藏 corpus. The toolkit already encodes these; this is the "why" so you don't undo them.

## Dedup by `url`, never by content hash

The cross-vault identity of an article is its stable `url` (`manifest.read_url`). A content hash breaks the moment an article is re-fetched or its frontmatter is rewritten — same article, new bytes — producing phantom "new" articles and duplicate files. The steady-state diff (`steady_state.diff_new`) and the materialize collision handling are both url-keyed.

## NFC-normalize at every disk↔TSV seam

CJK filenames round-trip between APFS (which may store NFD) and the TSVs (NFC). Compare and key everything in NFC, or a `café.md` on disk silently fails to match its `café.md` label → false ghost/gap. Every seam in the toolkit normalizes; preserve that in any new adapter.

## The frontmatter fence bug

Match the closing frontmatter fence as an **exact `---` line** (`\n---[ \t]*(?:\n|$)`), never `text.find("\n---")`. A multi-line quoted title containing `------` was splitting the frontmatter and orphaning the import metadata. `adapters/base._FENCE` and `frontmatter._FENCE` both use the safe pattern.

## Deterministic ordering + collision safety

`cooccur` sorts by `-weight` then name (Counter insertion order is label-order-dependent — not reproducible). Materialize picks a collision-safe `_N` destination with **move-by-url** semantics: a slot already holding the *same* article (same url) is reused; a *different* article never overwrites it.

## Cross-lingual labeling drift

Reading Chinese → emitting an English canon is reliable for a capable model, but English topic drift (`ML` vs `Machine Learning`) is the standing risk. It's contained by `registry.resolve()` (alias resolution) + the proposals gate — not by trusting the model. Keep the labeling prompt explicit: classify into the canon language (named in the assignment header), propose new topics in that language, write the summary in the article's own language.

## Agents don't set frozen fields

`ingest_wave` reconstructs `title` + `content_hash` from the manifest and `original_category` from the legacy labels — agents supply only the judgment fields. An agent can't fabricate provenance even if it emits a wrong `title`. Malformed/non-list agent JSON is surfaced as a structured error (the whole wave blocks), never a crash.

## Cookie-expiry caveat (steady-state)

The zhihu-fetcher runs locally where the cookie lives; an expired cookie makes a scheduled run fetch nothing **silently**. The run-ledger records `status` ∈ `ok | nothing_new | auth_failed | error`, so `python -m librarian.update status` surfaces a re-auth-needed signal as data — a silent failure can't rot the schedule unnoticed. The wrapper sets `auth_failed` on a fetch-side auth error; treat a run of `auth_failed`/`nothing_new` where you expected new articles as "re-login to Zhihu".

## Non-destructive, always

`materialize` writes a **new** vault and refuses to overwrite hand-edited hub notes (no `generated:` marker) or a different article's file. The inbox/source is never mutated except the deliberate move-into-library step. If something looks wrong, the source is intact — re-run.
