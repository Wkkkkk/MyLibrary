# Knowledge-Library Ingest Path Implementation Plan (Plan 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ingest path — source adapters that normalize raw producer output into the node contract, plus the wave orchestration that turns an inbox of nodes into validated label rows.

**Architecture:** Two new sub-packages under the existing `librarian/` (ported in Plan 1). `librarian/adapters/` defines the normalized-node contract (`base.py`) and two concrete adapters (`zhihu.py` lead recipe, `markdown_passthrough.py` generic). `librarian/orchestrate/` ports the MyBooks wave loop building blocks: `build_wave.py` (select unlabeled articles → per-agent assignment files embedding the active canon) and `ingest_wave.py` (read agent-written JSON → reconstruct full rows from frozen manifest fields → validate → merge into the labels store). All functions take `cfg` explicitly, matching the de-hardcoded module style established in Plan 1 (`manifest.build(vault, cfg)`, `hubgen.plan(..., cfg)`).

**Tech Stack:** Python 3, stdlib only (`json`, `re`, `unicodedata`, `hashlib`, `pathlib`) + the existing `librarian` modules (`config`, `contract`, `tsv`, `manifest`, `validate`, `store`, `registry`, `proposals`). Tests: `pytest`, run from `knowledge-library/`.

**Scope (Plan 2 = "Ingest path"):** adapters + `build_wave` + `ingest_wave` + their tests. **Non-goals (deferred):** the wave *loop driver* (repeat build→dispatch→ingest until 100%) and gate pauses are SKILL.md orchestration (Plan 5); `materialize --lang` localization is Plan 3; steady-state + run ledger are Plan 4; the actual parallel LLM dispatch is performed by the orchestrating skill following `dispatching-parallel-agents`, not by this Python (these modules only *prepare* assignments and *collect* results). Topic promotion stays a deliberate gate action (`proposals.accept`, GATE 2) — `ingest_wave` records proposals but never mutates the canon.

**Working directory for all commands:** `/Users/kunwu/Workspace/MyLibrary/knowledge-library`
**Run tests with:** `pytest -q` (the `conftest.py` there puts `librarian` on `sys.path`).

---

## File Structure

| File | Responsibility |
|---|---|
| `librarian/config.py` *(modify)* | Add labeling-knob fields (`agents_per_wave`, `articles_per_agent`, `extractor_version`) + `wave_assign_dir` / `wave_out_dir` properties. |
| `config.example.yaml` *(modify)* | Document the three new optional keys. |
| `librarian/adapters/__init__.py` *(create)* | Package marker. |
| `librarian/adapters/base.py` *(create)* | Node contract: `parse`, `validate`, `set_field`, `Adapter` base, `ingest_to_inbox`. |
| `librarian/adapters/zhihu.py` *(create)* | Lead adapter — passes zhihu-fetcher output through (fields already match). |
| `librarian/adapters/markdown_passthrough.py` *(create)* | Generic adapter — injects `source`, otherwise requires contract compliance. |
| `librarian/orchestrate/__init__.py` *(create)* | Package marker. |
| `librarian/orchestrate/build_wave.py` *(create)* | `select` / `assignments` / `canon_line` / `build` + CLI. |
| `librarian/orchestrate/ingest_wave.py` *(create)* | `ingest` (+ row assembly helpers) + CLI. |
| `librarian/tests/test_adapters_base.py` *(create)* | Contract + ingest_to_inbox behaviour. |
| `librarian/tests/test_adapter_zhihu.py` *(create)* | Zhihu pass-through + rejection. |
| `librarian/tests/test_adapter_markdown_passthrough.py` *(create)* | Source injection + rejection. |
| `librarian/tests/test_build_wave.py` *(create)* | Selection, splitting, assignment-file content. |
| `librarian/tests/test_ingest_wave.py` *(create)* | JSON→row, validation, merge, proposals, skip. |

---

## Task 1: Config — labeling knobs + wave directories

**Files:**
- Modify: `librarian/config.py`
- Modify: `config.example.yaml`
- Test: `librarian/tests/test_config.py` *(add cases to the existing file)*

- [ ] **Step 1: Write the failing test**

Append to `librarian/tests/test_config.py`:

```python
def test_labeling_knob_defaults(cfg):
    assert cfg.agents_per_wave == 4
    assert cfg.articles_per_agent == 15
    assert cfg.extractor_version == "knowledge-library"


def test_wave_directory_properties(cfg):
    assert cfg.wave_assign_dir == cfg.data_dir / "wave_assign"
    assert cfg.wave_out_dir == cfg.data_dir / "wave_out"


def test_loader_reads_labeling_knobs(tmp_path):
    from librarian import config
    p = tmp_path / "config.yaml"
    p.write_text(
        "corpus_path: ./v\nlibrary_path: ./l\ndata_dir: ./d\n"
        "categories: [Literature]\n"
        "agents_per_wave: 6\narticles_per_agent: 20\n"
        "extractor_version: pilot-2026\n",
        encoding="utf-8")
    c = config.load(p)
    assert c.agents_per_wave == 6
    assert c.articles_per_agent == 20
    assert c.extractor_version == "pilot-2026"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -q` (from `knowledge-library/`, i.e. `pytest librarian/tests/test_config.py -q`)
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'agents_per_wave'`

- [ ] **Step 3: Add the dataclass fields**

In `librarian/config.py`, inside the `@dataclass class Config`, add after the `legacy_labels_name` field (before the Language comment block):

```python
    # Labeling knobs (spec §4): the wave loop dispatches `agents_per_wave`
    # parallel agents, each handling `articles_per_agent` articles. The value
    # written to a label row's extractor_version column traces which run/version
    # produced it.
    agents_per_wave: int = 4
    articles_per_agent: int = 15
    extractor_version: str = "knowledge-library"
