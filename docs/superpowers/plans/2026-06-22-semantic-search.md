# Knowledge-Library Semantic Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add natural-language semantic search over the materialized vault: local Qwen3-Embedding (via Ollama) embeds each article into a flat SQLite vector index, queryable from a `librarian` CLI subcommand and an MCP `search_library` tool.

**Architecture:** A new `librarian/search/` package (settings → embedder → index_store → indexer → query → mcp_server) reusing the existing config, manifest, and label state. The embedder sits behind an interface so the whole pipeline is unit-tested with a deterministic `FakeEmbedder` (no model, no network). Two CLI subcommands (`index`, `search`) are added to the existing `python -m librarian.update` dispatcher via lazy imports; a thin MCP server wraps the same `query` engine for Claude and QwenPaw. Steady-state refreshes the index incrementally after each materialize.

**Tech Stack:** Python 3.11, numpy (already installed), stdlib `sqlite3` + `urllib` (Ollama HTTP) + `subprocess` (auto-pull), `mcp` (MCP server only). Local Ollama serving `qwen3-embedding`.

**Spec:** `docs/specs/2026-06-22-knowledge-library-semantic-search-design.md`

## Global Constraints

- **Working directory for all commands:** `knowledge-library/` (the package root; `conftest.py` puts it on `sys.path`).
- **Tests run with bare `pytest`** — it resolves to the Python 3.11 env that has numpy + pytest. `python -m pytest` fails (default `python` is 3.14 without pytest). This is an existing repo rule (see `README.md`).
- **Search/index CLI commands need numpy**, so run them under the numpy-equipped interpreter (the same Python 3.11 pytest uses), e.g. `/opt/homebrew/opt/python@3.11/bin/python3.11 -m librarian.update index`. Non-search commands are unaffected because search modules are imported lazily inside the handlers.
- **Label-row column indices** (`librarian/contract.py:LABEL_COLUMNS`): `relative_path=0, title=1, primary_category=3, topics=4, summary=7, content_hash=12`. Article bodies are read from `cfg.library_path / relative_path`.
- **Article identity is the stable `url`** (read via `manifest.read_url(path)`); `content_hash` drives incremental re-embedding. Articles with no `url` are skipped and reported, never silently dropped.
- **Vectors are L2-normalized at store time**, so query-time cosine similarity is a plain dot product.
- **TDD throughout:** failing test first, minimal code, green, commit. New tests go in `librarian/tests/test_*.py`.
- **Branch:** `feat/semantic-search` (already created). Commit after each task.
- **Existing patterns to match:** TSV/store access via `librarian.store`/`librarian.tsv`; config via `librarian.config.Config`; CLI handlers follow `cmd_audit`/`cmd_materialize` in `update.py` (lazy submodule import inside the function).

## Prerequisites: Ollama setup (runtime, not a code task)

The unit suite never touches Ollama (it uses `FakeEmbedder`). These checks are for actually running `index`/`search` and the manual end-to-end:

1. **Is Ollama installed?** `ollama --version` — if not, download from <https://ollama.com/download>.
2. **Is the embedding model pulled?** `ollama list | grep qwen3-embedding` — if absent, `ollama pull qwen3-embedding:8b` (the `ensure_model` preflight in Task 3 also auto-pulls it on first `index` when `auto_pull: true`).

Set `search.embed_model` in `config.yaml` to the exact tag you pulled (e.g. `qwen3-embedding:8b`). The `8b` tag is the highest-quality local option; `qwen3-embedding:4b`/`:0.6b` trade accuracy for speed/size.

---

### Task 1: Search settings resolver + config plumbing

Adds a `search:` config block and a `SearchSettings` resolver that centralizes all search defaults and resolves the index path against `data_dir`.

**Files:**
- Modify: `knowledge-library/librarian/config.py` (add `search` field + load it)
- Create: `knowledge-library/librarian/search/__init__.py` (empty)
- Create: `knowledge-library/librarian/search/settings.py`
- Test: `knowledge-library/librarian/tests/test_search_settings.py`

**Interfaces:**
- Consumes: `librarian.config.Config` (gains a `search: dict` attribute; `data_dir: Path`).
- Produces:
  - `librarian.search.settings.SearchSettings` dataclass with fields: `embed_backend: str`, `ollama_host: str`, `embed_model: str`, `embed_batch_size: int`, `auto_pull: bool`, `index_path: Path` (absolute), `default_limit: int`.
  - `librarian.search.settings.from_config(cfg) -> SearchSettings`.
  - `librarian.search.settings.QUERY_INSTRUCTION: str`.

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_search_settings.py`:

```python
from pathlib import Path
from librarian import config
from librarian.search import settings as ss


def _cfg(tmp_path, search=None):
    return config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "data", categories={"文学"},
        search=search or {})


def test_defaults_when_no_search_block(tmp_path):
    s = ss.from_config(_cfg(tmp_path))
    assert s.embed_backend == "ollama"
    assert s.ollama_host == "http://localhost:11434"
    assert s.embed_model == "qwen3-embedding"
    assert s.embed_batch_size == 16
    assert s.auto_pull is True
    assert s.default_limit == 10
    # relative index_path resolves under data_dir
    assert s.index_path == tmp_path / "data" / "search_index.db"


def test_overrides_and_host_trailing_slash(tmp_path):
    s = ss.from_config(_cfg(tmp_path, {
        "embed_model": "qwen3-embedding:4b", "ollama_host": "http://h:1234/",
        "auto_pull": False, "default_limit": 5, "embed_batch_size": 8}))
    assert s.embed_model == "qwen3-embedding:4b"
    assert s.ollama_host == "http://h:1234"   # trailing slash stripped
    assert s.auto_pull is False
    assert s.default_limit == 5
    assert s.embed_batch_size == 8


def test_absolute_index_path_kept(tmp_path):
    s = ss.from_config(_cfg(tmp_path, {"index_path": "/abs/idx.db"}))
    assert s.index_path == Path("/abs/idx.db")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_search_settings.py -v`
Expected: FAIL — `Config.__init__() got an unexpected keyword argument 'search'` (and/or `ModuleNotFoundError: librarian.search`).

- [ ] **Step 3: Add the `search` field to Config and load it**

In `knowledge-library/librarian/config.py`, add the field to the `Config` dataclass (after `category_localization`):

```python
    category_localization: dict = field(default_factory=dict)
    search: dict = field(default_factory=dict)
