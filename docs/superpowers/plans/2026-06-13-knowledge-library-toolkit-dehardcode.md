# Knowledge-Library Toolkit De-hardcode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the existing MyBooks toolkit into `knowledge-library/librarian/` as a config-driven package — every constant in `mybooks/schema.py` replaced by either a fixed data-contract module or a loaded `config.yaml` — with all ~21 ported test files green and zero coupling to the real `知乎收藏` vault. **Behaviour is preserved exactly; only the source of constants changes.**

**Architecture:** Split the old `schema.py` two ways. (1) The fixed *data contract* — column schemas and value enums (`*_COLUMNS`, `CONFIDENCE`, `BOOL`, `TOPIC_STATUS`) — moves to `librarian/contract.py` and is imported directly (it is not user-tunable; spec §4 lists none of it as config). (2) The *environmental / taxonomy / threshold* values (vault path, data dir, categories, `hub_dir`, `skip_dirs`, thresholds, batch size, marker) become fields on a `Config` dataclass loaded from `config.yaml` by `librarian/config.py`. Pure library functions that need a config value take an explicit `cfg: Config` parameter; the `update.py` CLI orchestrator holds a single module-level `cfg` injected at runtime (and monkeypatched in tests). This `update.py` is de-hardcoded **in place** — its structural split into `orchestrate/` is deferred to Plan 2.

**Tech Stack:** Python 3, `pyyaml`, `pytest`. Source toolkit: `~/workspace/playground/mybooks/mybooks/` (16 modules) + `~/workspace/playground/mybooks/tests/` (21 test files). Target: `~/Workspace/MyLibrary/knowledge-library/librarian/`.

---

## Plan-set context (this is Plan 1 of ~5)

The approved design (`docs/specs/2026-06-13-knowledge-library-skill-design.md`) is large; per the writing-plans scope check it is broken into a sequence of self-contained plans. **This plan delivers only the de-hardcoded toolkit + green tests.** The following are explicitly OUT OF SCOPE here and become later plans:

- **Plan 2** — split `update.py` into `orchestrate/{build_wave,ingest_wave,materialize,steady_state,status}`; add the adapter contract (`adapters/base.py`) + `zhihu.py` + `markdown_passthrough.py` (spec §3, §4 node contract, §6). **Includes the language-aware materialize:** `--lang en|zh` and localization of `verify`/`hubgen`/`refile` (folder names, hub filenames, hub section headers) per spec §4b — consuming the `name_zh` + `category_localization` schema laid down in Plan 1.
- **Plan 3** — steady-state mode, run ledger (`data/runs.tsv`), `first_seen_run` provenance, `librarian status`, the ~20-node synthetic end-to-end fixture (spec §7, §9, §11). **Includes the labeling-prompt language rule** (spec §4b): classify into the English canon, propose new topics in English, write the summary in the article's own language.
- **Plan 4** — assemble the skill package: `SKILL.md`, `references/`, `templates/`, recipes (spec §3, §5, §6).
- **Plan 5** — scheduling: `schedule/wrapper.sh` + launchd plist + cookie-expiry handling (spec §10).

Subsequent plans build *around* the package this plan creates at its final path, so nothing here needs to move later.

---

## Decisions locked by this plan (resolves part of spec §"Open questions")

- **Contract vs. config split:** column lists + enums are a fixed contract (`contract.py`), not `config.yaml` keys. This matches spec §4, which lists only `corpus_path`, `library_path`, `categories`, `hub_dir`, `hub_min_articles`, `split_threshold`, `skip_dirs`, delimiters, NFC flag, and labeling knobs as config.
- **Config delivery:** library functions take `cfg` as an explicit parameter (testable, no globals); `update.py` keeps a module-level `cfg` (behaviour-preserving; the clean DI version arrives with the Plan 2 split).
- **Package home:** `knowledge-library/librarian/` (final location — no later move). Tests live in `knowledge-library/librarian/tests/`; pytest runs from `knowledge-library/`.
- **`generated_marker` default** changes from `"generated: mybooks"` to `"generated: knowledge-library"`. Tests read `cfg.generated_marker` (never the literal), so this is invisible to them.
- **Language schema (spec §4b):** the controlled vocabulary is English-canonical with Chinese as a display localization. The *foundational schema* lands here because Plan 1 owns `contract.py` + `config.py`: a `name_zh` column **appended** to `contract.TOPIC_COLUMNS` (appended, so `registry`/`proposals` positional reads are untouched and behaviour is preserved — the field is carried, not yet consumed), plus config `label_language` (default `en`), `category_localization` (`{canonical: {zh: …}}`), and a `localize_category()` helper. The *consumers* — `materialize --lang`, language-aware `verify`/`hubgen`/`refile`, and the labeling prompt — are deferred to Plans 2–3. Net effect on Plan 1: topic-row test fixtures gain one trailing `""` (the empty `name_zh`); no logic changes.

---

## File Structure

Created in this plan (all under `knowledge-library/`):

```
knowledge-library/
├── conftest.py                  # puts knowledge-library/ on sys.path; defines the `cfg` pytest fixture
├── pytest.ini                   # rootdir + testpaths
├── config.example.yaml          # the config contract, filled with the Zhihu worked example
└── librarian/
    ├── __init__.py              # empty (package marker)
    ├── contract.py              # NEW — fixed data contract (column lists + enums; TOPIC_COLUMNS incl. name_zh)
    ├── config.py                # NEW — Config dataclass + load() + localization (label_language, category_localization, localize_category)
    ├── tsv.py                   # ported verbatim (0 schema refs)
    ├── cooccur.py               # ported (import swap only)
    ├── reconcile.py             # ported verbatim (0 schema refs)
    ├── refile.py                # ported verbatim (0 schema refs)
    ├── frontmatter.py           # ported verbatim (0 schema refs)
    ├── batches.py               # ported (import swap only)
    ├── store.py                 # ported — schema→contract
    ├── registry.py              # ported — schema→contract
    ├── proposals.py             # ported — schema→contract
    ├── validate.py              # ported — schema→contract
    ├── manifest.py              # ported — schema→contract + cfg threading (skip_dirs)
    ├── audit.py                 # ported — cfg threading (thresholds)
    ├── hubgen.py                # ported — schema→contract + cfg threading
    ├── verify.py                # ported — schema→contract + cfg threading
    ├── update.py                # ported — schema→contract + cfg threading (the big one)
    └── tests/
        ├── (21 ported test files — see tasks)
        └── ...
```

**Note: `schema.py` is NOT ported.** Its contents are redistributed into `contract.py` (fixed) and `config.py` (tunable). No file named `schema.py` exists in `librarian/`.

**The mybooks repo is read-only source material — never modified.** Every "port" step copies *from* `~/workspace/playground/mybooks/` *into* `knowledge-library/librarian/`.

---

## Constant → destination map (reference for all port tasks)

| Old `schema.X` | New home | Access |
|---|---|---|
| `MANIFEST_COLUMNS`, `TOPIC_COLUMNS`, `LABEL_COLUMNS` | `contract.py` | `contract.X` |
| `CONFIDENCE`, `BOOL`, `TOPIC_STATUS` | `contract.py` | `contract.X` |
| `VAULT` | `Config.corpus_path` | `cfg.corpus_path` |
| `DATA` | `Config.data_dir` | `cfg.data_dir` |
| `LEGACY_LABELS` | derived | `cfg.legacy_labels` |
| `HUB_DIR` | `Config.hub_dir` | `cfg.hub_dir` |
| `SKIP_DIRS` | `Config.skip_dirs` | `cfg.skip_dirs` |
| `CATEGORIES_V1` | `Config.categories` | `cfg.categories` |
| `GENERATED_MARKER` | `Config.generated_marker` | `cfg.generated_marker` |
| `HUB_MIN_ARTICLES` | `Config.hub_min_articles` | `cfg.hub_min_articles` |
| `TOPIC_SPLIT_THRESHOLD` | `Config.topic_split_threshold` | `cfg.topic_split_threshold` |
| magic `30` (batch size, `update.py:80`) | `Config.batch_size` | `cfg.batch_size` |
| `DATA/"article_labels.tsv"` etc. | derived properties | `cfg.labels_path`, `cfg.topics_path`, `cfg.manifest_path`, `cfg.batches_dir`, `cfg.progress_path`, `cfg.migration_log_path` |