```

- [ ] **Step 4: Add the directory properties**

In `librarian/config.py`, add after the `batches_dir` property:

```python
    @property
    def wave_assign_dir(self):
        return self.data_dir / "wave_assign"

    @property
    def wave_out_dir(self):
        return self.data_dir / "wave_out"
```

- [ ] **Step 5: Teach the loader the new keys**

In `librarian/config.py`, in `load()`, extend the optional-key tuple. Change:

```python
    for key in ("hub_dir", "generated_marker", "hub_min_articles",
                "topic_split_threshold", "batch_size", "legacy_labels_name",
                "label_language", "category_localization"):
```

to:

```python
    for key in ("hub_dir", "generated_marker", "hub_min_articles",
                "topic_split_threshold", "batch_size", "legacy_labels_name",
                "label_language", "category_localization",
                "agents_per_wave", "articles_per_agent", "extractor_version"):
```

- [ ] **Step 6: Document the keys in the example config**

In `config.example.yaml`, append after the final line (`generated_marker: "generated: knowledge-library"`):

```yaml

# LABELING (defaults shown) ------------------------------------------------
agents_per_wave: 4                       # parallel labeling agents per wave
articles_per_agent: 15                   # articles each agent labels
extractor_version: knowledge-library     # written to each label row's provenance column
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest librarian/tests/test_config.py -q`
Expected: PASS (all config tests).

- [ ] **Step 8: Commit**

```bash
git add librarian/config.py config.example.yaml librarian/tests/test_config.py
git commit -m "feat(librarian): config labeling knobs + wave directories"
```

---

## Task 2: Node contract — `adapters/base.py`

**Files:**
- Create: `librarian/adapters/__init__.py`
- Create: `librarian/adapters/base.py`
- Test: `librarian/tests/test_adapters_base.py`

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_adapters_base.py`:

```python
import unicodedata

from librarian.adapters import base

VALID = ('---\ntitle: "T"\nsource: zhihu\nurl: "https://z/p/1"\n---\n\nBody text.\n')


class ListAdapter(base.Adapter):
    """Test adapter that yields a fixed list of (filename, text) pairs."""
    name = "test"

    def __init__(self, items):
        self.items = items

    def nodes(self, src_dir):
        yield from self.items


def test_parse_splits_frontmatter_and_body():
    fm, body = base.parse(VALID)
    assert fm["title"] == "T"
    assert fm["source"] == "zhihu"
    assert fm["url"] == "https://z/p/1"
    assert body.strip() == "Body text."


def test_parse_fence_safe_with_dashes_in_title():
    text = '---\ntitle: "a\n------ b"\nsource: x\nurl: "u"\n---\nBody\n'
    fm, body = base.parse(text)
    # The bare closing fence is the real `---` line, not the `------` in the title.
    assert fm["source"] == "x"
    assert body.strip() == "Body"


def test_parse_no_frontmatter_returns_empty():
    fm, body = base.parse("no frontmatter here")
    assert fm == {} and body == "no frontmatter here"


def test_validate_accepts_complete_node():
    fm, body = base.parse(VALID)
    assert base.validate(fm, body) == []


def test_validate_rejects_missing_url():
    fm, body = base.parse('---\ntitle: "T"\nsource: zhihu\n---\nBody\n')
    errs = base.validate(fm, body)
    assert any("url" in e for e in errs)


def test_validate_rejects_empty_body():
    fm, body = base.parse('---\ntitle: "T"\nsource: zhihu\nurl: "u"\n---\n\n')
    assert any("body" in e for e in errs) if (errs := base.validate(fm, body)) else False
    assert base.validate(fm, body) != []


def test_set_field_injects_missing_key():
    text = '---\ntitle: "T"\nurl: "u"\n---\nBody\n'
    out = base.set_field(text, "source", "blog")
    fm, _ = base.parse(out)
    assert fm["source"] == "blog"


def test_set_field_replaces_existing_key():
    out = base.set_field(VALID, "source", "blog")
    fm, _ = base.parse(out)
    assert fm["source"] == "blog"


def test_ingest_writes_valid_node_under_source_subfolder(cfg):
    adapter = ListAdapter([("a.md", VALID)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md"]
    assert rejected == [] and skipped == []
    assert (cfg.corpus_path / "test" / "a.md").read_text(encoding="utf-8") == VALID


def test_ingest_rejects_contract_violation(cfg):
    bad = '---\ntitle: "T"\nsource: zhihu\n---\nBody\n'  # no url
    adapter = ListAdapter([("bad.md", bad)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == []
    assert rejected and rejected[0][0] == "bad.md"
    assert any("url" in e for e in rejected[0][1])
    assert not (cfg.corpus_path / "test" / "bad.md").exists()


def test_ingest_skips_duplicate_url(cfg):
    adapter = ListAdapter([("a.md", VALID), ("b.md", VALID)])  # same url
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md"]
    assert skipped == ["b.md"]


def test_ingest_collision_keeps_both_when_url_differs(cfg):
    other = VALID.replace("https://z/p/1", "https://z/p/2")
    adapter = ListAdapter([("a.md", VALID), ("a.md", other)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md", "test/a_2.md"]


def test_ingest_nfc_normalizes_filename(cfg):
    nfd_name = unicodedata.normalize("NFD", "ポップ.md")
    assert nfd_name != "ポップ.md"
    adapter = ListAdapter([(nfd_name, VALID)])
    written, _, _ = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/" + unicodedata.normalize("NFC", "ポップ.md")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_adapters_base.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.adapters'`

- [ ] **Step 3: Create the package marker**