```

In `load()`, add `"search"` to the optional-key copy loop:

```python
    for key in ("hub_dir", "generated_marker", "hub_min_articles",
                "topic_split_threshold", "batch_size", "legacy_labels_name",
                "label_language", "category_localization",
                "agents_per_wave", "articles_per_agent", "extractor_version",
                "label_model", "search"):
        if key in raw:
            kwargs[key] = raw[key]
```

- [ ] **Step 4: Create the search package + settings resolver**

Create empty `knowledge-library/librarian/search/__init__.py`.

Create `knowledge-library/librarian/search/settings.py`:

```python
"""Resolve the `search:` config block into a typed SearchSettings, applying
defaults (spec §4) and resolving index_path against data_dir. Keeps all search
defaults in one place so core config.py only stores the raw dict."""
from dataclasses import dataclass
from pathlib import Path

# Prepended to query text only (document text is embedded raw) — Qwen3-Embedding
# is instruction-aware and this asymmetry improves retrieval (spec §6).
QUERY_INSTRUCTION = ("Instruct: Given a search query, retrieve relevant "
                     "library articles that answer it\nQuery: ")

DEFAULTS = {
    "embed_backend": "ollama",
    "ollama_host": "http://localhost:11434",
    "embed_model": "qwen3-embedding",
    "embed_batch_size": 16,
    "auto_pull": True,
    "index_path": "search_index.db",
    "default_limit": 10,
}


@dataclass
class SearchSettings:
    embed_backend: str
    ollama_host: str
    embed_model: str
    embed_batch_size: int
    auto_pull: bool
    index_path: Path
    default_limit: int


