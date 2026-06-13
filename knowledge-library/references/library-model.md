# Library model — the label schema and the "why"

The library is a **browse-by-subject** model, not search-only storage. Each article carries a small, opinionated label set that drives the materialized vault.

## The label record (one row per article)

Columns (`librarian/contract.py` `LABEL_COLUMNS`, TSV at `data_dir/article_labels.tsv`):

| Field | Meaning |
|---|---|
| `relative_path` | the article's path in the vault (the row key) |
| `title` | frozen from the source (agents never set it) |
| `original_category` | the source's own folder/label, kept for provenance |
| `primary_category` | **exactly one**, from the locked English canon — the folder it files into |
| `topics` | reusable subjects from an emerging controlled vocabulary (the topic graph) |
| `tags` | free keywords — people, works, products, events (no vocabulary) |
| `article_type` | controlled form-of-writing (tutorial, Q&A, academic, review, experience-share, …) |
| `summary` | one sentence, **in the article's own language** (never translated) |
| `confidence` | `high` / `medium` / `low` |
| `needs_review` / `review_reason` | the deferred-gate flag |
| `proposed_topics` | topics the agent wants but that aren't in the canon yet |
| `content_hash`, `extractor_version`, `labeled_at`, `first_seen_run` | provenance — `first_seen_run` traces the article to the run that introduced it |

## Why these choices

- **One `primary_category`, locked canon.** A single home folder makes the vault browsable; a locked English-canonical list (set in `config.categories`) keeps folders stable. Co-primaries fracture the hierarchy — forbidden.
- **Topics, not folders.** Topics are a *graph* (a topic hub-note links its articles + related/parent/child topics), so an article lives in one folder but appears under many topics. The vocabulary *emerges* — agents propose, you promote at the proposals gate (`references/gates.md`).
- **Tags are free.** Named entities don't need a controlled vocabulary; they're search fodder, not browse structure.
- **`article_type` is orthogonal** to subject — it answers "what kind of writing", enabling "show me all tutorials in this category".

## Language (English-canonical, Chinese-display)

The controlled vocabulary is **English-canonical**: agents read native-language bodies and emit English `primary_category`/`topics`/`tags`/`article_type`; `summary` + bodies stay source-language. Chinese (or any target) is a **display localization** applied only at materialize via `--lang en|zh`:

- **Categories** localize via `config.category_localization` (`{<English canonical>: {zh: <中文>}}`).
- **Topics** localize via the registry's `name_zh` column (beside the canonical `name`).
- `--lang en` (default) renders the canon verbatim, zero lookup; `--lang zh` drives folder names, hub-note filenames, and hub section headers. The stored canon stays English; article frontmatter is not localized.

A library is **single-display-language**: pick the `--lang` at first materialize and keep it (the idempotent re-run keeps articles at their localized paths).

## The topic registry (`data_dir/topics.tsv`)

Columns: `topic_id, name, aliases, parent_topic, status, description, created_at, name_zh`. `status` ∈ `active | proposed | merged`. `registry.resolve()` maps a name or alias to its canonical active name; aliases may redirect a *merged* name but never shadow an active/proposed one. `validate` accepts a topic only if it's active in the registry OR re-declared in that row's `proposed_topics`. This is the guard that contains English topic drift (`ML` vs `Machine Learning`).