Create `librarian/adapters/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Write the implementation**

Create `librarian/adapters/base.py`:

```python
"""The normalized-node contract (spec §4): every source unit, whatever its
origin, becomes one Markdown file whose frontmatter carries the fields below.
An adapter's only job is to yield (filename, text) pairs already in this shape;
`ingest_to_inbox` validates each and writes the survivors into the inbox
(cfg.corpus_path). A node that violates the contract is rejected, never written.
"""
import re
import unicodedata
from pathlib import Path

# Stable identity + provenance the rest of the toolkit relies on. `url` is the
# dedup key (manifest.read_url) — language-neutral and surviving re-fetch +
# frontmatter rewrite, unlike a content hash (spec §4).
REQUIRED_FIELDS = ("title", "source", "url")

# Closing frontmatter fence: a line that is exactly '---' (optional trailing
# whitespace) — NOT dashes inside a multi-line quoted title (lessons §8 fence
# bug). Mirrors frontmatter._FENCE.
_FENCE = re.compile(r"\n---[ \t]*(?:\n|$)")
_KV = re.compile(r'(?m)^([A-Za-z0-9_]+):[ \t]*"?(.*?)"?[ \t]*$')


def parse(text):
    """Split a node Markdown string into (frontmatter: dict, body: str).
    Frontmatter is the block between the leading `---\\n` and the next bare
    `---` line; returns ({}, text) when absent. Only flat scalar `key: value`
    pairs are read (the contract fields are all scalars)."""
    if not text.startswith("---\n"):
        return {}, text
    m = _FENCE.search(text, 4)
    if not m:
        return {}, text
    head = text[4:m.start()]
    body = text[m.end():]
    fm = {km.group(1): km.group(2) for km in _KV.finditer(head)}
    return fm, body


def validate(frontmatter, body):
    """Return a list of contract-violation messages; [] means a valid node."""
    errors = []
    for f in REQUIRED_FIELDS:
        if not str(frontmatter.get(f, "")).strip():
            errors.append(f"missing required field: {f}")
    if not body.strip():
        errors.append("empty body")
    return errors


def set_field(text, key, value):
    """Insert or replace a scalar frontmatter `key: "value"` line, fence-safe.
    Returns text unchanged if it has no leading `---\\n` frontmatter block."""
    if not text.startswith("---\n"):
        return text
    m = _FENCE.search(text, 4)
    if not m:
        return text
    head, rest = text[4:m.start()], text[m.start():]
    line = f'{key}: "{value}"'
    lines = head.split("\n")
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:[ \t]", ln):
            lines[i] = line
            break
    else:
        lines.append(line)
    return "---\n" + "\n".join(lines) + rest


class Adapter:
    """Base class. A concrete adapter sets `name` and implements `nodes`. The
    `name` doubles as the inbox subfolder the adapter's nodes land in."""
    name = "base"

    def nodes(self, src_dir):
        """Yield (filename, text) per source unit, where text is a full node
        Markdown string and filename is the bare destination file name."""
        raise NotImplementedError


def ingest_to_inbox(adapter, src_dir, cfg):
    """Walk an adapter's nodes, validate each against the contract, and write
    the valid, not-yet-seen ones into cfg.corpus_path/<adapter.name>/ verbatim
    (NFC-normalized). Dedup is by the `url` frontmatter key across the whole
    inbox (idempotent re-runs). A same-name/different-url collision appends _N
    rather than overwriting (lessons §8). Returns
    (written: list[str], rejected: list[(filename, errors)], skipped: list[str]).
    """
    from librarian import manifest
    inbox = Path(cfg.corpus_path)
    dest_dir = inbox / adapter.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen_urls = {u for u in (manifest.read_url(p) for p in inbox.rglob("*.md")) if u}
    taken = {p.name for p in dest_dir.glob("*.md")}
    written, rejected, skipped = [], [], []
    for filename, text in adapter.nodes(src_dir):
        fm, body = parse(text)
        errs = validate(fm, body)
        if errs:
            rejected.append((filename, errs))
            continue
        url = fm["url"]
        if url in seen_urls:
            skipped.append(filename)
            continue
        seen_urls.add(url)
        dest = unicodedata.normalize("NFC", filename)
        stem = dest[:-3] if dest.endswith(".md") else dest
        n = 2
        while dest in taken:
            dest = f"{stem}_{n}.md"
            n += 1
        taken.add(dest)
        (dest_dir / dest).write_text(unicodedata.normalize("NFC", text), encoding="utf-8")
        written.append(f"{adapter.name}/{dest}")
    return written, rejected, skipped
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest librarian/tests/test_adapters_base.py -q`
Expected: PASS (13 tests).

- [ ] **Step 6: Commit**

```bash
git add librarian/adapters/__init__.py librarian/adapters/base.py librarian/tests/test_adapters_base.py
git commit -m "feat(librarian): node-contract adapters/base with ingest_to_inbox"
```

---

## Task 3: Zhihu adapter — `adapters/zhihu.py`

**Files:**
- Create: `librarian/adapters/zhihu.py`
- Test: `librarian/tests/test_adapter_zhihu.py`

Context: the zhihu-fetcher (`~/workspace/playground/zhihu`) writes flat `*.md` files whose frontmatter already carries `title`, `source: zhihu`, `url`, `voteup`, `images`, `interaction_action`, `interaction_time`, `activity_id`. It is treated as an opaque producer (spec §6: "referenced, never forked"), so the adapter only reads its output directory and passes each article through unchanged; `ingest_to_inbox` enforces the contract.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_adapter_zhihu.py`:

```python
from librarian.adapters import zhihu, base

ARTICLE = (
    '---\n'
    'title: "Claude Code绘图技巧"\n'
    'author: "社区"\n'
    'source: zhihu\n'
    'url: "https://zhuanlan.zhihu.com/p/204831"\n'
    'voteup: 8\n'
    'images: 2\n'
    'interaction_time: "2026-06-11T03:34:05.554000+00:00"\n'
    '---\n\n'
    '# Claude Code绘图技巧\n\n正文。\n'
)


def test_nodes_yield_each_markdown_file(tmp_path):
    (tmp_path / "0001_a.md").write_text(ARTICLE, encoding="utf-8")
    (tmp_path / "0002_b.md").write_text(ARTICLE.replace("204831", "204832"),
                                        encoding="utf-8")
    items = list(zhihu.ZhihuAdapter().nodes(tmp_path))
    assert [name for name, _ in items] == ["0001_a.md", "0002_b.md"]


def test_zhihu_output_passes_the_contract(tmp_path):
    fm, body = base.parse(ARTICLE)
    assert base.validate(fm, body) == []


def test_ingest_files_zhihu_articles_into_inbox(cfg, tmp_path):
    src = tmp_path / "fetched"
    src.mkdir()
    (src / "0001_a.md").write_text(ARTICLE, encoding="utf-8")
    written, rejected, skipped = base.ingest_to_inbox(zhihu.ZhihuAdapter(), src, cfg)
    assert written == ["zhihu/0001_a.md"]
    assert (cfg.corpus_path / "zhihu" / "0001_a.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_adapter_zhihu.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.adapters.zhihu'`

- [ ] **Step 3: Write the implementation**

Create `librarian/adapters/zhihu.py`:

```python
"""Lead adapter (spec §6): the zhihu-fetcher producer already emits the node
contract verbatim (title / source: zhihu / url / interaction_time frontmatter),
so this adapter only reads the producer's output directory and passes each
article through unchanged. The fetcher is opaque — referenced, never forked."""
from pathlib import Path
from librarian.adapters import base


class ZhihuAdapter(base.Adapter):
    name = "zhihu"

    def nodes(self, src_dir):
        for f in sorted(Path(src_dir).glob("*.md")):
            yield f.name, f.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_adapter_zhihu.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/adapters/zhihu.py librarian/tests/test_adapter_zhihu.py
git commit -m "feat(librarian): zhihu lead adapter (pass-through)"
```

---

## Task 4: Generic adapter — `adapters/markdown_passthrough.py`

**Files:**
- Create: `librarian/adapters/markdown_passthrough.py`
- Test: `librarian/tests/test_adapter_markdown_passthrough.py`

Context: a directory of plain Markdown files that already carry frontmatter. The adapter injects `source: <source_name>` when absent (the common gap); everything else must already satisfy the contract — notably a stable `url` dedup key, without which the node is genuinely un-ingestable and is rejected.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_adapter_markdown_passthrough.py`:

```python
from librarian.adapters import markdown_passthrough as mp
from librarian.adapters import base


def test_adapter_name_is_the_source_name():
    assert mp.MarkdownPassthroughAdapter("blog").name == "blog"


def test_injects_missing_source(tmp_path):
    (tmp_path / "a.md").write_text(
        '---\ntitle: "T"\nurl: "u1"\n---\nBody\n', encoding="utf-8")
    items = list(mp.MarkdownPassthroughAdapter("blog").nodes(tmp_path))
    fm, _ = base.parse(items[0][1])
    assert fm["source"] == "blog"


def test_keeps_existing_source(tmp_path):
    (tmp_path / "a.md").write_text(
        '---\ntitle: "T"\nsource: rss\nurl: "u1"\n---\nBody\n', encoding="utf-8")
    items = list(mp.MarkdownPassthroughAdapter("blog").nodes(tmp_path))
    fm, _ = base.parse(items[0][1])
    assert fm["source"] == "rss"


def test_ingest_files_passthrough_node(cfg, tmp_path):
    src = tmp_path / "md"
    src.mkdir()
    (src / "a.md").write_text('---\ntitle: "T"\nurl: "u1"\n---\nBody\n',
                              encoding="utf-8")
    adapter = mp.MarkdownPassthroughAdapter("blog")
    written, rejected, skipped = base.ingest_to_inbox(adapter, src, cfg)
    assert written == ["blog/a.md"]


def test_ingest_rejects_node_without_url(cfg, tmp_path):
    src = tmp_path / "md"
    src.mkdir()
    (src / "a.md").write_text('---\ntitle: "T"\n---\nBody\n', encoding="utf-8")
    adapter = mp.MarkdownPassthroughAdapter("blog")
    written, rejected, skipped = base.ingest_to_inbox(adapter, src, cfg)
    assert written == []
    assert rejected and any("url" in e for e in rejected[0][1])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_adapter_markdown_passthrough.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.adapters.markdown_passthrough'`

- [ ] **Step 3: Write the implementation**

Create `librarian/adapters/markdown_passthrough.py`:

```python
"""Generic adapter for a directory of Markdown files that already carry
frontmatter. Injects `source: <source_name>` when absent; everything else must
already satisfy the node contract (notably a stable `url` dedup key) or the node
is rejected by ingest_to_inbox."""
from pathlib import Path
from librarian.adapters import base


class MarkdownPassthroughAdapter(base.Adapter):
    def __init__(self, source_name):
        self.name = source_name

    def nodes(self, src_dir):
        for f in sorted(Path(src_dir).rglob("*.md")):
            text = f.read_text(encoding="utf-8")
            fm, _ = base.parse(text)
            if not fm.get("source"):
                text = base.set_field(text, "source", self.name)
            yield f.name, text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_adapter_markdown_passthrough.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/adapters/markdown_passthrough.py librarian/tests/test_adapter_markdown_passthrough.py
git commit -m "feat(librarian): markdown_passthrough generic adapter"
```