def from_config(cfg):
    raw = dict(DEFAULTS)
    raw.update(getattr(cfg, "search", None) or {})
    index_path = Path(str(raw["index_path"])).expanduser()
    if not index_path.is_absolute():
        index_path = cfg.data_dir / index_path
    return SearchSettings(
        embed_backend=str(raw["embed_backend"]),
        ollama_host=str(raw["ollama_host"]).rstrip("/"),
        embed_model=str(raw["embed_model"]),
        embed_batch_size=int(raw["embed_batch_size"]),
        auto_pull=bool(raw["auto_pull"]),
        index_path=index_path,
        default_limit=int(raw["default_limit"]),
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest librarian/tests/test_search_settings.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add librarian/config.py librarian/search/__init__.py librarian/search/settings.py librarian/tests/test_search_settings.py
git commit -m "feat(search): SearchSettings resolver + search config block"
```

---

### Task 2: SQLite index store

The persistence layer: one SQLite file holding one row per article (metadata + a float32 vector blob) plus a meta table. Knows nothing about embeddings or queries.

**Files:**
- Create: `knowledge-library/librarian/search/index_store.py`
- Test: `knowledge-library/librarian/tests/test_index_store.py`

**Interfaces:**
- Consumes: numpy; a `Path` for the db file.
- Produces: `librarian.search.index_store.IndexStore` with:
  - classmethod `open(path: Path) -> IndexStore`
  - `upsert(records: list[dict])` — each dict has keys `url, relative_path, title, summary, primary_category, topics, content_hash, vector` (vector = sequence of floats); commits.
  - `delete(urls: list[str])` — commits.
  - `hashes() -> dict[str, str]` — `{url: content_hash}`.
  - `load_matrix() -> tuple[list[dict], np.ndarray]` — metadata dicts (keys: `url, relative_path, title, summary, primary_category, topics, content_hash`) and an `[n, dim]` float32 matrix, both ordered by `url`.
  - `count() -> int`
  - `get_meta(key) -> str | None`, `set_meta(key, value)`
  - `close()`

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_index_store.py`:

```python
import numpy as np
from librarian.search.index_store import IndexStore


def _rec(url, h, vec):
    return {"url": url, "relative_path": f"文学/{url}.md", "title": f"t-{url}",
            "summary": "s", "primary_category": "文学", "topics": "a; b",
            "content_hash": h, "vector": vec}


def test_upsert_roundtrip_and_matrix_order(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("b", "h2", [0.0, 1.0]), _rec("a", "h1", [1.0, 0.0])])
    metas, matrix = store.load_matrix()
    assert [m["url"] for m in metas] == ["a", "b"]      # ordered by url
    assert matrix.shape == (2, 2)
    assert matrix.dtype == np.float32
    np.testing.assert_allclose(matrix[0], [1.0, 0.0])
    assert metas[0]["primary_category"] == "文学"
    assert store.count() == 2


def test_upsert_updates_in_place(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("a", "h1", [1.0, 0.0])])
    store.upsert([_rec("a", "h2", [0.0, 1.0])])
    assert store.count() == 1
    assert store.hashes() == {"a": "h2"}
    _, matrix = store.load_matrix()
    np.testing.assert_allclose(matrix[0], [0.0, 1.0])


def test_delete_and_empty_matrix(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("a", "h1", [1.0, 0.0])])
    store.delete(["a"])
    metas, matrix = store.load_matrix()
    assert metas == []
    assert matrix.shape == (0, 0)


def test_meta_roundtrip(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    assert store.get_meta("embed_model") is None
    store.set_meta("embed_model", "qwen3-embedding")
    store.set_meta("embed_model", "qwen3-embedding:4b")   # upsert
    assert store.get_meta("embed_model") == "qwen3-embedding:4b"


def test_persists_across_reopen(tmp_path):
    p = tmp_path / "idx.db"
    s1 = IndexStore.open(p); s1.upsert([_rec("a", "h1", [1.0, 0.0])]); s1.close()
    s2 = IndexStore.open(p)
    assert s2.count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_index_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.search.index_store'`.

- [ ] **Step 3: Write the implementation**

Create `knowledge-library/librarian/search/index_store.py`:

```python
"""The SQLite vector index: one row per article (metadata + a float32 vector
blob) and a key/value meta table. Vault-agnostic; knows nothing about embeddings
or queries. Vectors are stored exactly as handed in (the indexer L2-normalizes
them first)."""
import sqlite3

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url TEXT PRIMARY KEY,
    relative_path TEXT, title TEXT, summary TEXT,
    primary_category TEXT, topics TEXT, content_hash TEXT,
    dim INTEGER, vector BLOB);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

_META_KEYS = ("url", "relative_path", "title", "summary",
              "primary_category", "topics", "content_hash")


class IndexStore:
    def __init__(self, conn):
        self.conn = conn

    @classmethod
    def open(cls, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.executescript(_SCHEMA)
        conn.commit()
        return cls(conn)

    def upsert(self, records):
        for rec in records:
            vec = np.asarray(rec["vector"], dtype=np.float32)
            self.conn.execute(
                "INSERT INTO articles"
                "(url,relative_path,title,summary,primary_category,topics,"
                " content_hash,dim,vector) VALUES(?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(url) DO UPDATE SET "
                "relative_path=excluded.relative_path,title=excluded.title,"
                "summary=excluded.summary,primary_category=excluded.primary_category,"
                "topics=excluded.topics,content_hash=excluded.content_hash,"
                "dim=excluded.dim,vector=excluded.vector",
                (rec["url"], rec["relative_path"], rec["title"], rec["summary"],
                 rec["primary_category"], rec["topics"], rec["content_hash"],
                 int(vec.shape[0]), vec.tobytes()))
        self.conn.commit()

    def delete(self, urls):
        self.conn.executemany("DELETE FROM articles WHERE url=?",
                              [(u,) for u in urls])
        self.conn.commit()

    def hashes(self):
        return {u: h for u, h in
                self.conn.execute("SELECT url, content_hash FROM articles")}

    def load_matrix(self):
        cur = self.conn.execute(
            "SELECT url,relative_path,title,summary,primary_category,topics,"
            "content_hash,vector FROM articles ORDER BY url")
        metas, vecs = [], []
        for row in cur:
            metas.append(dict(zip(_META_KEYS, row[:7])))
            vecs.append(np.frombuffer(row[7], dtype=np.float32))
        matrix = np.vstack(vecs) if vecs else np.zeros((0, 0), dtype=np.float32)
        return metas, matrix

    def count(self):
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def get_meta(self, key):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?",
                               (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))
        self.conn.commit()

    def close(self):
        self.conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest librarian/tests/test_index_store.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add librarian/search/index_store.py librarian/tests/test_index_store.py
git commit -m "feat(search): SQLite vector index store"
```

---

### Task 3: Embedder interface, FakeEmbedder, OllamaEmbedder + preflight

The embedding seam: a `FakeEmbedder` for tests, an `OllamaEmbedder` that talks to local Ollama over stdlib HTTP with the query/document asymmetry, and an `ensure_model` preflight that auto-pulls a missing model.

**Files:**
- Create: `knowledge-library/librarian/search/embedder.py`
- Test: `knowledge-library/librarian/tests/test_search_embedder.py`

**Interfaces:**
- Consumes: `librarian.search.settings.SearchSettings`, `QUERY_INSTRUCTION`; numpy; stdlib `urllib`, `subprocess`.
- Produces:
  - `librarian.search.embedder.FakeEmbedder` — `dim = 16`; `embed(texts, *, is_query=False) -> np.ndarray [n, 16]`, L2-normalized, deterministic.
  - `librarian.search.embedder.OllamaEmbedder(settings)` — `embed(texts, *, is_query=False) -> np.ndarray [n, dim]`, L2-normalized; prepends `QUERY_INSTRUCTION` when `is_query`.
  - `librarian.search.embedder.ensure_model(settings, *, runner=subprocess.run, log=print) -> None` — raises `RuntimeError` with remediation when Ollama is unreachable / pull fails / model missing with `auto_pull` off.

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_search_embedder.py`:

```python
import json
import numpy as np
import pytest
from librarian.search import embedder as emb
from librarian.search.settings import from_config, QUERY_INSTRUCTION
from librarian import config


def _settings(tmp_path, **search):
    cfg = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                        data_dir=tmp_path / "d", categories={"文学"}, search=search)
    return from_config(cfg)


def test_fake_embedder_deterministic_and_normalized():
    f = emb.FakeEmbedder()
    a = f.embed(["hello", "world"])
    b = f.embed(["hello", "world"])
    assert a.shape == (2, 16)
    np.testing.assert_allclose(a, b)                      # deterministic
    np.testing.assert_allclose(np.linalg.norm(a, axis=1), [1.0, 1.0], atol=1e-6)
    assert not np.allclose(a[0], a[1])                    # different text -> different vec


def test_ollama_embed_shapes_request_and_normalizes(tmp_path, monkeypatch):
    captured = {}

    def fake_post(self, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"embeddings": [[3.0, 4.0]]}              # not unit length

    monkeypatch.setattr(emb.OllamaEmbedder, "_post", fake_post)
    e = emb.OllamaEmbedder(_settings(tmp_path, embed_model="m1"))
    vecs = e.embed(["doc text"])
    assert captured["path"] == "/api/embed"
    assert captured["payload"] == {"model": "m1", "input": ["doc text"]}
    np.testing.assert_allclose(vecs[0], [0.6, 0.8], atol=1e-6)   # L2-normalized
    assert e.dim == 2


def test_ollama_query_prepends_instruction(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(emb.OllamaEmbedder, "_post",
                        lambda self, p, payload: captured.update(payload)
                        or {"embeddings": [[1.0, 0.0]]})
    e = emb.OllamaEmbedder(_settings(tmp_path))
    e.embed(["who?"], is_query=True)
    assert captured["input"] == [QUERY_INSTRUCTION + "who?"]


def test_ensure_model_present_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: {"qwen3-embedding"})
    emb.ensure_model(_settings(tmp_path), runner=lambda *a, **k: pytest.fail("no pull"))