---

### Task 1: Package scaffold + fixed data contract

**Files:**
- Create: `knowledge-library/librarian/__init__.py`
- Create: `knowledge-library/librarian/contract.py`
- Create: `knowledge-library/conftest.py`
- Create: `knowledge-library/pytest.ini`
- Create: `knowledge-library/librarian/tests/test_contract.py`

- [ ] **Step 1: Create the package marker and pytest wiring**

`knowledge-library/librarian/__init__.py` — empty file.

`knowledge-library/pytest.ini`:

```ini
[pytest]
testpaths = librarian/tests
python_files = test_*.py
```

`knowledge-library/conftest.py`:

```python
import sys
from pathlib import Path

import pytest

# Put knowledge-library/ on sys.path so `import librarian` resolves when
# pytest is invoked from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from librarian import config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    """A throwaway Config pointing at tmp_path. The default `cfg` for tests that
    only need config values (skip_dirs, thresholds, hub_dir, marker)."""
    return config.Config(
        corpus_path=tmp_path / "vault",
        library_path=tmp_path / "vault",
        data_dir=tmp_path / "data",
        categories={"文学", "历史人文", "AI与机器学习"},
    )
```

(`config` is created in Task 2; the import will fail until then — that is fine, Task 1's own test does not import it. To keep Task 1 runnable in isolation, the `from librarian import config` line and the `cfg` fixture may be added in Task 2 instead. **Recommended: add the full `conftest.py` above now and run Task 1's test with `-p no:cacheprovider` ignoring collection of other dirs — or simply create `config.py`'s skeleton in Task 1.** To avoid the ordering hazard, create a minimal stub `librarian/config.py` now containing only `from dataclasses import dataclass` + an empty `Config` so collection succeeds; Task 2 fleshes it out.)

Minimal stub `knowledge-library/librarian/config.py` (Task 2 replaces it entirely):

```python
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:  # stub, fully defined in Task 2
    corpus_path: Path
    library_path: Path
    data_dir: Path
    categories: set = field(default_factory=set)
```

- [ ] **Step 2: Write the failing contract test**

`knowledge-library/librarian/tests/test_contract.py`:

```python
from librarian import contract


def test_label_columns_complete_and_ordered():
    assert contract.LABEL_COLUMNS[0] == "relative_path"
    assert contract.LABEL_COLUMNS[-1] == "labeled_at"
    assert len(contract.LABEL_COLUMNS) == 15
    assert len(set(contract.LABEL_COLUMNS)) == 15


def test_manifest_and_topic_columns():
    assert contract.MANIFEST_COLUMNS == [
        "relative_path", "title", "folder", "content_hash"]
    # name_zh is APPENDED last so registry/proposals positional reads (r[1]..r[6])
    # are unchanged; it holds the Chinese display name for the canonical English name.
    assert contract.TOPIC_COLUMNS == [
        "topic_id", "name", "aliases", "parent_topic", "status",
        "description", "created_at", "name_zh"]
    assert contract.TOPIC_COLUMNS[-1] == "name_zh"


def test_enums():
    assert contract.CONFIDENCE == {"high", "medium", "low"}
    assert contract.BOOL == {"true", "false"}
    assert contract.TOPIC_STATUS == {"active", "proposed", "merged"}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_contract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.contract'`.

- [ ] **Step 4: Create `contract.py`**

`knowledge-library/librarian/contract.py`:

```python
"""The fixed data contract: TSV column schemas and value enums. Unlike the
environmental values in config.py, these define the normalized-node / label
record shape and are not user-tunable."""

MANIFEST_COLUMNS = ["relative_path", "title", "folder", "content_hash"]

# name_zh is appended LAST: registry.py and proposals.py read topic rows
# positionally (r[1]=name … r[6]=created_at), so appending leaves them intact.
# It carries the Chinese display name beside the canonical English `name`
# (spec §4b); unused until the language-aware materialize in Plan 2.
TOPIC_COLUMNS = ["topic_id", "name", "aliases", "parent_topic", "status",
                 "description", "created_at", "name_zh"]

LABEL_COLUMNS = ["relative_path", "title", "original_category",
                 "primary_category", "topics", "tags", "article_type",
                 "summary", "confidence", "needs_review", "review_reason",
                 "proposed_topics", "content_hash", "extractor_version",
                 "labeled_at"]

CONFIDENCE = {"high", "medium", "low"}
BOOL = {"true", "false"}
TOPIC_STATUS = {"active", "proposed", "merged"}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_contract.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/
git commit -m "feat(librarian): scaffold package + fixed data contract"
```

---

### Task 2: Config dataclass + loader + config example

**Files:**
- Modify (replace stub): `knowledge-library/librarian/config.py`
- Create: `knowledge-library/config.example.yaml`
- Create: `knowledge-library/librarian/tests/test_config.py`

- [ ] **Step 1: Write the failing config test**

`knowledge-library/librarian/tests/test_config.py`:

```python
from pathlib import Path

from librarian import config


def test_defaults_match_legacy_schema():
    c = config.Config(corpus_path=Path("/v"), library_path=Path("/v"),
                       data_dir=Path("/d"), categories={"文学"})
    assert c.hub_dir == "_topics"
    assert c.skip_dirs == {"_images", "分类视图", "话题", "_topics"}
    assert c.hub_min_articles == 3
    assert c.topic_split_threshold == 40
    assert c.batch_size == 30
    assert c.generated_marker == "generated: knowledge-library"
    assert c.label_language == "en"          # English-canonical vocab (spec §4b)
    assert c.category_localization == {}      # no display map by default


def test_derived_paths():
    c = config.Config(corpus_path=Path("/v"), library_path=Path("/v"),
                      data_dir=Path("/d"), categories={"文学"})
    assert c.labels_path == Path("/d/article_labels.tsv")
    assert c.topics_path == Path("/d/topics.tsv")
    assert c.manifest_path == Path("/d/manifest.tsv")
    assert c.batches_dir == Path("/d/batches")
    assert c.progress_path == Path("/d/progress.tsv")
    assert c.migration_log_path == Path("/d/migration_log.tsv")
    assert c.legacy_labels == Path("/d/legacy_category_labels.tsv")


def test_load_from_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "corpus_path: /inbox\n"
        "library_path: /lib\n"
        "data_dir: /data\n"
        "categories: [文学, 历史人文]\n"
        "hub_min_articles: 5\n",
        encoding="utf-8")
    c = config.load(tmp_path / "config.yaml")
    assert c.corpus_path == Path("/inbox")
    assert c.library_path == Path("/lib")
    assert c.categories == {"文学", "历史人文"}
    assert c.hub_min_articles == 5          # overridden
    assert c.topic_split_threshold == 40    # default preserved


def test_load_nfc_normalizes_categories(tmp_path):
    import unicodedata
    nfd = unicodedata.normalize("NFD", "café")
    (tmp_path / "c.yaml").write_text(
        f"corpus_path: /v\nlibrary_path: /v\ndata_dir: /d\n"
        f"categories: ['{nfd}']\n", encoding="utf-8")
    c = config.load(tmp_path / "c.yaml")
    assert unicodedata.normalize("NFC", "café") in c.categories


def test_localize_category_round_trips(tmp_path):
    (tmp_path / "c.yaml").write_text(
        "corpus_path: /v\nlibrary_path: /v\ndata_dir: /d\n"
        "categories: [Literature, History]\n"
        "category_localization:\n"
        "  Literature: {zh: 文学}\n"
        "  History: {zh: 历史人文}\n",
        encoding="utf-8")
    c = config.load(tmp_path / "c.yaml")
    # canonical language (en) returns the canonical name verbatim, no lookup
    assert c.localize_category("Literature", "en") == "Literature"
    # zh looks up the display map
    assert c.localize_category("Literature", "zh") == "文学"
    # unknown language or unmapped category falls back to the canonical name
    assert c.localize_category("Literature", "fr") == "Literature"
    assert c.localize_category("Unmapped", "zh") == "Unmapped"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_config.py -v`
Expected: FAIL — the stub `Config` lacks `hub_dir`/`labels_path`/`load`.

- [ ] **Step 3: Write `config.py` (replace the Task 1 stub entirely)**

`knowledge-library/librarian/config.py`:

```python
"""Loads config.yaml into a Config dataclass, replacing every tunable constant
that mybooks/schema.py used to hardcode. The fixed data contract lives in
contract.py, not here."""
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _nfc_set(values):
    return {unicodedata.normalize("NFC", v) for v in values}


@dataclass
class Config:
    corpus_path: Path                 # was schema.VAULT — the inbox / source vault
    library_path: Path                # the materialized output vault
    data_dir: Path                    # was schema.DATA — TSV state directory
    categories: set                   # was schema.CATEGORIES_V1 — primary canon
    hub_dir: str = "_topics"
    skip_dirs: set = field(
        default_factory=lambda: {"_images", "分类视图", "话题", "_topics"})
    generated_marker: str = "generated: knowledge-library"
    hub_min_articles: int = 3
    topic_split_threshold: int = 40
    batch_size: int = 30
    legacy_labels_name: str = "legacy_category_labels.tsv"
    # Language (spec §4b): the controlled vocabulary is canonical in
    # label_language; category_localization maps a canonical category name to
    # its display names per language, e.g. {"Literature": {"zh": "文学"}}.
    label_language: str = "en"
    category_localization: dict = field(default_factory=dict)

    def localize_category(self, canonical, lang):
        """The display name for a canonical category in `lang`. Returns the
        canonical name unchanged when lang is the canon language or no mapping
        exists (consumed by the language-aware materialize in Plan 2)."""
        if lang == self.label_language:
            return canonical
        return self.category_localization.get(canonical, {}).get(lang, canonical)

    @property
    def labels_path(self):
        return self.data_dir / "article_labels.tsv"

    @property
    def topics_path(self):
        return self.data_dir / "topics.tsv"

    @property
    def manifest_path(self):
        return self.data_dir / "manifest.tsv"

    @property
    def batches_dir(self):
        return self.data_dir / "batches"

    @property
    def progress_path(self):
        return self.data_dir / "progress.tsv"

    @property
    def migration_log_path(self):
        return self.data_dir / "migration_log.tsv"

    @property
    def legacy_labels(self):
        return self.data_dir / self.legacy_labels_name


def load(path):
    """Read a config.yaml file into a Config. Unknown keys are ignored; missing
    optional keys fall back to dataclass defaults."""
    raw = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8")) or {}
    kwargs = dict(
        corpus_path=Path(raw["corpus_path"]).expanduser(),
        library_path=Path(raw["library_path"]).expanduser(),
        data_dir=Path(raw["data_dir"]).expanduser(),
        categories=_nfc_set(raw.get("categories", [])),
    )
    for key in ("hub_dir", "generated_marker", "hub_min_articles",
                "topic_split_threshold", "batch_size", "legacy_labels_name",
                "label_language", "category_localization"):
        if key in raw:
            kwargs[key] = raw[key]
    if "skip_dirs" in raw:
        kwargs["skip_dirs"] = _nfc_set(raw["skip_dirs"])
    return Config(**kwargs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_config.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Create the config example (the worked Zhihu contract, spec §4/§6)**

`knowledge-library/config.example.yaml`:

```yaml
# knowledge-library config — copy to config.yaml and fill in.
# Paths support ~ expansion.

# REQUIRED -----------------------------------------------------------------
corpus_path: ~/Obsidian/知乎收藏        # the inbox / source vault (was schema.VAULT)
library_path: ~/Obsidian/知乎收藏_v2     # the materialized output vault
data_dir: ./data                        # TSV state (labels, topics, manifest, runs)

# The primary_category canon — ENGLISH-CANONICAL (spec §4b). Locked after the
# pilot. The labeling agent reads Chinese article bodies and emits these names.
categories:
  - Technology & Internet
  - Programming & Software Engineering
  - AI & Machine Learning
  - Science & Engineering
  - Economics & Business
  - Society, Politics & Public Affairs
  - Language Learning
  - Education & Learning
  - Productivity & Tools
  - Literature
  - History & Humanities
  - Film, Anime & Pop Culture
  - Psychology, Relationships & Self-growth
  - Lifestyle
  - Art & Design

# LANGUAGE (spec §4b) ------------------------------------------------------
label_language: en                       # canon language for the controlled vocab
# Display names per language, applied only by `materialize --lang zh`.
# Categories map here; topics carry their display name in the registry's
# name_zh column. Article bodies and summaries are never translated.
category_localization:
  Technology & Internet: {zh: 技术与互联网}
  Programming & Software Engineering: {zh: 编程与软件工程}
  AI & Machine Learning: {zh: AI与机器学习}
  Science & Engineering: {zh: 科学与工程知识}
  Economics & Business: {zh: 经济与商业}
  Society, Politics & Public Affairs: {zh: 社会政治与公共议题}
  Language Learning: {zh: 语言学习}
  Education & Learning: {zh: 教育与学习}
  Productivity & Tools: {zh: 效率与工具}
  Literature: {zh: 文学}
  History & Humanities: {zh: 历史人文}
  Film, Anime & Pop Culture: {zh: 影视动漫与流行文化}
  Psychology, Relationships & Self-growth: {zh: 心理关系与自我成长}
  Lifestyle: {zh: 生活方式}
  Art & Design: {zh: 艺术与设计}

# OPTIONAL (defaults shown) ------------------------------------------------
hub_dir: _topics                         # topic hub-note folder in the vault
skip_dirs: [_images, 分类视图, 话题, _topics]
hub_min_articles: 3                      # min articles before a topic gets a hub
topic_split_threshold: 40                # topic size that flags a split candidate
batch_size: 30                           # articles per labeling batch
generated_marker: "generated: knowledge-library"
```

- [ ] **Step 6: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/
git commit -m "feat(librarian): config dataclass + loader + example config"
```

---

### Task 3: Port the zero-coupling modules (tsv, cooccur, reconcile, refile, frontmatter, batches)

These six modules contain **no `schema.` references**. The only change is rewriting `from mybooks import …` to `from librarian import …`. They are batched because each is a pure rename with no logic change; the batch is verified by running all six test files together.

**Files:**
- Create: `librarian/{tsv,cooccur,reconcile,refile,frontmatter,batches}.py`
- Create: `librarian/tests/test_{tsv,cooccur,reconcile,refile,frontmatter,batches}.py`

- [ ] **Step 1: Port the six modules**

For each module `M` in `tsv, cooccur, reconcile, refile, frontmatter, batches`:
copy `~/workspace/playground/mybooks/mybooks/M.py` → `knowledge-library/librarian/M.py`, then in the copy replace any `from mybooks import …` line with `from librarian import …`.

Known internal imports to rewrite:
- `cooccur.py`: `from mybooks import tsv` → `from librarian import tsv`
- `batches.py`: if it imports `tsv`, rewrite the same way; otherwise no change.
- `tsv.py`, `reconcile.py`, `refile.py`, `frontmatter.py`: no `mybooks` imports — copy verbatim.

After copying, grep to confirm none slipped through:

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -rn "mybooks" librarian/tsv.py librarian/cooccur.py librarian/reconcile.py \
  librarian/refile.py librarian/frontmatter.py librarian/batches.py
```
Expected: no output.

- [ ] **Step 2: Port the six test files**

For each `test_M.py` in the list, copy `~/workspace/playground/mybooks/tests/test_M.py` → `knowledge-library/librarian/tests/test_M.py`, then:
- Rewrite import lines: `from mybooks import …` → `from librarian import …`.
- `test_reconcile.py` imports `schema` and reads `schema.LABEL_COLUMNS`: change `from mybooks import reconcile, schema` → `from librarian import reconcile, contract`, and replace every `schema.LABEL_COLUMNS` → `contract.LABEL_COLUMNS`.
- The other five test files import only their module (no `schema`): import-line rewrite only.

Grep to confirm:

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -rn "mybooks\|schema\." librarian/tests/test_tsv.py librarian/tests/test_cooccur.py \
  librarian/tests/test_reconcile.py librarian/tests/test_refile.py \
  librarian/tests/test_frontmatter.py librarian/tests/test_batches.py
```
Expected: no output.

- [ ] **Step 3: Run the six test files**

Run:
```bash
cd ~/Workspace/MyLibrary/knowledge-library && python -m pytest \
  librarian/tests/test_tsv.py librarian/tests/test_cooccur.py \
  librarian/tests/test_reconcile.py librarian/tests/test_refile.py \
  librarian/tests/test_frontmatter.py librarian/tests/test_batches.py -v
```
Expected: all PASS. If any import error mentions `mybooks` or `schema`, fix the missed rename and re-run.

- [ ] **Step 4: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian
git commit -m "feat(librarian): port zero-coupling modules (tsv, cooccur, reconcile, refile, frontmatter, batches)"
```

---

### Task 4: Port the contract-swap modules (store, registry, proposals, validate)

These modules reference only the *fixed contract* constants (`*_COLUMNS`, `CONFIDENCE`, `BOOL`, `TOPIC_STATUS`). The de-hardcoding is a pure `schema.` → `contract.` swap; no `cfg` threading, no signature changes. Done one module at a time (test-first per module).

**Files:**
- Create: `librarian/{store,registry,proposals,validate}.py`
- Create: `librarian/tests/test_{store,registry,validate}.py`
  (NOTE: `test_proposals.py` is deferred to Task 9 because it monkeypatches `update` globals — see that task.)

#### 4a — store.py

- [ ] **Step 1: Port `test_store.py`**

Copy `tests/test_store.py` → `librarian/tests/test_store.py`. Edit:
- `from mybooks import store, schema` → `from librarian import store, contract`
- every `schema.LABEL_COLUMNS` → `contract.LABEL_COLUMNS`

- [ ] **Step 2: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.store'`.

- [ ] **Step 3: Port `store.py`**

Copy `mybooks/store.py` → `librarian/store.py`. Edit line 1:
`from mybooks import tsv, schema` → `from librarian import tsv, contract`
Replace both `schema.LABEL_COLUMNS` (lines 7, 12) → `contract.LABEL_COLUMNS`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_store.py -v`
Expected: PASS.

#### 4b — registry.py

- [ ] **Step 5: Port `test_registry.py`**

Copy `tests/test_registry.py` → `librarian/tests/test_registry.py`. Edit:
- `from mybooks import registry, tsv, schema` → `from librarian import registry, tsv, contract`
- `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS`; `schema.TOPIC_STATUS` → `contract.TOPIC_STATUS`
- **name_zh:** `TOPIC_COLUMNS` is now 8 wide. Append a trailing `""` (empty `name_zh`) to every topic-row literal — e.g. `["T0001", "文学评论", "", "", "active", "", ""]` → `["T0001", "文学评论", "", "", "active", "", "", ""]`. (Registry reads rows positionally only up to `r[6]`, so the values are unchanged in meaning; the extra field keeps rows aligned with the 8-column header.)

- [ ] **Step 6: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_registry.py -v`
Expected: FAIL — no module `librarian.registry`.

- [ ] **Step 7: Port `registry.py`**

Copy `mybooks/registry.py` → `librarian/registry.py`. Edit:
- line 1 `from mybooks import tsv, schema` → `from librarian import tsv, contract`
- line 10 `schema.TOPIC_STATUS` → `contract.TOPIC_STATUS`
- line 54 `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS`

- [ ] **Step 8: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_registry.py -v`
Expected: PASS.

#### 4c — proposals.py (module only; its test is in Task 9)

- [ ] **Step 9: Port `proposals.py`**

Copy `mybooks/proposals.py` → `librarian/proposals.py`. Edit:
- line 8 `from mybooks import tsv, schema` → `from librarian import tsv, contract`
- line 10 `schema.LABEL_COLUMNS.index("proposed_topics")` → `contract.LABEL_COLUMNS.index("proposed_topics")`
- line 11 `schema.LABEL_COLUMNS.index("title")` → `contract.LABEL_COLUMNS.index("title")`
- line 52 `len(schema.TOPIC_COLUMNS)` → `len(contract.TOPIC_COLUMNS)`

(No standalone test run here — `proposals.pending`/`accept` are exercised by `test_proposals.py` in Task 9 after `update.py` is ported.)

#### 4d — validate.py

- [ ] **Step 10: Port `test_validate.py`**

Copy `tests/test_validate.py` → `librarian/tests/test_validate.py`. Edit:
- `from mybooks import validate, registry, tsv, schema` → `from librarian import validate, registry, tsv, contract`
- `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS` (used in `reg()` and `test_alias_normalized`)
- **name_zh:** append a trailing `""` to every topic-row literal so it matches the 8-column `TOPIC_COLUMNS`. This includes `REG_ROWS` (both rows) and the inline row in `test_alias_normalized` (`["T0001", "文学评论", "lit-crit", "", "active", "", ""]` → `[..., "", ""]`). The label-row builder `row()` is unaffected (it uses `LABEL_COLUMNS`, unchanged).

- [ ] **Step 11: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_validate.py -v`
Expected: FAIL — no module `librarian.validate`.

- [ ] **Step 12: Port `validate.py`**

Copy `mybooks/validate.py` → `librarian/validate.py`. Edit:
- line 1 `from mybooks import tsv, schema` → `from librarian import tsv, contract`
- lines 3–8 module-level index lookups: `schema.LABEL_COLUMNS.index(...)` → `contract.LABEL_COLUMNS.index(...)` (6 occurrences: PATH_I, PRIMARY_I, TOPICS_I, CONF_I, REVIEW_I, PROPOSED_I)
- line 22 `len(schema.LABEL_COLUMNS)` → `len(contract.LABEL_COLUMNS)`
- line 23 `len(schema.LABEL_COLUMNS)` → `len(contract.LABEL_COLUMNS)`
- line 51 `schema.CONFIDENCE` → `contract.CONFIDENCE`
- line 53 `schema.BOOL` → `contract.BOOL`
- line 57 `len(schema.LABEL_COLUMNS)` → `len(contract.LABEL_COLUMNS)`

(`validate.check`'s `categories` argument is already a parameter — no change. `log_progress` is unchanged.)

- [ ] **Step 13: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_validate.py -v`
Expected: PASS.

- [ ] **Step 14: Grep + commit**

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -rn "mybooks\|schema\." librarian/store.py librarian/registry.py \
  librarian/proposals.py librarian/validate.py
```
Expected: no output. Then:

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian
git commit -m "feat(librarian): port contract-swap modules (store, registry, proposals, validate)"
```

---

### Task 5: Port `manifest.py` (cfg threading — skip_dirs)

`manifest.build` reads `schema.SKIP_DIRS`; `manifest.diff` reads `schema.MANIFEST_COLUMNS`. Add a `cfg` parameter to `build`; `diff` uses the fixed contract.

**Files:**
- Create: `librarian/manifest.py`
- Create: `librarian/tests/test_manifest.py`

- [ ] **Step 1: Port `test_manifest.py` with the cfg fixture**

Copy `tests/test_manifest.py` → `librarian/tests/test_manifest.py`. Edit:
- import line: `from mybooks import manifest` → `from librarian import manifest`
- Every call `manifest.build(<vault>)` becomes `manifest.build(<vault>, cfg)`, and the test functions that call it gain the `cfg` fixture parameter (the conftest `cfg` fixture; only `cfg.skip_dirs` is read, so the vault path mismatch with `cfg.corpus_path` is irrelevant).

Example transform — if the source has:
```python
def test_build_lists_articles(tmp_path):
    v = make_vault(tmp_path)
    rows = manifest.build(v)
```
it becomes:
```python
def test_build_lists_articles(tmp_path, cfg):
    v = make_vault(tmp_path)
    rows = manifest.build(v, cfg)
```
Apply this to every test function in the file that calls `manifest.build`. `manifest.diff` and `manifest.read_url` calls are unchanged.

- [ ] **Step 2: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_manifest.py -v`
Expected: FAIL — no module `librarian.manifest`.

- [ ] **Step 3: Port `manifest.py`**

Copy `mybooks/manifest.py` → `librarian/manifest.py`. Edit:
- line 4 `from mybooks import schema` → `from librarian import contract`
- line 24 signature `def build(vault):` → `def build(vault, cfg):`
- line 27 `if d.name in schema.SKIP_DIRS:` → `if d.name in cfg.skip_dirs:`
- line 42 `schema.MANIFEST_COLUMNS.index("relative_path")` → `contract.MANIFEST_COLUMNS.index("relative_path")`
- line 43 `schema.MANIFEST_COLUMNS.index("content_hash")` → `contract.MANIFEST_COLUMNS.index("content_hash")`

(`read_url` and the title/url regexes are unchanged — they are part of the parsing contract, not config.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_manifest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian
git commit -m "feat(librarian): port manifest.py with cfg-driven skip_dirs"
```

---

### Task 6: Port `audit.py` (cfg threading — thresholds)

`audit.report` reads `schema.TOPIC_SPLIT_THRESHOLD` and `schema.HUB_MIN_ARTICLES`. Add a `cfg` parameter.

**Files:**
- Create: `librarian/audit.py`
- Create: `librarian/tests/test_audit.py`

- [ ] **Step 1: Port `test_audit.py`**

Copy `tests/test_audit.py` → `librarian/tests/test_audit.py`. Edit:
- import line: `from mybooks import audit, tsv` → `from librarian import audit, tsv`
- Every call `audit.report(<rows>)` → `audit.report(<rows>, cfg)`, adding the `cfg` fixture parameter to each test function that calls it.

Note: the conftest `cfg` fixture has `hub_min_articles=3`, `topic_split_threshold=40` (defaults), matching the old `schema` values — so existing assertions about split/merge candidates remain valid.

- [ ] **Step 2: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_audit.py -v`
Expected: FAIL — no module `librarian.audit`.

- [ ] **Step 3: Port `audit.py`**

Copy `mybooks/audit.py` → `librarian/audit.py`. Edit:
- line 2 `from mybooks import tsv, schema` → `from librarian import tsv`
- line 5 signature `def report(label_rows):` → `def report(label_rows, cfg):`
- line 13 `schema.TOPIC_SPLIT_THRESHOLD` → `cfg.topic_split_threshold`
- line 15 `schema.HUB_MIN_ARTICLES` → `cfg.hub_min_articles`

- [ ] **Step 4: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_audit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian
git commit -m "feat(librarian): port audit.py with cfg-driven thresholds"
```

---

### Task 7: Port `hubgen.py` and `verify.py` (cfg threading — hub_dir, marker, thresholds)

#### 7a — hubgen.py

`hubgen.plan` and `hubgen.apply` read `HUB_MIN_ARTICLES`, `GENERATED_MARKER`, `HUB_DIR`. Replace the `min_articles` default-param form with an explicit `cfg` argument.

**Files:**
- Create: `librarian/hubgen.py`
- Create: `librarian/tests/test_hubgen.py`

- [ ] **Step 1: Port `test_hubgen.py`**

Copy `tests/test_hubgen.py` → `librarian/tests/test_hubgen.py`. Edit:
- import line: `from mybooks import hubgen, registry, tsv, schema` → `from librarian import hubgen, registry, tsv, contract`
- `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS`
- **name_zh:** append a trailing `""` to every topic-row literal so each matches the 8-column `TOPIC_COLUMNS`.
- `schema.HUB_DIR` → `cfg.hub_dir`; `schema.GENERATED_MARKER` → `cfg.generated_marker`
- `hubgen.plan(rows, reg, vault)` → `hubgen.plan(rows, reg, vault, cfg)`; `hubgen.apply(plans, vault)` → `hubgen.apply(plans, vault, cfg)`
- Add the `cfg` fixture parameter to each test function that references `cfg.hub_dir`, `cfg.generated_marker`, or calls `plan`/`apply`.
- If any test passes a custom `min_articles=` keyword to `plan`, replace it by building a Config with that `hub_min_articles` (e.g. `dataclasses.replace(cfg, hub_min_articles=2)`) and passing `cfg`. (Check the source file for such calls.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_hubgen.py -v`
Expected: FAIL — no module `librarian.hubgen`.

- [ ] **Step 3: Port `hubgen.py`**

Copy `mybooks/hubgen.py` → `librarian/hubgen.py`. Edit:
- line 3 `from mybooks import tsv, schema, cooccur` → `from librarian import tsv, cooccur`
- line 6 signature `def plan(label_rows, reg, vault, min_articles=schema.HUB_MIN_ARTICLES):` → `def plan(label_rows, reg, vault, cfg):`
- line 19 `if len(arts) < min_articles or topic not in reg.active_names():` → `if len(arts) < cfg.hub_min_articles or topic not in reg.active_names():`
- line 23 `schema.GENERATED_MARKER` → `cfg.generated_marker`
- line 43 `vault / schema.HUB_DIR / f"{topic}.md"` → `vault / cfg.hub_dir / f"{topic}.md"`
- line 47 signature `def apply(plans, vault):` → `def apply(plans, vault, cfg):`
- line 48 `(vault / schema.HUB_DIR).mkdir(...)` → `(vault / cfg.hub_dir).mkdir(...)`
- line 51 `schema.GENERATED_MARKER not in path.read_text(...)` → `cfg.generated_marker not in path.read_text(...)`

(The `k=8` related-topics cap and the Chinese section headers stay as-is — out of scope for this plan.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_hubgen.py -v`
Expected: PASS.

#### 7b — verify.py

`verify.run` reads `LABEL_COLUMNS`, `CONFIDENCE`, `BOOL` (contract) and `SKIP_DIRS`, `HUB_DIR`, `HUB_MIN_ARTICLES`, `GENERATED_MARKER` (config). Add `cfg` **before** the `manifest_rows=None` keyword so existing `manifest_rows=` callers keep working.

**Files:**
- Create: `librarian/verify.py`
- Create: `librarian/tests/test_verify.py`

- [ ] **Step 5: Port `test_verify.py`**

Copy `tests/test_verify.py` → `librarian/tests/test_verify.py`. Edit:
- import line: `from mybooks import verify, registry, tsv, schema` → `from librarian import verify, registry, tsv, contract`
- in `reg()` and `hub_reg()`: `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS`, and append a trailing `""` to the topic-row literal (`["T0001", "文学评论", "", "", "active", "", ""]` → `[..., "", ""]`) to match the 8-column `TOPIC_COLUMNS`
- in `write_hub()`: `schema.HUB_DIR` → `cfg.hub_dir` (and add `cfg` parameter to `write_hub` and thread it from callers) — OR, simpler, since `write_hub` is a test helper, change it to take `hub_dir` as an argument and pass `cfg.hub_dir`. Recommended: `def write_hub(vault, stem, body, cfg):` and `d = vault / cfg.hub_dir`.
- every `schema.GENERATED_MARKER` literal in hub-note bodies → `cfg.generated_marker`
- every `verify.run(rows, reg, v, {...})` → `verify.run(rows, reg, v, {...}, cfg)`; calls using `manifest_rows=` keep the keyword: `verify.run(..., cfg, manifest_rows=manifest)`
- add the `cfg` fixture parameter to every test function (all of them call `verify.run` and/or `write_hub`).

- [ ] **Step 6: Run to verify it fails**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_verify.py -v`
Expected: FAIL — no module `librarian.verify`.

- [ ] **Step 7: Port `verify.py`**

Copy `mybooks/verify.py` → `librarian/verify.py`. Edit:
- line 4 `from mybooks import tsv, schema` → `from librarian import tsv, contract`
- line 11 signature `def run(label_rows, reg, vault, categories, manifest_rows=None):` → `def run(label_rows, reg, vault, categories, cfg, manifest_rows=None):`
- line 16 `len(schema.LABEL_COLUMNS)` → `len(contract.LABEL_COLUMNS)`
- line 31 `schema.CONFIDENCE` → `contract.CONFIDENCE`
- line 33 `schema.BOOL` → `contract.BOOL`
- line 39 `if d.name in schema.SKIP_DIRS:` → `if d.name in cfg.skip_dirs:`
- line 57 `hub_dir = vault / schema.HUB_DIR` → `hub_dir = vault / cfg.hub_dir`
- line 69 `c >= schema.HUB_MIN_ARTICLES` → `c >= cfg.hub_min_articles`
- line 72 `if schema.GENERATED_MARKER not in text:` → `if cfg.generated_marker not in text:`

(The hub-link regex on line 81 is parsing contract — unchanged.)

- [ ] **Step 8: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_verify.py -v`
Expected: PASS.

- [ ] **Step 9: Grep + commit**

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -rn "mybooks\|schema\." librarian/hubgen.py librarian/verify.py
```
Expected: no output. Then:

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian
git commit -m "feat(librarian): port hubgen.py + verify.py with cfg threading"
```

---

### Task 8: Port `update.py` (the orchestrator — module-level cfg)

`update.py` carries 19 `schema.X` references plus module-level path globals `LABELS/TOPICS/MANIFEST` derived from `schema.DATA`, plus a magic batch size `30`. De-hardcode it **in place** (no structural split): introduce a module-level `cfg`, derive the path globals from it on demand, and thread `cfg` into the library calls that now require it (`manifest.build`, `hubgen.plan/apply`, `verify.run`, `audit.report`).

**Files:**
- Create: `librarian/update.py`

- [ ] **Step 1: Port `update.py` — header, imports, module-level cfg**

Copy `mybooks/update.py` → `librarian/update.py`. Then apply all edits below.

Replace the module docstring command examples `python3 -m mybooks.update …` → `python3 -m librarian.update …`.

Replace the import block (lines 13–18):
```python
from mybooks import (schema, tsv, manifest, registry, batches, validate,
                     store, hubgen, frontmatter, refile, verify, audit, proposals)

LABELS = schema.DATA / "article_labels.tsv"
TOPICS = schema.DATA / "topics.tsv"
MANIFEST = schema.DATA / "manifest.tsv"
```
with:
```python
from librarian import (config, contract, tsv, manifest, registry, batches,
                       validate, store, hubgen, frontmatter, refile, verify,
                       audit, proposals)

# The active config. Set by configure() (or __main__); tests monkeypatch it.
cfg = None


def configure(c):
    """Install the active Config for this process."""
    global cfg
    cfg = c
```

- [ ] **Step 2: Replace every `schema.X` reference in `update.py`**

Apply these edits (function by function). All `LABELS`/`TOPICS`/`MANIFEST` global reads become `cfg.labels_path`/`cfg.topics_path`/`cfg.manifest_path`.

- `_manifest_rows()` (line 21–23):
  `tsv.read_rows(MANIFEST, schema.MANIFEST_COLUMNS)` → `tsv.read_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS)`
- `_new_inbox_rows(library)` (lines 45–50):
  - `store.load(LABELS)` → `store.load(cfg.labels_path)`
  - `for r in manifest.build(schema.VAULT):` → `for r in manifest.build(cfg.corpus_path, cfg):`
  - `manifest.read_url(schema.VAULT / r[0])` → `manifest.read_url(cfg.corpus_path / r[0])`
- `cmd_diff(library=None)` (lines 55–61):
  - `if library is not None and library != schema.VAULT:` → `if library is not None and library != cfg.corpus_path:`
  - `manifest.diff(_manifest_rows(), manifest.build(schema.VAULT))` → `manifest.diff(_manifest_rows(), manifest.build(cfg.corpus_path, cfg))`
- `cmd_queue(library=None)` (lines 69–80):
  - `if library is not None and library != schema.VAULT:` → `… != cfg.corpus_path:`
  - `current = manifest.build(schema.VAULT)` → `current = manifest.build(cfg.corpus_path, cfg)`
  - `legacy = load_legacy(schema.LEGACY_LABELS)` → `legacy = load_legacy(cfg.legacy_labels)`
  - `batches.make(todo, legacy, schema.DATA / "batches", 30, schema.VAULT)` → `batches.make(todo, legacy, cfg.batches_dir, cfg.batch_size, cfg.corpus_path)`
- `cmd_ingest(out_tsv, library=None)` (lines 85–109):
  - `reg = registry.load(TOPICS)` → `reg = registry.load(cfg.topics_path)`
  - `tsv.read_rows(Path(out_tsv), schema.LABEL_COLUMNS)` → `tsv.read_rows(Path(out_tsv), contract.LABEL_COLUMNS)`
  - `manifest.build(schema.VAULT)` (line 87) → `manifest.build(cfg.corpus_path, cfg)`
  - `validate.check(rows, expected, reg, schema.CATEGORIES_V1)` → `validate.check(rows, expected, reg, cfg.categories)`
  - `store.merge(LABELS, rows)` → `store.merge(cfg.labels_path, rows)`
  - `validate.log_progress(schema.DATA / "progress.tsv", …)` → `validate.log_progress(cfg.progress_path, …)`
  - `if library is not None and library != schema.VAULT:` → `… != cfg.corpus_path:`
  - `manifest.diff(_manifest_rows(), manifest.build(schema.VAULT))` (line 106) → `manifest.diff(_manifest_rows(), manifest.build(cfg.corpus_path, cfg))`
  - `store.delete(LABELS, deleted)` → `store.delete(cfg.labels_path, deleted)`
  - `tsv.write_rows(MANIFEST, schema.MANIFEST_COLUMNS, manifest.build(schema.VAULT))` → `tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))`
- `cmd_materialize(write=False, out=None)` (lines 114–139):
  - `rows = store.load(LABELS)` → `store.load(cfg.labels_path)`
  - `reg = registry.load(TOPICS)` → `registry.load(cfg.topics_path)`
  - `if out is not None and out != schema.VAULT:` → `… != cfg.corpus_path:`
  - `moves = refile.plan(rows, schema.VAULT)` → `refile.plan(rows, cfg.corpus_path)`
  - `plans = hubgen.plan(rows, reg, schema.VAULT)` → `hubgen.plan(rows, reg, cfg.corpus_path, cfg)`
  - `move_log = refile.apply(moves, schema.VAULT)` → `refile.apply(moves, cfg.corpus_path)`
  - `log_path = schema.DATA / "migration_log.tsv"` → `log_path = cfg.migration_log_path`
  - `store.delete(LABELS, [old for old, _ in move_log])` → `store.delete(cfg.labels_path, …)`
  - `skipped = hubgen.apply(plans, schema.VAULT)` → `hubgen.apply(plans, cfg.corpus_path, cfg)`
  - `frontmatter.apply(schema.VAULT / r[0], r)` → `frontmatter.apply(cfg.corpus_path / r[0], r)`
  - `store.merge(LABELS, rows)` → `store.merge(cfg.labels_path, rows)`
  - `tsv.write_rows(MANIFEST, schema.MANIFEST_COLUMNS, manifest.build(schema.VAULT))` → `tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))`
- `_materialize_to_library(rows, reg, library, write)` (lines 158–199):
  - `plans = hubgen.plan(rows, reg, library)` (line 169) → `hubgen.plan(rows, reg, library, cfg)`
  - `src = schema.VAULT / r[0]` → `src = cfg.corpus_path / r[0]`
  - `plans = hubgen.plan(rows, reg, library)` (line 190) → `hubgen.plan(rows, reg, library, cfg)`
  - `skipped = hubgen.apply(plans, library)` → `hubgen.apply(plans, library, cfg)`
  - `frontmatter.apply(library / r[0], r)` — unchanged (no schema)
  - `store.delete(LABELS, src_paths)` → `store.delete(cfg.labels_path, src_paths)`
  - `store.merge(LABELS, rows)` → `store.merge(cfg.labels_path, rows)`
  - `tsv.write_rows(MANIFEST, schema.MANIFEST_COLUMNS, manifest.build(library))` → `tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(library, cfg))`
  - (`_free_dest` lines 143–155: no schema refs — unchanged)
- `cmd_proposals(accept=False)` (lines 202–214):
  - `rows = store.load(LABELS)` → `store.load(cfg.labels_path)`
  - `reg = registry.load(TOPICS)` → `registry.load(cfg.topics_path)`
  - `tsv.write_rows(TOPICS, schema.TOPIC_COLUMNS, new_rows)` → `tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS, new_rows)`
  - `print(f"accepted … into {TOPICS}; …")` → `… into {cfg.topics_path}; …`
- `verify_problems(library=None)` (lines 217–226):
  - `vault = library if library is not None else schema.VAULT` → `vault = library if library is not None else cfg.corpus_path`
  - `rows = store.load(LABELS)` → `store.load(cfg.labels_path)`
  - `reg = registry.load(TOPICS)` → `registry.load(cfg.topics_path)`
  - `if MANIFEST.exists():` → `if cfg.manifest_path.exists():`
  - `return verify.run(rows, reg, vault, schema.CATEGORIES_V1, manifest_rows=_manifest_rows())` → `return verify.run(rows, reg, vault, cfg.categories, cfg, manifest_rows=_manifest_rows())`
  - `return verify.run(rows, reg, vault, schema.CATEGORIES_V1)` → `return verify.run(rows, reg, vault, cfg.categories, cfg)`
- `cmd_verify(library=None)` (lines 229–233):
  - `print(audit.report(store.load(LABELS))["review_open"], …)` → `print(audit.report(store.load(cfg.labels_path), cfg)["review_open"], …)`

- [ ] **Step 3: Update the `__main__` block to load and install a config**

Replace the `if __name__ == "__main__":` block (lines 245–259). After computing `out`/`lib`, install a config from an env var or a default path before dispatching:
```python
if __name__ == "__main__":
    import os
    configure(config.load(os.environ.get(
        "KNOWLEDGE_LIBRARY_CONFIG", "config.yaml")))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "diff"
    if cmd == "ingest" and len(sys.argv) < 3:
        sys.exit("usage: python -m librarian.update ingest <out.tsv> [--out <library>]")
    out = _opt("--out")
    lib = Path(out).expanduser() if out else None
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib)}
    if cmd not in handlers:
        sys.exit(f"unknown command {cmd!r}; choose from {', '.join(handlers)}")
    handlers[cmd]()
