# Design: `knowledge-library` semantic search

**Date:** 2026-06-22
**Status:** Approved design — ready for implementation plan.
**Origin:** Extension of the completed `knowledge-library` skill ([2026-06-13 design](2026-06-13-knowledge-library-skill-design.md)). Adds natural-language retrieval over the materialized vault, reusing the existing manifest, label state, and config.

---

## 1. Purpose

Let the user **search the library with natural language** and get back a ranked list of the most relevant vault notes. The corpus is ~2,200 article-sized units, mostly Chinese with some English; queries may be in either language. This is **semantic retrieval only** — find the note, not generate an answer.

The vault already carries, per article, a stable `url` identity plus a `title`, `summary`, `topics`, and `primary_category` in label state and materialized frontmatter. The search layer embeds that content and serves ranked lookups; it does not change how items are ingested, labeled, or materialized.

### The deciding property

Retrieval returns **ranked notes**, not synthesized answers. One vector per article (units are already article-sized). No answer-generation layer, no chunking — both deliberately deferred (YAGNI).

---

## 2. Key decisions (locked)

| Decision | Choice |
|---|---|
| Output | **Ranked list of notes** (semantic retrieval), not RAG answer generation |
| Interface | **CLI subcommand** (`librarian search`) as the core, plus a thin **MCP server** wrapper over the same engine |
| Embedder | **Qwen3-Embedding via local Ollama** — local, private, strong Chinese; behind an `Embedder` interface |
| Language | **One multilingual model** for everything; single shared vector space; cross-language queries work |
| Granularity | **One vector per article** (`title + summary + body`); no chunking |
| Vector store | **Flat SQLite index** in `data_dir`; brute-force cosine (≈2,200 rows → <10ms). No ANN / vector DB |
| Index identity | Keyed by stable `url`; `content_hash` drives incremental re-embedding |
| Index refresh | **Auto via `steady_state`** (embed only the run's deltas) + manual `librarian index [--rebuild]` |
| Model provisioning | **Auto-pull** the model on first index when Ollama is reachable; fail fast only if the daemon is down or the pull fails |
| Front-end | QwenPaw consumes the MCP `search_library` tool (QwenPaw supports MCP clients natively) — same server also serves Claude |
| Testability | Embedder is an interface; the whole pipeline is unit-tested with a deterministic `FakeEmbedder` (no model, no network) |

**Why QwenPaw is a client, not the embedder:** QwenPaw is a personal-assistant framework (LLM + chat-channel + skills/MCP), not an embedding model. It composes as a *front-end* that calls our search tool; the embedding work is done by Qwen3-Embedding.

---

## 3. Architecture

A new `librarian/search/` package alongside the existing toolkit, reusing its config, manifest, and label state. Five single-purpose modules:

```
librarian/search/
├── embedder.py      # Embedder interface + OllamaEmbedder; knows nothing about the vault
├── index_store.py   # SQLite index (data_dir/search_index.db): upsert/delete by url, load matrix + metadata
├── indexer.py       # build orchestration: manifest+labels → hash diff → embed deltas → upsert
├── query.py         # one query: embed → cosine → filter → ranked SearchResult rows
└── mcp_server.py    # thin MCP server exposing search_library; serves Claude + QwenPaw
```

| Module | Responsibility | Depends on |
|---|---|---|
| `embedder.py` | Abstract `Embedder` + `OllamaEmbedder`. Vault-agnostic. | Ollama HTTP, config |
| `index_store.py` | The SQLite store: upsert/delete by `url`, load the full matrix + metadata. Embedding/query-agnostic. | sqlite3, contract |
| `indexer.py` | Read manifest + labels, classify new/changed/deleted by `content_hash`, embed deltas, upsert. | embedder, index_store, manifest, labels |
| `query.py` | Embed the query, cosine vs matrix, apply filters, return ranked results. | embedder, index_store |
| `mcp_server.py` | `search_library` MCP tool over `query.py`. | query |

**Key boundary:** the embedder is an interface, so every pipeline test injects a deterministic stub — no model or Ollama in the unit suite (mirrors how the toolkit stubs `claude -p`). Swapping to an in-process `sentence-transformers` backend later is one new class, no changes elsewhere.

CLI wiring adds two subcommands to the existing entrypoint:

- `librarian index [--rebuild]`
- `librarian search "<query>" [--limit N] [--category C] [--topic T]`

---

## 4. Configuration

New `search:` block in `config.yaml` (defaults shown):

```yaml
search:
  embed_backend: ollama
  ollama_host: http://localhost:11434
  embed_model: qwen3-embedding        # exact tag confirmed at implementation time
  embed_batch_size: 16
  auto_pull: true                     # pull the model on first index if missing; false reverts to fail-with-remediation
  index_path: ./data/search_index.db  # relative to data_dir
  default_limit: 10
```

---

## 5. Data flow

### What represents each article (embedding input)

```
title + "\n\n" + summary + "\n\n" + body
```

Title and summary (both in label state) give a strong topical signal; the body adds detail. The full body is embedded (Qwen3-Embedding handles long context), truncated only if it exceeds the model's token cap. **One vector per article**, no chunking.

### Identity & change detection

Keyed by the stable `url` (the cross-vault identity the toolkit already uses). Each index row stores `content_hash`; an article is re-embedded only when its hash changes, so reindexing is cheap and incremental.

### Index build (`librarian index`)

1. Build the current manifest (`manifest.build`) and load label state.
2. Diff against `search_index.db` by `url` + `content_hash` → `new`, `changed`, `deleted`.
3. Embed `new ∪ changed` in batches via the Ollama embedder.
4. Upsert those rows; delete `deleted` rows.
5. `--rebuild` ignores the diff and re-embeds everything.

### Query (`librarian search "q"`)

1. Embed the query string (same model, query instruction prefix — see §6).
2. Load the vector matrix + metadata from SQLite.
3. Cosine (dot product on L2-normalized vectors) query-vs-all; apply optional `--category`/`--topic` filters on metadata.
4. Return top-N `SearchResult`s: score, title, summary, `primary_category`, `topics`, and vault-relative path (clickable into Obsidian).

### Steady-state hook

After `steady_state` files new items, it calls the same incremental indexer on just that run's added/changed items — index stays fresh hands-off, and a scheduled run never re-embeds the whole corpus.

---

## 6. The embedder & Ollama contract

**Interface** (`search/embedder.py`):

```python
class Embedder(Protocol):
    dim: int
    def embed(self, texts: list[str], *, is_query: bool = False) -> list[list[float]]: ...
```

**`OllamaEmbedder`** posts to a local Ollama instance (`POST {ollama_host}/api/embed`) with the configured model and a batch of texts, returning the vectors.

**Query/document asymmetry:** Qwen3-Embedding is instruction-aware. Document embedding sends raw text; query embedding (`is_query=True`) prepends the recommended task instruction. This is asymmetric by design and improves retrieval. The `FakeEmbedder` ignores the flag.

**Normalization:** vectors are L2-normalized at store time, so query-time cosine is a single matrix-vector dot product over ~2,200 rows.

**Model provisioning** (`librarian index` preflight):

1. **Ollama unreachable** → fail fast with remediation (e.g. `ollama serve`); we can't pull without the daemon.
2. **Model tag missing, Ollama reachable, `auto_pull: true`** → log `pulling <model> (first run, ~Ngb)…`, run `ollama pull <model>`, stream progress, proceed.
3. **Pull fails** (network/disk/bad tag) → surface Ollama's error and stop.
4. **`auto_pull: false`** → revert to fail-with-remediation (air-gapped/CI).

---

## 7. Error handling

Fail fast and loud, matching the toolkit's philosophy.

| Situation | Behavior |
|---|---|
| Ollama daemon unreachable | Stop with remediation (`ollama serve`); never silently fall back. |
| Model tag missing | Auto-pull (§6); only stop if the pull itself fails, surfacing Ollama's error. |
| `search` run but index empty / file absent | Clear message: "no index — run `librarian index` first." Not a stack trace. |
| Index stale (manifest has items not in index) | `search` still returns results, prints a one-line warning with the un-indexed count + refresh command. Doesn't block. |
| Article has no `url` | Skip during indexing; collect into a reconcile-style report at the end so it's visible, not swallowed. |
| Query embedding fails | Surface the error; no partial/garbage ranking. |
| Embedding batch fails mid-index | Abort with the failing batch identified; already-upserted rows persist (resumable next run via the hash diff). |

The store is written transactionally per batch, so an interrupted `index` leaves a consistent (if partial) DB that the next run completes incrementally.

---

## 8. Testing

Same ethos as the existing suite: **no network, no model, no Ollama in unit tests** — the embedder interface is the seam.

- **`FakeEmbedder`** — deterministic vectors from text (hash-seeded, L2-normalized); reproducible similarity, assertable ranking, no real model. Injected by every pipeline test.
- **`index_store`** — upsert/update/delete by `url`; vector-blob round-trip; matrix load in stable row order. Pure SQLite, fast.
- **`indexer`** — hash-diff classification (new/changed/deleted); `--rebuild` re-embeds all; missing-`url` items skipped and reported; assert only deltas get embedded (spy on `FakeEmbedder` call count).
- **`query`** — ranking order with known fake vectors; `--category`/`--topic` filters; `--limit`; empty-index message.
- **`embedder` (OllamaEmbedder)** — request shaping and the query/document asymmetry against a mocked HTTP layer; the auto-pull preflight against a mocked subprocess (reachable+missing → pulls; unreachable → fails). No real Ollama.
- **`mcp_server`** — the `search_library` tool contract: input schema and structured `SearchResult` return shape (calls a stubbed `query`).
- **One opt-in integration test** — real Ollama + real model, marked `@pytest.mark.integration`, skipped by default; run manually for end-to-end validation.

---

## 9. Out of scope (deferred)

- **Answer generation / RAG synthesis** — retrieval only; an LLM answer layer can reuse `query.py` later.
- **Chunking** — units are already article-sized.
- **ANN / dedicated vector DB** — flat cosine is instant at this scale.
- **Hybrid lexical+vector (BM25) search** — pure vector first; revisit if recall gaps appear.
- **`sentence-transformers` in-process backend** — interface supports it; ship Ollama only for now.