def test_ensure_model_pulls_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: set())
    calls = []

    class R:
        returncode = 0

    emb.ensure_model(_settings(tmp_path, embed_model="m"),
                     runner=lambda cmd, **k: calls.append(cmd) or R(), log=lambda *a: None)
    assert calls == [["ollama", "pull", "m"]]


def test_ensure_model_unreachable_raises(tmp_path, monkeypatch):
    def boom(s):
        raise OSError("connection refused")
    monkeypatch.setattr(emb, "_list_models", boom)
    with pytest.raises(RuntimeError, match="unreachable"):
        emb.ensure_model(_settings(tmp_path))


def test_ensure_model_missing_no_autopull_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: set())
    with pytest.raises(RuntimeError, match="auto_pull"):
        emb.ensure_model(_settings(tmp_path, auto_pull=False))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_search_embedder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.search.embedder'`.

- [ ] **Step 3: Write the implementation**

Create `knowledge-library/librarian/search/embedder.py`:

```python
"""The embedding seam. FakeEmbedder is deterministic and dependency-free (tests).
OllamaEmbedder talks to a local Ollama over stdlib HTTP, prepending the query
instruction for queries only (spec §6). ensure_model preflights reachability and
auto-pulls a missing model. All vectors are L2-normalized so downstream cosine is
a dot product."""
import json
import subprocess
import urllib.error
import urllib.request

import numpy as np

from librarian.search.settings import QUERY_INSTRUCTION


def _l2(vecs):
    arr = np.asarray(vecs, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class FakeEmbedder:
    """Deterministic test embedder: a fixed 16-dim vector per text, L2-normalized.
    is_query is accepted (interface parity) but ignored."""
    dim = 16

    def embed(self, texts, *, is_query=False):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, t in enumerate(texts):
            for i, ch in enumerate(t):
                out[r, i % self.dim] += (ord(ch) % 17) + 1
        return _l2(out)


class OllamaEmbedder:
    def __init__(self, settings):
        self.settings = settings
        self.dim = None

    def _post(self, path, payload):
        req = urllib.request.Request(
            self.settings.ollama_host + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def embed(self, texts, *, is_query=False):
        texts = list(texts)
        inputs = [QUERY_INSTRUCTION + t for t in texts] if is_query else texts
        data = self._post("/api/embed",
                          {"model": self.settings.embed_model, "input": inputs})
        vecs = _l2(data["embeddings"])
        if vecs.shape[0]:
            self.dim = int(vecs.shape[1])
        return vecs


def _list_models(settings):
    """Model names known to Ollama, plus their bare (tag-stripped) forms."""
    req = urllib.request.Request(settings.ollama_host + "/api/tags")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    names = {m["name"] for m in data.get("models", [])}
    return names | {n.split(":")[0] for n in names}


def ensure_model(settings, *, runner=subprocess.run, log=print):
    """Preflight for indexing (spec §6): confirm Ollama is up and the model is
    present, auto-pulling a missing model when auto_pull is on. Raises
    RuntimeError with remediation otherwise."""
    try:
        present = _list_models(settings)
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(
            f"Ollama unreachable at {settings.ollama_host} ({e}). "
            f"Start it with `ollama serve`.") from e
    model = settings.embed_model
    if model in present or model.split(":")[0] in present:
        return
    if not settings.auto_pull:
        raise RuntimeError(
            f"model {model!r} not found in Ollama and auto_pull is off. "
            f"Run `ollama pull {model}`.")
    log(f"pulling {model} (first run; this downloads the model)…")
    result = runner(["ollama", "pull", model])
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(f"`ollama pull {model}` failed "
                           f"(exit {result.returncode}).")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest librarian/tests/test_search_embedder.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add librarian/search/embedder.py librarian/tests/test_search_embedder.py
git commit -m "feat(search): embedder interface, FakeEmbedder, OllamaEmbedder + preflight"
```

---

### Task 4: Indexer (build + incremental)

Reads label rows, builds embed-text per article, diffs against the store by `content_hash`, embeds only deltas in batches, upserts, deletes removed articles, and records the model in meta (a model change forces a rebuild).

**Files:**
- Create: `knowledge-library/librarian/search/indexer.py`
- Test: `knowledge-library/librarian/tests/test_indexer.py`

**Interfaces:**
- Consumes: `librarian.store.load`, `librarian.manifest.read_url`; `IndexStore`; an embedder (`.embed(texts)`); `SearchSettings`.
- Produces:
  - `librarian.search.indexer.build_inputs(cfg) -> tuple[list[dict], list[str]]` — records (each with keys `url, relative_path, title, summary, primary_category, topics, content_hash, _text`) and a list of skipped relative paths.
  - `librarian.search.indexer.update_index(cfg, settings, embedder, *, rebuild=False, store_factory=None) -> dict` with keys `embedded, deleted, skipped (list), total`.

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_indexer.py`:

```python
import numpy as np
from librarian import config, store, contract
from librarian.search import indexer
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder
from librarian.search.index_store import IndexStore


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db", "embed_batch_size": 2})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _write_article(cfg, rel, url, body="body text"):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")


def _label(rel, h):
    # LABEL_COLUMNS order; primary=3, topics=4, summary=7, content_hash=12
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "Title", "文学", "诗; 词", "sum", h
    return r


class SpyFake(FakeEmbedder):
    def __init__(self):
        self.calls = 0

    def embed(self, texts, *, is_query=False):
        self.calls += len(texts)
        return super().embed(texts, is_query=is_query)


def test_build_inputs_skips_missing_url(tmp_path):
    cfg = _cfg(tmp_path)
    _write_article(cfg, "文学/a.md", "u-a")
    (cfg.library_path / "文学/b.md").write_text("---\ntitle: NoUrl\n---\nx\n",
                                               encoding="utf-8")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h2")])
    records, skipped = indexer.build_inputs(cfg)
    assert [r["url"] for r in records] == ["u-a"]
    assert skipped == ["文学/b.md"]
    assert "body text" in records[0]["_text"] and "sum" in records[0]["_text"]