```

- [ ] **Step 4: Grep for stragglers**

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -n "schema\.\|mybooks\|\bLABELS\b\|\bTOPICS\b\|\bMANIFEST\b" librarian/update.py
```
Expected: no `schema.` / `mybooks` matches. The only `LABELS`/`TOPICS`/`MANIFEST` allowed are inside the `cfg.*_path` property names — i.e. there should be **no bare** `LABELS`/`TOPICS`/`MANIFEST` identifiers left. Fix any that remain.

- [ ] **Step 5: Smoke-import the module**

Run: `cd knowledge-library && python -c "from librarian import update; print('ok')"`
Expected: prints `ok` (no `NameError`/`ImportError`).

- [ ] **Step 6: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/librarian/update.py
git commit -m "feat(librarian): port update.py orchestrator with module-level cfg"
```

---

### Task 9: Port the update-coupled tests + full-suite green

The remaining test files monkeypatch `update`'s globals / `schema.VAULT` / `schema.DATA`. They are ported last because they depend on Task 8. Each replaces the old `_patch` idiom (monkeypatch `schema.VAULT`, `schema.DATA`, `update.LABELS/TOPICS/MANIFEST`) with **a Config injected via `monkeypatch.setattr(update, "cfg", c)`**, and swaps `schema.*_COLUMNS` → `contract.*_COLUMNS`.

**Files:**
- Create: `librarian/tests/test_update_materialize.py`
- Create: `librarian/tests/test_update_two_vault.py`
- ~~Create: `librarian/tests/test_update_v2.py`~~ — **NOT PORTED (scope correction, 2026-06-13).** The source `tests/test_update_v2.py` is an integration test for `scripts/update_v2_topics.py`, a one-off migration script in mybooks' `scripts/` dir — NOT one of the 16 `mybooks/` package modules this plan ports. It monkeypatches that script's globals (`mod.LABELS/TOPICS/MIGRATION`), not `update`'s, and the script was never in scope for the `librarian/` package. The behaviour it covered (refile on `primary_category` change, two-phase collision-safe rename, migration-log rewrite) is already exercised by the ported `test_update_materialize.py` refile tests against the de-hardcoded `cmd_materialize`. (If the v2-updater script is ever ported in a later plan, port this test alongside it.)
- Create: `librarian/tests/test_update_legacy.py`
- Create: `librarian/tests/test_update_smoke.py`
- Create: `librarian/tests/test_diff_dedup.py`
- Create: `librarian/tests/test_proposals.py`

- [ ] **Step 1: Port `test_update_materialize.py` (the reference transform)**

Copy `tests/test_update_materialize.py` → `librarian/tests/test_update_materialize.py`. Apply:
- import line: `from mybooks import update, schema, tsv, manifest` → `from librarian import update, config, contract, tsv, manifest`
- Replace the `_patch` helper with a Config-injecting version:
```python
def _patch(monkeypatch, vault, data, categories=("文学", "历史人文", "AI与机器学习")):
    c = config.Config(corpus_path=vault, library_path=vault, data_dir=data,
                      categories=set(categories))
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS, [])
    monkeypatch.setattr(update, "cfg", c)
    return c.labels_path, c.topics_path, c.manifest_path