---

## Task 5: Wave builder — `orchestrate/build_wave.py`

**Files:**
- Create: `librarian/orchestrate/__init__.py`
- Create: `librarian/orchestrate/build_wave.py`
- Test: `librarian/tests/test_build_wave.py`

Context (ported from `mybooks/scripts/build_wave.py`): pick the next `agents_per_wave * articles_per_agent` *unlabeled* manifest rows, split them across agents, and write one assignment `.md` per agent. Each assignment embeds the active topic canon + per-article fields (`relative_path`, `title`, `original_category` from legacy, `content_hash`, `source_path`, `v1_reference`). The downstream parallel dispatch + JSON write is the skill's job (`dispatching-parallel-agents`), not this module's.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_build_wave.py`:

```python
from librarian import contract, tsv, registry
from librarian.orchestrate import build_wave

MANIFEST = [[f"zhihu/a{i}.md", f"title{i}", "zhihu", f"{i:016x}"] for i in range(6)]
REG_ROWS = [["T0001", "文学评论", "", "", "active", "", "", ""],
            ["T0002", "思想史", "", "", "proposed", "", "", ""]]


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, REG_ROWS)
    return registry.load(p)


def test_select_skips_labeled_and_caps():
    rows = build_wave.select(MANIFEST, labeled_paths=["zhihu/a0.md"], limit=3)
    assert [r[0] for r in rows] == ["zhihu/a1.md", "zhihu/a2.md", "zhihu/a3.md"]


def test_assignments_split_near_even():
    rows = MANIFEST[:5]
    slices = build_wave.assignments(rows, n_agents=2)
    assert [len(s) for s in slices] == [3, 2]


def test_assignments_drop_empty_slices():
    slices = build_wave.assignments(MANIFEST[:1], n_agents=4)
    assert len(slices) == 1


def test_canon_line_is_active_topics_only(tmp_path):
    assert build_wave.canon_line(_reg(tmp_path)) == "文学评论"


def test_build_writes_one_file_per_agent(cfg, tmp_path):
    cfg.agents_per_wave = 2
    cfg.articles_per_agent = 2
    legacy = {"zhihu/a0.md": ("AI与机器学习", "深度学习")}
    files, canon = build_wave.build(
        MANIFEST, labeled_paths=[], reg=_reg(tmp_path), legacy=legacy,
        out_dir=cfg.wave_assign_dir, vault=cfg.corpus_path, cfg=cfg, wave_no=1)
    assert [f.name for f in files] == ["wave01_agent1.md", "wave01_agent2.md"]
    text = files[0].read_text(encoding="utf-8")
    assert "wave 1, agent 1" in text
    assert "Active topics: 文学评论" in text
    assert "relative_path\tzhihu/a0.md" in text
    assert "original_category\tAI与机器学习" in text
    assert f"source_path\t{cfg.corpus_path}/zhihu/a0.md" in text
    assert "v1_reference\tAI与机器学习 | 深度学习" in text
    # a1 has no legacy row
    assert "v1_reference\tnone" in files[1].read_text(encoding="utf-8")


def test_build_caps_total_at_wave_size(cfg, tmp_path):
    cfg.agents_per_wave = 2
    cfg.articles_per_agent = 2          # wave size 4
    files, _ = build_wave.build(
        MANIFEST, labeled_paths=[], reg=_reg(tmp_path), legacy={},
        out_dir=cfg.wave_assign_dir, vault=cfg.corpus_path, cfg=cfg, wave_no=1)
    total = sum(t.count("## Article ")
                for t in (f.read_text(encoding="utf-8") for f in files))
    assert total == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_build_wave.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.orchestrate'`

- [ ] **Step 3: Create the package marker**

Create `librarian/orchestrate/__init__.py` (empty file):

```python
```

- [ ] **Step 4: Write the implementation**

Create `librarian/orchestrate/build_wave.py`:

```python
"""Build one labeling wave (spec §5 step 3): select the next slice of unlabeled
articles, split them across N agents, and write one assignment file per agent
embedding the active topic canon. The parallel dispatch + JSON write is done by
the orchestrating skill (dispatching-parallel-agents); this module only prepares
the assignments — ingest_wave later collects the results."""
import unicodedata
from librarian import manifest, registry, store


def select(manifest_rows, labeled_paths, limit):
    """The first `limit` manifest rows whose relative_path is not yet labeled.
    Paths are NFC-normalized on both sides so CJK NFC/NFD drift can't leak an
    already-labeled article back into a wave."""
    done = {unicodedata.normalize("NFC", p) for p in labeled_paths}
    todo = [r for r in manifest_rows
            if unicodedata.normalize("NFC", r[0]) not in done]
    return todo[:limit]


def assignments(rows, n_agents):
    """Split rows into n_agents near-even contiguous slices (earlier slices may
    be one longer). Empty slices are dropped."""
    if n_agents < 1:
        raise ValueError("n_agents must be >= 1")
    per = -(-len(rows) // n_agents)  # ceil
    slices = [rows[i:i + per] for i in range(0, len(rows), per)] if per else []
    return [s for s in slices if s]


def canon_line(reg):
    """Semicolon-joined active topic names, for embedding in the agent prompt."""
    return "; ".join(sorted(reg.active_names()))


def _agent_file(wave_no, agent_no, rows, legacy_nfc, canon, vault):
    out = [f"# Labeling — wave {wave_no}, agent {agent_no} ({len(rows)} articles)\n",
           "Read each article's FULL text at source_path. Classify into the "
           "active canon below; propose new topics (in the canon language) only "
           "when nothing fits. Write the summary in the article's own language.\n",
           f"\nActive topics: {canon or '(none yet — seed the canon)'}\n"]
    for j, r in enumerate(rows, start=1):
        rel, title = r[0], r[1]
        v1 = legacy_nfc.get(unicodedata.normalize("NFC", rel))
        ref = f"{v1[0]} | {v1[1]}" if v1 else "none"
        out += [f"\n## Article {j}\n",
                f"relative_path\t{rel}\n",
                f"title\t{title}\n",
                f"original_category\t{v1[0] if v1 else ''}\n",
                f"content_hash\t{r[3]}\n",
                f"source_path\t{vault}/{rel}\n",
                f"v1_reference\t{ref}\n"]
    return "".join(out)


def build(manifest_rows, labeled_paths, reg, legacy, out_dir, vault, cfg, wave_no):
    """Write one assignment .md per agent into out_dir. Wave size =
    cfg.agents_per_wave * cfg.articles_per_agent. Returns (files, canon)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    limit = cfg.agents_per_wave * cfg.articles_per_agent
    rows = select(manifest_rows, labeled_paths, limit)
    canon = canon_line(reg)
    files = []
    for ai, slice_rows in enumerate(assignments(rows, cfg.agents_per_wave), start=1):
        p = out_dir / f"wave{wave_no:02d}_agent{ai}.md"
        p.write_text(_agent_file(wave_no, ai, slice_rows, legacy_nfc, canon, vault),
                     encoding="utf-8")
        files.append(p)
    return files, canon


if __name__ == "__main__":
    import os
    import sys
    from librarian import config
    from librarian.update import load_legacy
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    wave_no = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    manifest_rows = manifest.build(cfg.corpus_path, cfg)
    labeled = [r[0] for r in store.load(cfg.labels_path)]
    reg = registry.load(cfg.topics_path)
    legacy = load_legacy(cfg.legacy_labels)
    files, canon = build(manifest_rows, labeled, reg, legacy,
                         cfg.wave_assign_dir, cfg.corpus_path, cfg, wave_no)
    print(f"wave {wave_no}: wrote {len(files)} agent assignment(s) "
          f"to {cfg.wave_assign_dir}; have agents write JSON to {cfg.wave_out_dir}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest librarian/tests/test_build_wave.py -q`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add librarian/orchestrate/__init__.py librarian/orchestrate/build_wave.py librarian/tests/test_build_wave.py
git commit -m "feat(librarian): orchestrate.build_wave — select + per-agent assignments"
```

---

## Task 6: Wave ingester — `orchestrate/ingest_wave.py`

**Files:**
- Create: `librarian/orchestrate/ingest_wave.py`
- Test: `librarian/tests/test_ingest_wave.py`

Context (ported from `mybooks/scripts/ingest_wave.py`): agents self-write a JSON array, one object per article, carrying only the 10 judgment fields (`relative_path`, `primary_category`, `topics`, `tags`, `article_type`, `summary`, `confidence`, `needs_review`, `review_reason`, `proposed_topics`). The ingester reconstructs the full 15-column `LABEL_COLUMNS` row by pulling the *frozen* fields (`title`, `content_hash` from the manifest; `original_category` from legacy) so agents cannot fabricate them, validates against the canon, and merges into the labels store. Proposals are reported, not promoted.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_ingest_wave.py`:

```python
import json

from librarian import contract, tsv, registry, store
from librarian.orchestrate import ingest_wave

MANIFEST = [["zhihu/a0.md", "Title Zero", "zhihu", "0" * 16],
            ["zhihu/a1.md", "Title One", "zhihu", "1" * 16]]
REG_ROWS = [["T0001", "深度学习", "", "", "active", "", "", ""]]


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, REG_ROWS)
    return registry.load(p)


def _judgment(rel="zhihu/a0.md", primary="AI与机器学习", topics=None,
              proposed=None, review=False):
    return {"relative_path": rel, "primary_category": primary,
            "topics": topics or ["深度学习"], "tags": ["YOLO"],
            "article_type": "学术解读", "summary": "摘要。",
            "confidence": "high", "needs_review": review,
            "review_reason": "", "proposed_topics": proposed or []}


def _write_json(tmp_path, objs, name="wave01_agent1.json"):
    p = tmp_path / name
    p.write_text(json.dumps(objs, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _cfg(cfg):
    cfg.categories = {"AI与机器学习"}
    return cfg


def test_ingest_merges_rows_with_frozen_fields(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    summary = ingest_wave.ingest([jp], MANIFEST, legacy={}, reg=_reg(tmp_path),
                                 cfg=cfg, today="2026-06-13")
    assert summary["errors"] == []
    assert summary["merged"] == 1
    rows = store.load(cfg.labels_path)
    r = rows[0]
    assert r[0] == "zhihu/a0.md"
    assert r[1] == "Title Zero"          # frozen title from manifest
    assert r[3] == "AI与机器学习"          # primary from agent
    assert r[4] == "深度学习"             # topics joined
    assert r[12] == "0" * 16             # frozen content_hash from manifest
    assert r[13] == cfg.extractor_version
    assert r[14] == "2026-06-13"


def test_original_category_comes_from_legacy(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    legacy = {"zhihu/a0.md": ("旧类", "旧子类")}
    ingest_wave.ingest([jp], MANIFEST, legacy, _reg(tmp_path), cfg, "2026-06-13")
    assert store.load(cfg.labels_path)[0][2] == "旧类"


def test_needs_review_bool_becomes_lowercase_string(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(review=True)])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["review"] == 1
    assert store.load(cfg.labels_path)[0][9] == "true"


def test_off_canon_primary_blocks_the_whole_wave(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(primary="不存在类")])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("primary" in e for e in summary["errors"])
    assert store.load(cfg.labels_path) == []


def test_fabricated_path_is_skipped_not_merged(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(rel="zhihu/ghost.md")])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["skipped"] == ["zhihu/ghost.md"]
    assert summary["merged"] == 0


def test_proposed_topic_is_recorded_and_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(topics=["新话题"], proposed=["新话题"])])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 1
    assert "新话题" in summary["proposals"]
    # canon untouched — proposal recorded, not promoted
    assert "新话题" not in registry.load(cfg.topics_path).active_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_ingest_wave.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.orchestrate.ingest_wave'`