def test_first_index_embeds_all_then_incremental(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    spy = SpyFake()
    out = indexer.update_index(cfg, s, spy)
    assert out["embedded"] == 2 and out["total"] == 2 and spy.calls == 2

    # Re-run with no changes -> embeds nothing.
    spy2 = SpyFake()
    out2 = indexer.update_index(cfg, s, spy2)
    assert out2["embedded"] == 0 and spy2.calls == 0 and out2["total"] == 2


def test_changed_hash_reembeds_only_that_row(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    store.merge(cfg.labels_path, [_label("文学/b.md", "h2")])   # b changed
    spy = SpyFake()
    out = indexer.update_index(cfg, s, spy)
    assert spy.calls == 1 and out["embedded"] == 1


def test_deleted_article_removed_from_index(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    store.delete(cfg.labels_path, ["文学/b.md"])
    out = indexer.update_index(cfg, s, FakeEmbedder())
    assert out["deleted"] == 1 and out["total"] == 1


def test_model_change_forces_rebuild(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    cfg2 = _cfg(tmp_path)
    cfg2.search["embed_model"] = "different-model"
    s2 = from_config(cfg2)
    spy = SpyFake()
    out = indexer.update_index(cfg2, s2, spy)   # hash unchanged, but model changed
    assert spy.calls == 1 and out["embedded"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_indexer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.search.indexer'`.

- [ ] **Step 3: Write the implementation**

Create `knowledge-library/librarian/search/indexer.py`:

```python
"""Build/refresh the vector index from label state. Reads each labeled article's
body + summary + title as the embed text, diffs against the store by content_hash
(spec §5), embeds only new/changed rows in batches, upserts, and drops removed
articles. The embed model is recorded in meta; a model change forces a rebuild."""
from librarian import store, manifest
from librarian.search.index_store import IndexStore

# LABEL_COLUMNS positional indices (see contract.py / Global Constraints).
_REL, _TITLE, _PRIMARY, _TOPICS, _SUMMARY, _HASH = 0, 1, 3, 4, 7, 12


def build_inputs(cfg):
    records, skipped = [], []
    for r in store.load(cfg.labels_path):
        rel = r[_REL]
        path = cfg.library_path / rel
        url = manifest.read_url(path)
        if not url:
            skipped.append(rel)
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            skipped.append(rel)
            continue
        text = "\n\n".join(p for p in (r[_TITLE], r[_SUMMARY], body) if p)
        records.append({
            "url": url, "relative_path": rel, "title": r[_TITLE],
            "summary": r[_SUMMARY], "primary_category": r[_PRIMARY],
            "topics": r[_TOPICS], "content_hash": r[_HASH], "_text": text})
    return records, skipped


def update_index(cfg, settings, embedder, *, rebuild=False, store_factory=None):
    open_store = store_factory or IndexStore.open
    idx = open_store(settings.index_path)
    try:
        if idx.get_meta("embed_model") not in (None, settings.embed_model):
            rebuild = True
        if rebuild:
            idx.delete(list(idx.hashes()))

        records, skipped = build_inputs(cfg)
        existing = idx.hashes()
        want = {rec["url"] for rec in records}
        to_embed = [rec for rec in records
                    if existing.get(rec["url"]) != rec["content_hash"]]
        deleted = [u for u in existing if u not in want]

        bs = max(1, settings.embed_batch_size)
        embedded = 0
        for i in range(0, len(to_embed), bs):
            batch = to_embed[i:i + bs]
            vecs = embedder.embed([rec["_text"] for rec in batch])
            payload = []
            for rec, vec in zip(batch, vecs):
                clean = {k: v for k, v in rec.items() if k != "_text"}
                clean["vector"] = vec
                payload.append(clean)
            idx.upsert(payload)            # commits per batch (transactional)
            embedded += len(payload)

        idx.delete(deleted)
        idx.set_meta("embed_model", settings.embed_model)
        return {"embedded": embedded, "deleted": len(deleted),
                "skipped": skipped, "total": idx.count()}
    finally:
        idx.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest librarian/tests/test_indexer.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add librarian/search/indexer.py librarian/tests/test_indexer.py
git commit -m "feat(search): incremental indexer (build/diff/embed/upsert)"
```

---

### Task 5: Query

Embeds the query, scores it against the loaded matrix (dot product on normalized vectors), applies optional category/topic filters, returns the top-N ranked results.

**Files:**
- Create: `knowledge-library/librarian/search/query.py`
- Test: `knowledge-library/librarian/tests/test_query.py`

**Interfaces:**
- Consumes: `IndexStore.load_matrix`; an embedder (`.embed([q], is_query=True)`); `SearchSettings`.
- Produces:
  - `librarian.search.query.SearchResult` dataclass: `score: float, title, summary, primary_category, topics, relative_path, url` (str).
  - `librarian.search.query.search(cfg, settings, embedder, query, *, limit=None, category=None, topic=None, store_factory=None) -> list[SearchResult]` (ranked desc; `[]` on empty index).

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_query.py`:

```python
from librarian import config, store, contract
from librarian.search import indexer, query
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path, **search):
    s = {"index_path": "idx.db"}
    s.update(search)
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学", "历史人文"},
                      search=s)
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, body, primary, topics, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, body[:5], primary, topics, body, h
    return r


def _build(cfg):
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())


def test_empty_index_returns_empty(tmp_path):
    cfg = _cfg(tmp_path)
    out = query.search(cfg, from_config(cfg), FakeEmbedder(), "anything")
    assert out == []


def test_ranks_most_similar_first(tmp_path):
    cfg = _cfg(tmp_path)
    rows = [_article(cfg, "文学/a.md", "u-a", "alpha alpha", "文学", "诗", "h"),
            _article(cfg, "文学/b.md", "u-b", "beta", "文学", "词", "h")]
    store.merge(cfg.labels_path, rows)
    _build(cfg)
    out = query.search(cfg, from_config(cfg), FakeEmbedder(), "alpha alpha")
    assert out[0].url == "u-a"
    assert out[0].score >= out[1].score


def test_limit_caps_results(tmp_path):
    cfg = _cfg(tmp_path, default_limit=1)
    store.merge(cfg.labels_path, [
        _article(cfg, "文学/a.md", "u-a", "x", "文学", "诗", "h"),
        _article(cfg, "文学/b.md", "u-b", "y", "文学", "词", "h")])
    _build(cfg)
    assert len(query.search(cfg, from_config(cfg), FakeEmbedder(), "x")) == 1
    assert len(query.search(cfg, from_config(cfg), FakeEmbedder(), "x", limit=2)) == 2


def test_category_and_topic_filters(tmp_path):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [
        _article(cfg, "文学/a.md", "u-a", "x", "文学", "诗; 散文", "h"),
        _article(cfg, "历史人文/b.md", "u-b", "x", "历史人文", "战争", "h")])
    _build(cfg)
    s = from_config(cfg)
    cat = query.search(cfg, s, FakeEmbedder(), "x", category="历史人文", limit=10)
    assert [r.url for r in cat] == ["u-b"]
    top = query.search(cfg, s, FakeEmbedder(), "x", topic="散文", limit=10)
    assert [r.url for r in top] == ["u-a"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_query.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.search.query'`.

- [ ] **Step 3: Write the implementation**

Create `knowledge-library/librarian/search/query.py`:

```python
"""One semantic query: embed it (with the query instruction), score against the
stored matrix via dot product (vectors are pre-normalized, so this is cosine),
apply optional category/topic filters, and return the top-N ranked results."""
from dataclasses import dataclass

import numpy as np

from librarian.search.index_store import IndexStore


@dataclass
class SearchResult:
    score: float
    title: str
    summary: str
    primary_category: str
    topics: str
    relative_path: str
    url: str


def _topics(s):
    return [t.strip() for t in s.split(";") if t.strip()]


def search(cfg, settings, embedder, query, *, limit=None, category=None,
           topic=None, store_factory=None):
    open_store = store_factory or IndexStore.open
    limit = limit or settings.default_limit
    idx = open_store(settings.index_path)
    try:
        metas, matrix = idx.load_matrix()
    finally:
        idx.close()
    if not metas:
        return []
    qvec = np.asarray(embedder.embed([query], is_query=True)[0], dtype=np.float32)
    scores = matrix @ qvec
    results = []
    for i in np.argsort(-scores):
        m = metas[i]
        if category and m["primary_category"] != category:
            continue
        if topic and topic not in _topics(m["topics"]):
            continue
        results.append(SearchResult(
            score=float(scores[i]), title=m["title"], summary=m["summary"],
            primary_category=m["primary_category"], topics=m["topics"],
            relative_path=m["relative_path"], url=m["url"]))
        if len(results) >= limit:
            break
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest librarian/tests/test_query.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add librarian/search/query.py librarian/tests/test_query.py
git commit -m "feat(search): ranked query with category/topic filters"
```

---

### Task 6: CLI subcommands (`index`, `search`)

Wires `index` and `search` into the existing `python -m librarian.update` dispatcher, following the `cmd_audit`/`cmd_materialize` pattern (lazy submodule import inside the handler so numpy never loads for non-search commands).

**Files:**
- Modify: `knowledge-library/librarian/update.py` (add two `cmd_*` functions; extend the `handlers` dict + argv parsing; update the module docstring)
- Test: `knowledge-library/librarian/tests/test_search_cli.py`

**Interfaces:**
- Consumes: `librarian.search.{settings,embedder,indexer,query}`; the module-level `cfg` set by `configure()`; the existing `_opt(flag)` helper.
- Produces:
  - `librarian.update.cmd_index(rebuild=False)` — prints an index summary line.
  - `librarian.update.cmd_search(query, limit=None, category=None, topic=None)` — prints ranked results or a "build the index" hint.

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_search_cli.py`:

```python
from librarian import update, config, store, contract
from librarian.search import indexer
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db"})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, body, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "Alpha Doc", "文学", "诗", body, h
    return r


def test_cmd_index_uses_fake_embedder(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    monkeypatch.setattr(update, "cfg", cfg)
    # Inject the fake embedder + no-op preflight so no real Ollama is touched.
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.ensure_model",
                        lambda *a, **k: None)
    update.cmd_index()
    assert "embedded 1" in capsys.readouterr().out


def test_cmd_search_prints_results(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("alpha", limit=5)
    out = capsys.readouterr().out
    assert "Alpha Doc" in out and "文学/a.md" in out


def test_cmd_search_empty_index_hints(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("anything")
    assert "index" in capsys.readouterr().out.lower()


def test_cmd_search_warns_when_index_is_stale(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    # Index one article, then add a second label row that is NOT indexed.
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())
    store.merge(cfg.labels_path, [_article(cfg, "文学/b.md", "u-b", "beta", "h")])
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("alpha", limit=5)
    assert "not yet indexed" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_search_cli.py -v`
Expected: FAIL — `AttributeError: module 'librarian.update' has no attribute 'cmd_index'`.

- [ ] **Step 3: Add the two handlers + dispatch**

In `knowledge-library/librarian/update.py`, add these two functions next to `cmd_audit` (above `_opt`):

```python
def cmd_index(rebuild=False):
    """Build/refresh the semantic-search vector index (spec §5)."""
    from librarian.search import settings as ssettings, embedder as semb, indexer
    s = ssettings.from_config(cfg)
    emb = semb.OllamaEmbedder(s)
    semb.ensure_model(s)
    summary = indexer.update_index(cfg, s, emb, rebuild=rebuild)
    print(f"indexed: embedded {summary['embedded']}, deleted {summary['deleted']}, "
          f"total {summary['total']}, skipped {len(summary['skipped'])}")
    if summary["skipped"]:
        head = summary["skipped"][:5]
        more = " …" if len(summary["skipped"]) > 5 else ""
        print(f"  skipped (no url / unreadable): {head}{more}")


def _stale_count(cfg, settings):
    """Approximate count of labeled items not yet in the index: label rows minus
    indexed rows (spec §7). Heuristic — over-counts by any no-url/unreadable rows
    the indexer skips, which are rare. Cheap (no body reads)."""
    from librarian.search.index_store import IndexStore
    idx = IndexStore.open(settings.index_path)
    try:
        return max(0, len(store.load(cfg.labels_path)) - idx.count())
    finally:
        idx.close()


def cmd_search(query, limit=None, category=None, topic=None):
    """Semantic search over the library; prints ranked notes (spec §5)."""
    from librarian.search import settings as ssettings, embedder as semb, query as q
    s = ssettings.from_config(cfg)
    emb = semb.OllamaEmbedder(s)
    results = q.search(cfg, s, emb, query, limit=limit, category=category,
                       topic=topic)
    if not results:
        print("no results — is the index built? run "
              "`python -m librarian.update index`")
        return
    for r in results:
        print(f"[{r.score:.3f}] {r.title}  ·  {r.primary_category}")
        print(f"        {r.relative_path}")
        if r.summary:
            print(f"        {r.summary[:140]}")
    pending = _stale_count(cfg, s)
    if pending:
        print(f"note: ~{pending} labeled item(s) not yet indexed — run "
              f"`python -m librarian.update index` to refresh")
```

In the `if __name__ == "__main__":` block, add a usage guard for `search` (after the `ingest` guard) and the two handler entries. Replace the `handlers` dict assignment with:

```python
    if cmd == "search" and len(sys.argv) < 3:
        sys.exit('usage: python -m librarian.update search "<query>" '
                 '[--limit N] [--category C] [--topic T]')
    limit = _opt("--limit")
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib, lang=lang),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib, lang=lang),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib),
                "status": lambda: cmd_status(),
                "audit": lambda: cmd_audit(),
                "index": lambda: cmd_index("--rebuild" in sys.argv),
                "search": lambda: cmd_search(
                    sys.argv[2], limit=int(limit) if limit else None,
                    category=_opt("--category"), topic=_opt("--topic"))}