```
- Replace every `schema.LABEL_COLUMNS` → `contract.LABEL_COLUMNS`, `schema.MANIFEST_COLUMNS` → `contract.MANIFEST_COLUMNS`, `schema.TOPIC_COLUMNS` → `contract.TOPIC_COLUMNS` throughout (in `_lrow`, the body `tsv.write_rows(...)` calls, and the assertions).
- Replace every `manifest.build(vault)` / `manifest.build(inbox)` / `manifest.build(lib)` → add `, c` (the Config returned by `_patch`). Since the helpers currently call `manifest.build(...)` without a config, capture the Config: change call sites from `_patch(monkeypatch, vault, data)` to also keep the returned Config if needed, OR fetch it via `update.cfg`. **Simplest:** after `_patch(...)`, the active config is `update.cfg`; use `manifest.build(vault, update.cfg)`.

Concretely, the body line `tsv.write_rows(man, schema.MANIFEST_COLUMNS, manifest.build(vault))` becomes `tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(vault, update.cfg))`, and the assertion `{r[0] for r in manifest.build(vault)}` becomes `{r[0] for r in manifest.build(vault, update.cfg)}`. Apply the same to the `inbox`/`lib` variants.

- [ ] **Step 2: Run to verify it passes**

Run: `cd knowledge-library && python -m pytest librarian/tests/test_update_materialize.py -v`
Expected: PASS (6 tests).

- [ ] **Step 3: Port the remaining four update-coupled test files the same way**

For `test_update_two_vault.py`, `test_update_v2.py`, `test_diff_dedup.py`, `test_proposals.py`: copy each from `tests/`, then apply the identical transform:
1. imports: drop `schema`, add `config, contract`; `from mybooks import …` → `from librarian import …`.
2. Replace the `_patch`/setup helper that monkeypatches `schema.VAULT`/`schema.DATA`/`update.LABELS`/`update.TOPICS`/`update.MANIFEST` with the Config-injection form (`monkeypatch.setattr(update, "cfg", c)`), as in Step 1.
3. `schema.*_COLUMNS` → `contract.*_COLUMNS` everywhere.
4. `manifest.build(<v>)` → `manifest.build(<v>, update.cfg)`.
5. `verify.run(...)` calls (if any) → add `update.cfg` before any `manifest_rows=`.
6. `audit.report(<rows>)` (if any) → `audit.report(<rows>, update.cfg)`.

For `test_proposals.py` specifically: it imports `proposals, registry, schema, tsv, update`. The proposals module itself is already ported (Task 4c). Apply the same `_patch` transform for the `update` globals it monkeypatches, and `schema.LABEL_COLUMNS`/`schema.TOPIC_COLUMNS` → `contract.*`. If it writes any topic-row literals (seeding the registry), append a trailing `""` (name_zh) so they match the 8-column `TOPIC_COLUMNS`. Note `proposals.accept` builds new rows via `[""] * len(contract.TOPIC_COLUMNS)`, so it auto-adapts — assertions that check a generated row's length should expect 8, not 7.

Run each as you port it:
```bash
cd knowledge-library && python -m pytest librarian/tests/test_update_two_vault.py -v
cd knowledge-library && python -m pytest librarian/tests/test_update_v2.py -v
cd knowledge-library && python -m pytest librarian/tests/test_diff_dedup.py -v
cd knowledge-library && python -m pytest librarian/tests/test_proposals.py -v
```
Expected: each PASS. Use `grep -n "schema\.\|mybooks" <file>` to catch missed swaps.

- [ ] **Step 4: Port `test_update_legacy.py` and `test_update_smoke.py`**

- `test_update_smoke.py`: a pure import check. Copy and change `from mybooks import update` → `from librarian import update`. If it asserts the module imports cleanly, that suffices.
- `test_update_legacy.py`: copy; change `from mybooks import update` → `from librarian import update`. This exercises `update.load_legacy(path)` directly (a pure function taking an explicit path — no `cfg` needed). If any test calls a `cmd_*` function, inject a Config via `monkeypatch.setattr(update, "cfg", config.Config(...))` as in Step 1. Inspect the file and add the injection only where a `cmd_*` is invoked.

Run:
```bash
cd knowledge-library && python -m pytest librarian/tests/test_update_legacy.py librarian/tests/test_update_smoke.py -v
```
Expected: PASS.

- [ ] **Step 5: Run the FULL suite**

Run: `cd knowledge-library && python -m pytest -v`
Expected: every test passes. The count should be ~all tests from the original 21 files (minus `test_schema.py`, replaced by `test_contract.py` + `test_config.py`). If anything fails, fix the specific port (do not weaken assertions).

- [ ] **Step 6: Final grep — no residual coupling**

```bash
cd ~/Workspace/MyLibrary/knowledge-library
grep -rn "mybooks" librarian/
grep -rn "schema\." librarian/        # contract./cfg. only — no bare schema.
grep -rn "知乎收藏\|/Users/kunwu/Obsidian" librarian/   # no hardcoded vault path
```
Expected: first two empty; the third may match only inside `config.example.yaml` (which lives at `knowledge-library/`, not under `librarian/`), so it too should be empty under `librarian/`.

- [ ] **Step 7: Commit**

```bash
cd ~/Workspace/MyLibrary
git add knowledge-library/
git commit -m "feat(librarian): port update-coupled tests; full suite green, config-driven"
```

---

## Self-Review (run after all tasks)

**1. Spec coverage (this plan's slice — spec §12 'biggest single chunk'):**
- "threading config.py through every module" → Tasks 2, 5, 6, 7, 8 (config-threaded modules) + Tasks 3, 4 (contract swap). ✓
- "porting the tests, parameterized by config" → Tasks 1–9 each port their test alongside the module; the `cfg` fixture (Task 1 conftest) is the parameterization. ✓
- Language foundational schema (spec §4b) → `contract.TOPIC_COLUMNS` gains `name_zh` (Task 1); `config` gains `label_language`, `category_localization`, `localize_category()` (Task 2). Consumers (`materialize --lang`, language-aware `verify`/`hubgen`/`refile`, labeling prompt) correctly deferred to Plans 2–3. ✓
- Out-of-scope items (orchestrate split, adapters, steady-state, run ledger, skill package, scheduling) are correctly deferred to Plans 2–5. ✓

**2. Placeholder scan:** every code step contains literal code or an exact old→new edit list with line numbers; no "add error handling"/"TBD". The two judgement calls (custom `min_articles=` kwargs in `test_hubgen`; `cmd_*` calls in `test_update_legacy`) are flagged as "inspect the source file and apply X" because the exact source line is not reproduced here — when executing, read the file first.

**3. Type/signature consistency across tasks:**
- `manifest.build(vault, cfg)` — defined Task 5, called Task 8 (`update.py`) and Tasks 5/9 tests. ✓
- `hubgen.plan(label_rows, reg, vault, cfg)` and `hubgen.apply(plans, vault, cfg)` — defined Task 7a, called Task 8. ✓
- `verify.run(label_rows, reg, vault, categories, cfg, manifest_rows=None)` — `cfg` before `manifest_rows` so keyword callers (`test_verify`, `update.verify_problems`) stay valid. Defined Task 7b, called Task 8. ✓
- `audit.report(label_rows, cfg)` — defined Task 6, called Task 8 (`cmd_verify`). ✓
- `config.Config(corpus_path, library_path, data_dir, categories, …)` and its derived `*_path` properties — defined Task 2, used by Task 8 and the Task 9 `_patch` helpers. ✓
- `contract.{MANIFEST,TOPIC,LABEL}_COLUMNS`, `contract.{CONFIDENCE,BOOL,TOPIC_STATUS}` — defined Task 1, used everywhere. `TOPIC_COLUMNS` is 8 wide (name_zh appended); every ported topic-row fixture carries a trailing `""` (Tasks 4b, 4d, 7a, 7b, 9). `registry`/`proposals` read rows positionally only to `r[6]`, so appending is behaviour-neutral. ✓
- `config.localize_category(canonical, lang)` + fields `label_language`, `category_localization` — defined Task 2; no Plan 1 consumer (Plan 2 materialize uses them). ✓
- `update.configure(c)` / `update.cfg` — defined Task 8, injected by Task 9 tests. ✓

---

## Execution note

This plan is behaviour-preserving: every ported test asserts the **same** behaviour as the original MyBooks suite, now sourced from `config`/`contract` instead of `schema`. A passing full suite (Task 9 Step 5) is the completion signal. Plan 2 (orchestrate split + adapters) builds directly on this package.