- [ ] **Step 3: Write the implementation**

Create `librarian/orchestrate/ingest_wave.py`:

```python
"""Collect one wave's labeling output (spec §5 step 3): read the agent-written
JSON files, reconstruct full label rows using the FROZEN manifest fields (title,
content_hash) + legacy original_category — agents never supply those, so they
can't fabricate them — validate against the canon, and merge into the labels
store. Proposed topics are recorded (validate accepts them) but NOT promoted
here; promotion stays a deliberate gate action (proposals.accept, GATE 2)."""
import json
import unicodedata
from pathlib import Path
from librarian import (contract, tsv, manifest, registry, validate, store,
                       proposals)

PATH_I = contract.LABEL_COLUMNS.index("relative_path")
REVIEW_I = contract.LABEL_COLUMNS.index("needs_review")


def _multi(v):
    """Agent JSON gives topics/tags/proposed as a list; join to the TSV form
    (deduped, '; '-separated). A bare string is passed through trimmed."""
    if isinstance(v, list):
        return tsv.join_multi([str(x).strip() for x in v if str(x).strip()])
    return str(v).strip()


def _frozen_index(manifest_rows, legacy):
    """{NFC relative_path: (title, original_category, content_hash)}; the title
    and hash are frozen from the manifest, original_category from legacy v1."""
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    idx = {}
    for r in manifest_rows:
        rel = unicodedata.normalize("NFC", r[0])
        v1 = legacy_nfc.get(rel)
        idx[rel] = (r[1], v1[0] if v1 else "", r[3])
    return idx


def _row(j, frozen, cfg, today):
    """One full LABEL_COLUMNS row from an agent judgment object `j` and the
    frozen (title, original_category, content_hash) tuple."""
    title, original_category, content_hash = frozen
    return [
        unicodedata.normalize("NFC", j["relative_path"]),
        title,
        original_category,
        str(j.get("primary_category", "")).strip(),
        _multi(j.get("topics", [])),
        _multi(j.get("tags", [])),
        str(j.get("article_type", "")).strip(),
        str(j.get("summary", "")).strip(),
        str(j.get("confidence", "")).strip(),
        "true" if j.get("needs_review") else "false",
        str(j.get("review_reason", "")).strip(),
        _multi(j.get("proposed_topics", [])),
        content_hash,
        cfg.extractor_version,
        today,
    ]


def ingest(json_paths, manifest_rows, legacy, reg, cfg, today):
    """Read agent JSON outputs and merge validated rows into cfg.labels_path.
    Rows whose path is not in the manifest are skipped (fabricated). On ANY
    validation error nothing is written. Returns a summary dict:
      {"merged", "review", "errors": [...], "skipped": [...], "proposals": [...]}
    """
    frozen = _frozen_index(manifest_rows, legacy)
    rows, skipped = [], []
    for jp in sorted(str(p) for p in json_paths):
        for j in json.loads(Path(jp).read_text(encoding="utf-8")):
            rel = unicodedata.normalize("NFC", j["relative_path"])
            if rel not in frozen:
                skipped.append(rel)
                continue
            rows.append(_row(j, frozen[rel], cfg, today))
    expected = [r[PATH_I] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        return {"merged": 0, "review": 0, "errors": errors,
                "skipped": skipped, "proposals": []}
    store.merge(cfg.labels_path, rows)
    n_review = sum(1 for r in rows if r[REVIEW_I] == "true")
    validate.log_progress(cfg.progress_path, "wave", len(rows), n_review)
    pend = [p[0] for p in proposals.pending(store.load(cfg.labels_path), reg)]
    return {"merged": len(rows), "review": n_review, "errors": [],
            "skipped": skipped, "proposals": pend}


if __name__ == "__main__":
    import os
    import sys
    from datetime import date
    from librarian import config
    from librarian.update import load_legacy
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    paths = sys.argv[1:] or [str(p) for p in sorted(cfg.wave_out_dir.glob("*.json"))]
    manifest_rows = manifest.build(cfg.corpus_path, cfg)
    legacy = load_legacy(cfg.legacy_labels)
    reg = registry.load(cfg.topics_path)
    summary = ingest(paths, manifest_rows, legacy, reg, cfg, str(date.today()))
    if summary["errors"]:
        print("\n".join(summary["errors"]))
        sys.exit(1)
    print(f"merged {summary['merged']} rows · {summary['review']} flagged · "
          f"{len(summary['proposals'])} pending proposal(s) · "
          f"{len(summary['skipped'])} skipped")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_ingest_wave.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the FULL suite to confirm no regression**

Run: `pytest -q` (from `knowledge-library/`)
Expected: PASS — the Plan 1 suite (92 tests) plus the new ingest-path tests, all green.

- [ ] **Step 6: Commit**

```bash
git add librarian/orchestrate/ingest_wave.py librarian/tests/test_ingest_wave.py
git commit -m "feat(librarian): orchestrate.ingest_wave — JSON→validated rows, proposals reported"
```

---

## Self-Review (run after all tasks)

**1. Spec coverage (this plan's slice — spec §3 `adapters/` + `orchestrate/{build_wave,ingest_wave}`, §4 node contract, §4 config labeling knobs, §5 wave loop building blocks, §11 adapter-contract tests):**
- Normalized-node contract (spec §4: title / source / stable url / body) → `adapters/base.py` `REQUIRED_FIELDS` + `validate` (Task 2). ✓
- Adapter extension point (spec §4 "a new source = one small normalizer") → `Adapter` base + `zhihu` (Task 3) + `markdown_passthrough` (Task 4). ✓
- `url` (not content_hash) is the dedup key (spec §4) → `ingest_to_inbox` dedups on the `url` frontmatter field via `manifest.read_url` (Task 2). ✓
- Config labeling knobs `agents-per-wave`, `articles-per-agent` (spec §4) → `agents_per_wave`, `articles_per_agent` (Task 1). `model` knob is **deferred** — no Plan 2 code consumes it; it belongs with the skill-dispatch packaging (Plan 5). Noted.
- Wave loop building blocks (spec §5 step 3: build_wave → dispatch agents that self-write JSON → ingest_wave + validate) → `build_wave.build` (Task 5) + `ingest_wave.ingest` (Task 6). The repeat-until-100% *loop driver* and the GATE pauses are correctly deferred to SKILL.md (Plan 5). ✓
- Agents self-write JSON; frozen fields not fabricated (spec §5) → `ingest_wave` reconstructs title/original_category/content_hash from the manifest+legacy, not from agent output (Task 6). ✓
- Adapter-contract tests (spec §11 "a node that violates the contract is rejected") → `test_ingest_rejects_contract_violation`, `test_ingest_rejects_node_without_url` (Tasks 2, 4). ✓
- NFC at every disk↔TSV seam (spec §8) → `ingest_to_inbox` normalizes names+bodies; `select` and `_frozen_index` normalize paths (Tasks 2, 5, 6). ✓
- Fence-safe frontmatter parse (spec §8 fence bug) → `base._FENCE` mirrors `frontmatter._FENCE`; `test_parse_fence_safe_with_dashes_in_title` (Task 2). ✓
- Collision-safe `_N` dest with move-by-url semantics (spec §8) → `ingest_to_inbox` skips same-url, appends `_N` for same-name/different-url; `test_ingest_collision_keeps_both_when_url_differs` (Task 2). ✓
- Proposals NOT auto-promoted (spec §6/§7 gate model; GATE 2) → `ingest_wave` reports `proposals` but leaves `proposals.accept` to the gate; `test_proposed_topic_is_recorded_and_reported` (Task 6). ✓
- **Out of scope, correctly deferred:** `materialize --lang` localization (Plan 3); steady-state + run ledger + `first_seen_run` + `status` (Plan 4); SKILL.md / wave-loop-driver / gate pauses / scheduling (Plan 5); the `model` config knob (Plan 5). ✓

**2. Placeholder scan:** every code step contains literal code; every command step has an exact `pytest` invocation + expected result. No "TBD"/"add error handling"/"handle edge cases". The one cross-task lookup (`load_legacy`) is an existing function in `librarian/update.py` (read in Plan 1), imported by the two `__main__` blocks — not a placeholder.

**3. Type/signature consistency across tasks:**
- `base.parse(text) -> (dict, str)` — defined Task 2; used by `zhihu`/`markdown_passthrough` tests, `markdown_passthrough.nodes`, and `ingest_to_inbox`. ✓
- `base.validate(frontmatter, body) -> list` — defined Task 2; used by `ingest_to_inbox` + adapter tests. ✓
- `base.set_field(text, key, value) -> str` — defined Task 2; used by `markdown_passthrough.nodes` (Task 4). ✓
- `base.Adapter.nodes(src_dir)` yields `(filename, text)` — contract honored by `ZhihuAdapter` (Task 3) and `MarkdownPassthroughAdapter` (Task 4); consumed by `ingest_to_inbox` (Task 2). ✓
- `base.ingest_to_inbox(adapter, src_dir, cfg) -> (written, rejected, skipped)` — defined Task 2; called in Tasks 2/3/4 tests. `written` items are `"<adapter.name>/<file>"`. ✓
- `build_wave.select(manifest_rows, labeled_paths, limit)`, `.assignments(rows, n_agents)`, `.canon_line(reg)`, `.build(manifest_rows, labeled_paths, reg, legacy, out_dir, vault, cfg, wave_no) -> (files, canon)` — defined Task 5; called positionally/by-keyword in Task 5 tests with matching names. ✓
- `ingest_wave.ingest(json_paths, manifest_rows, legacy, reg, cfg, today) -> summary dict` with keys `merged/review/errors/skipped/proposals` — defined Task 6; asserted in every Task 6 test. ✓
- Existing interfaces reused unchanged: `manifest.read_url(path)`, `manifest.build(vault, cfg)`, `registry.load(path)` → `Registry.active_names()`, `validate.check(rows, expected, reg, categories) -> (rows, errors)`, `validate.log_progress(path, name, n, n_review)`, `store.merge/load(path)`, `proposals.pending(rows, reg) -> [(name, count, examples)]`, `tsv.join_multi(vals)`, `cfg.{labels_path, topics_path, progress_path, wave_assign_dir, wave_out_dir, extractor_version, agents_per_wave, articles_per_agent, categories, corpus_path}`. All verified against the ported Plan 1 sources. ✓

---

## Execution note

Plan 2 is purely additive: two new sub-packages and config fields, no edits to Plan 1 module behaviour (config gains fields with defaults; the loader gains keys). The completion signal is a green full suite (Task 6 Step 5): the 92 Plan 1 tests plus ~33 new ingest-path tests. Plan 3 (materialize `--lang`) builds on the labels these modules produce.