```

Also add `index` and `search` to the module docstring's command list at the top of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest librarian/tests/test_search_cli.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `pytest -q`
Expected: PASS — all prior tests plus the new ones green.

- [ ] **Step 6: Commit**

```bash
git add librarian/update.py librarian/tests/test_search_cli.py
git commit -m "feat(search): index + search CLI subcommands"
```

---

### Task 7: MCP server (`search_library` tool)

A thin MCP server exposing `search_library` over the `query` engine, for Claude and QwenPaw. The testable seam is `run_search` (pure, no `mcp` dep); `build_server` is thin wiring that requires the `mcp` package.

**Files:**
- Create: `knowledge-library/librarian/search/mcp_server.py`
- Test: `knowledge-library/librarian/tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `librarian.config.load`; `librarian.search.{settings,embedder,query}`.
- Produces:
  - `librarian.search.mcp_server.run_search(query, limit=None, category=None, topic=None, *, _ctx=None) -> list[dict]` — each dict has keys `score, title, summary, primary_category, topics, relative_path, url`. `_ctx=(cfg, settings)` bypasses config loading (used by tests and `build_server`).
  - `librarian.search.mcp_server.build_server()` — returns a configured `FastMCP` instance (requires `mcp`).

- [ ] **Step 1: Install the `mcp` dependency**

Run (under the Python 3.11 env that has pytest/numpy):
```bash
/opt/homebrew/opt/python@3.11/bin/python3.11 -m pip install mcp
```
Expected: `Successfully installed mcp-…`. (Only `build_server`/serving needs it; `run_search` and its test do not.)

- [ ] **Step 2: Write the failing test**

Create `knowledge-library/librarian/tests/test_mcp_server.py`:

```python
from librarian import config, store, contract
from librarian.search import indexer, mcp_server
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db"})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, body, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "Alpha Doc", "文学", "诗", body, h
    return r


def test_run_search_returns_structured_dicts(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    s = from_config(cfg)
    indexer.update_index(cfg, s, FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    out = mcp_server.run_search("alpha", limit=5, _ctx=(cfg, s))
    assert isinstance(out, list) and isinstance(out[0], dict)
    assert set(out[0]) == {"score", "title", "summary", "primary_category",
                           "topics", "relative_path", "url"}
    assert out[0]["url"] == "u-a"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest librarian/tests/test_mcp_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.search.mcp_server'`.

- [ ] **Step 4: Write the implementation**

Create `knowledge-library/librarian/search/mcp_server.py`:

```python
"""MCP server exposing the library's semantic search as a `search_library` tool,
for any MCP client (Claude, QwenPaw — both support MCP). Run:

  KNOWLEDGE_LIBRARY_CONFIG=config.yaml python -m librarian.search.mcp_server

`run_search` is the pure, importable seam (no `mcp` dependency); `build_server`
is the thin FastMCP wiring and requires `pip install mcp`."""
import os

from librarian import config
from librarian.search import settings as ssettings
from librarian.search import embedder as semb
from librarian.search import query as q


def _load():
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    return cfg, ssettings.from_config(cfg)


def run_search(query, limit=None, category=None, topic=None, *, _ctx=None):
    cfg, s = _ctx or _load()
    emb = semb.OllamaEmbedder(s)
    results = q.search(cfg, s, emb, query, limit=limit, category=category,
                       topic=topic)
    return [{"score": r.score, "title": r.title, "summary": r.summary,
             "primary_category": r.primary_category, "topics": r.topics,
             "relative_path": r.relative_path, "url": r.url}
            for r in results]


def build_server():
    from mcp.server.fastmcp import FastMCP
    ctx = _load()
    server = FastMCP("knowledge-library")

    @server.tool()
    def search_library(query: str, limit: int = 0, category: str = "",
                       topic: str = "") -> list:
        """Semantic search over the knowledge library. Returns the most relevant
        notes (title, summary, category, topics, vault path) ranked by meaning."""
        return run_search(query, limit=limit or None, category=category or None,
                          topic=topic or None, _ctx=ctx)

    return server


if __name__ == "__main__":
    build_server().run()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest librarian/tests/test_mcp_server.py -v`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add librarian/search/mcp_server.py librarian/tests/test_mcp_server.py
git commit -m "feat(search): MCP search_library server (Claude + QwenPaw)"
```

---

### Task 8: Steady-state hook, config template, docs

Hooks incremental indexing into `steady_state.finish` (best-effort, non-fatal — a steady-state run that already materialized must not fail because Ollama is down), documents the `search:` config block, and adds user-facing docs.

**Files:**
- Modify: `knowledge-library/librarian/orchestrate/steady_state.py` (call indexer after materialize)
- Modify: `knowledge-library/config.example.yaml` (add the `search:` block)
- Modify: `knowledge-library/SKILL.md` (add a short "Search" subsection)
- Modify: `README.md` (mention search under the skill's capabilities)
- Test: `knowledge-library/librarian/tests/test_steady_state_index_hook.py`

**Interfaces:**
- Consumes: `librarian.search.{settings,embedder,indexer}`; `cfg`.
- Produces: `librarian.orchestrate.steady_state._index_after_materialize(cfg) -> None` (never raises).

- [ ] **Step 1: Write the failing test**

Create `knowledge-library/librarian/tests/test_steady_state_index_hook.py`:

```python
from librarian import config, store, contract
from librarian.orchestrate import steady_state
from librarian.search.settings import from_config
from librarian.search.index_store import IndexStore
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db"})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\nbody\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "T", "文学", "诗", "s", h
    return r


def test_hook_refreshes_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "h")])
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.ensure_model",
                        lambda *a, **k: None)
    steady_state._index_after_materialize(cfg)
    idx = IndexStore.open(from_config(cfg).index_path)
    assert idx.count() == 1


def test_hook_is_non_fatal_on_embedder_error(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "h")])
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())

    def boom(*a, **k):
        raise RuntimeError("Ollama unreachable")
    monkeypatch.setattr("librarian.search.embedder.ensure_model", boom)
    steady_state._index_after_materialize(cfg)        # must NOT raise
    assert "not refreshed" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_steady_state_index_hook.py -v`
Expected: FAIL — `AttributeError: module 'librarian.orchestrate.steady_state' has no attribute '_index_after_materialize'`.

- [ ] **Step 3: Add the hook to steady_state.py**

In `knowledge-library/librarian/orchestrate/steady_state.py`, add this helper at module level (after the imports):

```python
def _index_after_materialize(cfg):
    """Refresh the search index with this run's new/changed items (spec §5).
    Best-effort: a missing/unreachable embedder must NOT fail a steady-state run
    that already materialized — the index just stays stale until the next run or
    a manual `index`."""
    try:
        from librarian.search import settings as ssettings
        from librarian.search import embedder as semb
        from librarian.search import indexer
        s = ssettings.from_config(cfg)
        emb = semb.OllamaEmbedder(s)
        semb.ensure_model(s)
        indexer.update_index(cfg, s, emb)
    except Exception as e:  # noqa: BLE001 — non-fatal by design (spec §7)
        print(f"warning: search index not refreshed ({e}); run "
              f"`python -m librarian.update index` later")
```

Then call it in `finish()`, immediately after the successful `materialize.materialize(...)` line:

```python
    materialize.materialize(cfg, write=True, out=library, lang=lang)
    _index_after_materialize(cfg)
```

- [ ] **Step 4: Run the hook test to verify it passes**

Run: `pytest librarian/tests/test_steady_state_index_hook.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Add the `search:` block to the config template**

Append to `knowledge-library/config.example.yaml`:

```yaml
# SEMANTIC SEARCH (spec 2026-06-22) ---------------------------------------
# Local Qwen3-Embedding (via Ollama) over the materialized library. Build the
# index with `python -m librarian.update index`; query with
# `python -m librarian.update search "<query>"`. Steady-state refreshes it.
search:
  embed_backend: ollama
  ollama_host: http://localhost:11434
  embed_model: qwen3-embedding:8b     # the exact pulled tag; `ollama list | grep qwen3-embedding`
  embed_batch_size: 16
  auto_pull: true                     # pull the model on first index if missing
  index_path: search_index.db         # relative to data_dir
  default_limit: 10
```

- [ ] **Step 6: Document search in SKILL.md and README**

In `knowledge-library/SKILL.md`, add a short subsection (after the steady-state section) describing the two commands and the MCP server:

```markdown
## Semantic search (optional)

Natural-language retrieval over the materialized library, powered by a local
Qwen3-Embedding model via Ollama (see the `search:` block in `config.yaml`).

- `python -m librarian.update index [--rebuild]` — build/refresh the vector
  index. First run auto-pulls the model if missing (needs Ollama running).
- `python -m librarian.update search "<query>" [--limit N] [--category C] [--topic T]`
  — print the most relevant notes, ranked.
- `python -m librarian.search.mcp_server` — expose a `search_library` MCP tool
  for Claude or QwenPaw (requires `pip install mcp`).

Steady-state refreshes the index automatically after each materialize.
Run search commands under a Python with numpy installed (the same env as `pytest`).
```

In `README.md`, add a line to the skill description noting semantic search is available (one sentence under "Layout" or "Two operating modes").

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: PASS — every test green (existing + all new search tests).

- [ ] **Step 8: Commit**

```bash
git add librarian/orchestrate/steady_state.py config.example.yaml SKILL.md ../README.md librarian/tests/test_steady_state_index_hook.py
git commit -m "feat(search): steady-state index hook, config template, docs"
```

---

## Final verification (after all tasks)

- [ ] Run the full suite from `knowledge-library/`: `pytest -q` → all green.
- [ ] Optional manual end-to-end (needs Ollama + the model): build a tiny `config.yaml` pointing at a small library, run `python3.11 -m librarian.update index`, then `python3.11 -m librarian.update search "your query"`, and confirm ranked results print.

## Notes for the implementer

- **Why lazy imports in `update.py`:** the default `python` is 3.14 without numpy; importing search modules at file top would break every `librarian.update` command. Importing inside `cmd_index`/`cmd_search` keeps non-search commands working everywhere and confines the numpy requirement to search.
- **Transactionality:** `IndexStore.upsert`/`delete` commit immediately, so an interrupted `index` leaves a consistent partial DB; the next run completes it via the hash diff (spec §7).
- **Deferred (spec §9), do not build:** answer generation/RAG synthesis, chunking, ANN/vector-DB, BM25 hybrid, an in-process sentence-transformers backend.
