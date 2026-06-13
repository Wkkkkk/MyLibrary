# Knowledge-Library Steady-State Implementation Plan (Plan 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the deterministic Python for the steady-state recurring workflow (spec §7) — extract `orchestrate/materialize.py`, add `orchestrate/steady_state.py` (the run-ledger writer), add the `label_model` config knob, harden `ingest_wave` against malformed agent JSON, and relocate `status` under `orchestrate/` per the spec §3 layout.

**Architecture:** `cmd_materialize`/`_materialize_to_library`/`_free_dest` move verbatim from `update.py` into `orchestrate/materialize.py` with `cfg` passed as a parameter (the bodies already reference `cfg.`, so relocation is behaviour-preserving); `update.cmd_materialize` becomes a thin delegator. A new `orchestrate/steady_state.py` provides the deterministic glue around the external steps (the zhihu-fetcher + the parallel LLM labeling stay in the schedule wrapper / SKILL): `diff_new` (net-new by url), `finish` (ingest the labeled wave → materialize → verify → append one run-ledger row), and `record_nothing_new` (a zero-cost empty pull) — each returning `(run_row, digest)`. `ingest_wave` is hardened to surface malformed/non-list JSON as structured errors rather than crashing.

**Tech Stack:** Python 3, stdlib only (`json`, `shutil`, `unicodedata`) + existing `librarian` modules. Tests: `pytest`, run from `knowledge-library/`.

**Scope (Plan 5 = "steady-state Python", per user decision):** materialize extraction + `steady_state.py` + `label_model` knob + harden ingest + move `status` to `orchestrate/`. **Non-goals (deferred to the final packaging plan):** `SKILL.md` + `references/` + `templates/` + `schedule/` (wrapper.sh + launchd plist) — the skill assembly that wires the real `claude -p` labeling dispatch and the zhihu-fetcher (spec §3 packaging + §10 scheduling). This plan ships the testable deterministic functions the wrapper/SKILL will call; it does NOT add a recurring CLI that shells out to an LLM.

**Working directory for all commands:** `/Users/kunwu/Workspace/MyLibrary/knowledge-library`
**Run tests with:** `pytest -q` (the `conftest.py` there puts `librarian` on `sys.path`; bare `python`/`python3` is 3.14 without pytest — use the `pytest` command).

---

## File Structure

| File | Responsibility |
|---|---|
| `librarian/orchestrate/materialize.py` *(create)* | `materialize(cfg, write, out, lang)` + `_to_library` + `_free_dest` — moved from `update.py`, cfg-parameterized. |
| `librarian/update.py` *(modify)* | `cmd_materialize` delegates to `orchestrate.materialize`; drop the moved functions + the now-unused `shutil` import. |
| `librarian/orchestrate/steady_state.py` *(create)* | `diff_new` / `finish` / `record_nothing_new` — the §7 deterministic glue + run-ledger writer. |
| `librarian/orchestrate/ingest_wave.py` *(modify)* | harden `ingest` against malformed / non-list / missing-key agent JSON. |
| `librarian/config.py` *(modify)* | add `label_model` knob. |
| `librarian/status.py` → `librarian/orchestrate/status.py` *(move)* | relocate per spec §3 layout; fix importers. |
| `librarian/tests/test_materialize.py` *(create)* | direct test of the extracted `materialize.materialize`. |
| `librarian/tests/test_steady_state.py` *(create)* | diff_new / finish (ok + error) / record_nothing_new. |
| `librarian/tests/test_ingest_wave.py` *(modify)* | malformed-JSON hardening tests. |
| `librarian/tests/test_config.py` *(modify)* | `label_model` default + loader. |
| `librarian/tests/test_status.py` *(modify)* | update the import path after the move. |

---

## Task 1: Extract `orchestrate/materialize.py`

**Files:**
- Create: `librarian/orchestrate/materialize.py`
- Modify: `librarian/update.py`
- Test: `librarian/tests/test_materialize.py`

Context: the materialize logic must be callable with an explicit `cfg` (not `update.py`'s module global) so `steady_state` can drive it. The three functions reference `cfg.` throughout, so moving them with `cfg` as the first parameter is behaviour-preserving. `update.cmd_materialize` delegates, keeping the existing `test_update_materialize`/`test_update_two_vault` suites green as the regression guard.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_materialize.py`:

```python
"""Direct test of the extracted orchestrate.materialize (cfg passed explicitly,
not via update.py's module global)."""
from librarian import config, contract, tsv, manifest, store
from librarian.orchestrate import materialize


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
                      data_dir=tmp_path / "data", categories={"文学", "历史人文"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _lrow(rel, primary):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[12] = rel, "t", primary, "h0"
    return r


def _article(vault, rel, primary):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "t"\nprimary_category: "{primary}"\n---\n\n# t\n',
                 encoding="utf-8")


def test_materialize_refiles_in_place(tmp_path):
    cfg = _cfg(tmp_path)
    _article(cfg.corpus_path, "文学/a.md", "历史人文")
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS, [])
    tsv.write_rows(cfg.labels_path, contract.LABEL_COLUMNS, [_lrow("文学/a.md", "历史人文")])
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))

    materialize.materialize(cfg, write=True)

    assert [r[0] for r in store.load(cfg.labels_path)] == ["历史人文/a.md"]
    assert (cfg.corpus_path / "历史人文" / "a.md").exists()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_materialize.py -q`
Expected: FAIL — `No module named 'librarian.orchestrate.materialize'`.

- [ ] **Step 3: Create `orchestrate/materialize.py`**

Create `librarian/orchestrate/materialize.py` (the bodies are copied verbatim from `update.py`; `cfg` is now the first parameter and the recursive call passes it):

```python
"""Materialize labeled articles into a browsable vault (spec §5 step 8): refile
into <primary_category>/ folders, write topic hub notes, apply managed
frontmatter, and rebuild the manifest. `lang` selects the display language for
folders / hub names / headers (spec §4b). Extracted from update.py so the CLI
and steady_state share one implementation; cfg is passed explicitly."""
import shutil
from pathlib import Path
from librarian import (contract, tsv, manifest, registry, store, hubgen,
                       frontmatter, refile)


def materialize(cfg, write=False, out=None, lang="en"):
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if out is not None and out != cfg.corpus_path:
        return _to_library(cfg, rows, reg, out, write, lang)
    moves = refile.plan(rows, cfg.corpus_path, cfg, lang)
    plans = hubgen.plan(rows, reg, cfg.corpus_path, cfg, lang)
    print(f"would move {len(moves)} files, write {len(plans)} hub notes")
    if not write:
        print("dry run; pass --write")
        return
    move_log = refile.apply(moves, cfg.corpus_path)
    if move_log:
        log_path = cfg.migration_log_path
        tsv.write_rows(log_path, ["old_path", "new_path"], [list(m) for m in move_log])
        # refile.apply mutated each moved row's path in place; drop the stale
        # old-path rows so store.merge below can't leave duplicates behind.
        store.delete(cfg.labels_path, [old for old, _ in move_log])
        print(f"wrote {len(move_log)} moves to {log_path}")
    skipped = hubgen.apply(plans, cfg.corpus_path, cfg)
    stats = {}
    for r in rows:
        res = frontmatter.apply(cfg.corpus_path / r[0], r)
        stats[res] = stats.get(res, 0) + 1
    store.merge(cfg.labels_path, rows)
    # files moved on disk; rebuild the manifest so it matches the new layout.
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS,
                   manifest.build(cfg.corpus_path, cfg))
    print("frontmatter:", stats, "| hub notes skipped (hand-edited):", skipped)


def _free_dest(library, primary, base, url, taken):
    """Pick library-relative path <primary>/<base>, appending _N to dodge a
    title collision with a DIFFERENT article (different url) — never overwriting
    it. A slot already holding this same article (same url) is reused."""
    stem, ext = Path(base).stem, Path(base).suffix
    rel = f"{primary}/{base}"
    n = 2
    while rel in taken or (
        (library / rel).exists() and manifest.read_url(library / rel) != url
    ):
        rel = f"{primary}/{stem}_{n}{ext}"
        n += 1
    return rel


def _to_library(cfg, rows, reg, library, write, lang="en"):
    """Materialize labels into a separate library vault (e.g. 知乎收藏_v2).

    Each labeled article is copied from the inbox (cfg.corpus_path) into
    library/<primary_category>/, frontmatter + hub notes are written there, and
    the inbox original is removed (move semantics). Idempotent: on a re-run the
    inbox source is already gone, so it just refreshes the library in place.
    The labels TSV and manifest become library-relative.

    Single display language per library: `lang` must match the language used on
    the initial materialize — the idempotent re-run path keeps each article at
    its already-localized path, so switching lang on a populated library would
    leave folders disagreeing with their canonical primary_category.
    """
    src_paths = [r[0] for r in rows]
    if not write:
        plans = hubgen.plan(rows, reg, library, cfg, lang)
        print(f"would copy {len(rows)} files into {library}, write {len(plans)} hub notes")
        print("dry run; pass --write")
        return
    taken = set()
    for r in rows:
        src = cfg.corpus_path / r[0]
        if not src.exists() and (library / r[0]).exists():
            dst_rel = r[0]  # idempotent re-run: already at its final library path
        else:
            dst_rel = _free_dest(library, cfg.localize_category(r[3], lang),
                                 r[0].rsplit("/", 1)[-1],
                                 manifest.read_url(src), taken)
        taken.add(dst_rel)
        dst = library / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
            src.unlink()
        else:
            assert dst.exists(), (r[0], dst_rel)
        r[0] = dst_rel
    plans = hubgen.plan(rows, reg, library, cfg, lang)  # plan against the final paths
    skipped = hubgen.apply(plans, library, cfg)
    stats = {}
    for r in rows:
        res = frontmatter.apply(library / r[0], r)
        stats[res] = stats.get(res, 0) + 1
    store.delete(cfg.labels_path, src_paths)   # drop inbox-keyed rows
    store.merge(cfg.labels_path, rows)         # re-add at library paths
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(library, cfg))
    print(f"copied into {library}:", stats, "| hub notes skipped:", skipped)
```

- [ ] **Step 4: Delegate from `update.py` and remove the moved code**

In `librarian/update.py`:

(a) Replace the entire `cmd_materialize` function, the `_free_dest` function, and the `_materialize_to_library` function (three consecutive functions, from `def cmd_materialize(` through the end of `_materialize_to_library`, i.e. everything before `def cmd_proposals(`) with this single delegator:
```python
def cmd_materialize(write=False, out=None, lang="en"):
    from librarian.orchestrate import materialize
    return materialize.materialize(cfg, write=write, out=out, lang=lang)
```

(b) Remove the now-unused `import shutil` line near the top of `update.py` (it was only used by the moved `_materialize_to_library`).

- [ ] **Step 5: Run the targeted + full suite**

Run: `pytest librarian/tests/test_materialize.py librarian/tests/test_update_materialize.py librarian/tests/test_update_two_vault.py -q`
Expected: PASS — the new direct test plus the existing materialize/two-vault suites (now exercising the delegated path).

Run: `pytest -q`
Expected: PASS — full suite green; report the count.

- [ ] **Step 6: Commit**

```bash
git add librarian/orchestrate/materialize.py librarian/update.py librarian/tests/test_materialize.py
git commit -m "refactor(librarian): extract orchestrate/materialize.py (cfg-explicit)"
```

---

## Task 2: `label_model` config knob

**Files:**
- Modify: `librarian/config.py`, `config.example.yaml`
- Test: `librarian/tests/test_config.py`

Context (spec §4 "labeling knobs: … model"): the display/labeling model the SKILL passes to `claude -p` when dispatching wave agents. No Python consumes it yet (the skill does, in the packaging plan); this completes the config contract. Default `"sonnet"` (a capable, cost-effective bulk-labeling default; the user overrides per library).

- [ ] **Step 1: Write the failing test**

Append to `librarian/tests/test_config.py`:

```python
def test_label_model_default(cfg):
    assert cfg.label_model == "sonnet"


def test_loader_reads_label_model(tmp_path):
    from librarian import config
    p = tmp_path / "config.yaml"
    p.write_text(
        "corpus_path: ./v\nlibrary_path: ./l\ndata_dir: ./d\n"
        "categories: [Literature]\nlabel_model: opus\n", encoding="utf-8")
    assert config.load(p).label_model == "opus"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_config.py::test_label_model_default -q`
Expected: FAIL — `'Config' object has no attribute 'label_model'`.

- [ ] **Step 3: Add the field**

In `librarian/config.py`, add to the labeling-knob block (right after `extractor_version: str = "knowledge-library"`):
```python
    label_model: str = "sonnet"          # model the skill passes to `claude -p`
```

- [ ] **Step 4: Teach the loader the key**

In `librarian/config.py`, in `load()`, add `"label_model"` to the optional-key tuple. Change:
```python
                "agents_per_wave", "articles_per_agent", "extractor_version"):
```
to:
```python
                "agents_per_wave", "articles_per_agent", "extractor_version",
                "label_model"):
```

- [ ] **Step 5: Document it in the example config**

In `config.example.yaml`, in the `# LABELING (defaults shown)` section, add after the `extractor_version:` line:
```yaml
label_model: sonnet                      # model the skill passes to `claude -p` for labeling
```

- [ ] **Step 6: Run tests**

Run: `pytest librarian/tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add librarian/config.py config.example.yaml librarian/tests/test_config.py
git commit -m "feat(librarian): label_model config knob"
```

---

## Task 3: Harden `ingest_wave` against malformed agent JSON

**Files:**
- Modify: `librarian/orchestrate/ingest_wave.py`
- Test: `librarian/tests/test_ingest_wave.py`

Context: agents are the primary failure surface. Currently `for j in json.loads(...)` crashes on invalid JSON (`JSONDecodeError`), a non-list payload (iterates dict keys → `TypeError`), or a missing `relative_path` (`KeyError`). Harden `ingest` to collect these as structured `errors` and bail (all-or-nothing, nothing written) — never crash. Valid-list payloads behave exactly as before.

- [ ] **Step 1: Write the failing tests**

Append to `librarian/tests/test_ingest_wave.py`:

```python
def test_invalid_json_is_reported_not_raised(cfg, tmp_path):
    cfg = _cfg(cfg)
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    summary = ingest_wave.ingest([str(bad)], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("invalid JSON" in e for e in summary["errors"])
    assert store.load(cfg.labels_path) == []


def test_non_list_payload_is_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    obj = _write_json(tmp_path, _judgment(), name="obj.json")  # a dict, not a list
    summary = ingest_wave.ingest([obj], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("expected a JSON array" in e for e in summary["errors"])


def test_item_missing_relative_path_is_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    j = _judgment()
    del j["relative_path"]
    jp = _write_json(tmp_path, [j])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("relative_path" in e for e in summary["errors"])
```

Note: `_write_json` (already in the file) calls `json.dumps(objs, ...)`; `test_non_list_payload_is_reported` passes a bare dict (not wrapped in a list) so the file contains a JSON object.

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest librarian/tests/test_ingest_wave.py -q`
Expected: FAIL — the three new tests raise (`JSONDecodeError`/`TypeError`/`KeyError`) instead of returning a summary.

- [ ] **Step 3: Harden `ingest`**

In `librarian/orchestrate/ingest_wave.py`, replace the body of `ingest` from its first executable line through the `validate.check` error return. Replace:
```python
    frozen = _frozen_index(manifest_rows, legacy)
    rows, skipped = [], []
    for jp in sorted(str(p) for p in json_paths):
        for j in json.loads(Path(jp).read_text(encoding="utf-8")):
            rel = unicodedata.normalize("NFC", j["relative_path"])
            if rel not in frozen:
                skipped.append(rel)
                continue
            rows.append(_row(j, frozen[rel], cfg, today, run_id))
    expected = [r[PATH_I] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        return {"merged": 0, "review": 0, "errors": errors,
                "skipped": skipped, "proposals": []}
```
with:
```python
    frozen = _frozen_index(manifest_rows, legacy)
    rows, skipped, parse_errors = [], [], []
    for jp in sorted(str(p) for p in json_paths):
        try:
            data = json.loads(Path(jp).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            parse_errors.append(f"{jp}: invalid JSON ({e})")
            continue
        if not isinstance(data, list):
            parse_errors.append(
                f"{jp}: expected a JSON array, got {type(data).__name__}")
            continue
        for j in data:
            if not isinstance(j, dict) or not j.get("relative_path"):
                parse_errors.append(f"{jp}: item missing 'relative_path'")
                continue
            rel = unicodedata.normalize("NFC", j["relative_path"])
            if rel not in frozen:
                skipped.append(rel)
                continue
            rows.append(_row(j, frozen[rel], cfg, today, run_id))
    if parse_errors:
        return {"merged": 0, "review": 0, "errors": parse_errors,
                "skipped": skipped, "proposals": []}
    expected = [r[PATH_I] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        return {"merged": 0, "review": 0, "errors": errors,
                "skipped": skipped, "proposals": []}
```

- [ ] **Step 4: Run tests**

Run: `pytest librarian/tests/test_ingest_wave.py -q`
Expected: PASS — the three new hardening tests plus all existing ingest_wave tests (valid lists behave unchanged).

- [ ] **Step 5: Commit**

```bash
git add librarian/orchestrate/ingest_wave.py librarian/tests/test_ingest_wave.py
git commit -m "feat(librarian): ingest_wave surfaces malformed agent JSON as errors"
```

---

## Task 4: `orchestrate/steady_state.py` — the run-ledger writer

**Files:**
- Create: `librarian/orchestrate/steady_state.py`
- Test: `librarian/tests/test_steady_state.py`

Context (spec §7): the deterministic glue around the external fetch + LLM-labeling steps. `diff_new` finds net-new inbox articles by url; `finish` runs the tail (ingest the labeled wave → materialize into the library → verify) and appends one run-ledger row; `record_nothing_new` logs a zero-cost empty pull. Timestamps + `run_id` are passed in (deterministic for tests; the wrapper supplies real ones). Reuses Plan-4 `ledger` + the extracted `materialize`.

- [ ] **Step 1: Write the failing tests**

Create `librarian/tests/test_steady_state.py`:

```python
"""Steady-state deterministic glue (spec §7): diff_new / finish / record_nothing_new."""
import json

from librarian import config, contract, tsv, manifest, registry, store, ledger
from librarian.orchestrate import steady_state


def _cfg(tmp_path, inbox_name="inbox"):
    inbox = tmp_path / inbox_name
    c = config.Config(corpus_path=inbox, library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"Literature"},
                      label_language="en", hub_min_articles=1)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _node(vault, rel, url):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "{rel}"\nsource: blog\nurl: "{url}"\n---\n\nBody.\n',
                 encoding="utf-8")


def _lrow(rel, url=None):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[3], r[4] = rel, "Literature", "Lit Crit"
    return r


def _reg(cfg):
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])


def test_diff_new_is_net_new_by_url(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    # library already has article with url U1 (filed under Literature/)
    _node(lib, "Literature/a.md", "https://x/1")
    store.merge(cfg.labels_path, [_lrow("Literature/a.md")])
    # inbox has a re-fetch of U1 (known) + a brand-new U2
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    _node(cfg.corpus_path, "blog/b.md", "https://x/2")
    new = steady_state.diff_new(cfg, lib)
    assert [r[0] for r in new] == ["blog/b.md"]


def test_record_nothing_new_logs_zero_cost_run(tmp_path):
    cfg = _cfg(tmp_path)
    row, digest = steady_state.record_nothing_new(
        cfg, run_id="r1", started_at="2026-06-13T10:00", finished_at="2026-06-13T10:00")
    assert digest == "0 new · 0 proposed · 0 flagged"
    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "nothing_new"
    assert ledger.latest(cfg.runs_path)[i("run_id")] == "r1"


def test_finish_ingests_materializes_verifies_and_logs_ok(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    lib.mkdir(parents=True, exist_ok=True)
    _reg(cfg)
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    man = manifest.build(cfg.corpus_path, cfg)
    objs = [{"relative_path": "blog/a.md", "primary_category": "Literature",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []}]
    jp = cfg.data_dir / "wave.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    row, digest = steady_state.finish(
        cfg, lib, [str(jp)], run_id="r1", started_at="2026-06-13T10:00",
        finished_at="2026-06-13T10:05", today="2026-06-13", fetched=1, new=1)

    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "ok"
    assert row[i("labeled")] == "1"
    assert digest == "1 new · 0 proposed · 0 flagged"
    assert (lib / "Literature" / "a.md").exists()      # materialized into the library
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert all(r[fsr] == "r1" for r in store.load(cfg.labels_path))
    assert ledger.latest(cfg.runs_path)[i("status")] == "ok"


def test_finish_off_canon_logs_error_and_materializes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    lib.mkdir(parents=True, exist_ok=True)
    _reg(cfg)
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    objs = [{"relative_path": "blog/a.md", "primary_category": "NotACategory",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []}]
    jp = cfg.data_dir / "wave.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    row, _ = steady_state.finish(
        cfg, lib, [str(jp)], run_id="r1", started_at="2026-06-13T10:00",
        finished_at="2026-06-13T10:05", today="2026-06-13", fetched=1, new=1)

    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "error"
    assert store.load(cfg.labels_path) == []           # nothing ingested
    assert not (lib / "Literature").exists()           # nothing materialized
    assert ledger.latest(cfg.runs_path)[i("status")] == "error"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest librarian/tests/test_steady_state.py -q`
Expected: FAIL — `No module named 'librarian.orchestrate.steady_state'`.

- [ ] **Step 3: Write `orchestrate/steady_state.py`**

Create `librarian/orchestrate/steady_state.py`:

```python
"""Steady-state run orchestration (spec §7): the DETERMINISTIC glue around the
external steps. The zhihu-fetcher and the parallel LLM labeling live in the
schedule wrapper / SKILL, not here. `diff_new` finds net-new inbox articles by
url; `finish` runs the tail (ingest the labeled wave -> materialize into the
library -> verify) and appends one run-ledger row; `record_nothing_new` logs a
zero-cost empty pull. Each path returns (run_row, digest)."""
from librarian import (contract, tsv, manifest, registry, store, ledger, verify)
from librarian.orchestrate import ingest_wave, materialize


def diff_new(cfg, library):
    """Inbox articles whose stable url is not yet in `library` (net-new). Keyed
    by url so a re-fetch (same url, new bytes) is not treated as new — mirrors
    update's two-vault diff."""
    known = {u for u in (manifest.read_url(library / r[0])
                         for r in store.load(cfg.labels_path)) if u}
    new = []
    for r in manifest.build(cfg.corpus_path, cfg):
        url = manifest.read_url(cfg.corpus_path / r[0])
        if url is None or url not in known:
            new.append(r)
    return new


def _row(run_id, started_at, finished_at, source, fetched, new, labeled,
         proposed, flagged, status, lang):
    return [run_id, started_at, finished_at, source, str(fetched), str(new),
            str(labeled), str(proposed), str(flagged), status, lang]


def record_nothing_new(cfg, *, run_id, started_at, finished_at, source="zhihu",
                       fetched=0, lang="en"):
    """Append a `nothing_new` run row — a clean empty pull, no LLM spend."""
    row = _row(run_id, started_at, finished_at, source, fetched, 0, 0, 0, 0,
               "nothing_new", lang)
    ledger.append(cfg.runs_path, row)
    return row, ledger.digest(row)


def finish(cfg, library, json_paths, *, run_id, started_at, finished_at, today,
           source="zhihu", fetched=0, new=0, lang="en"):
    """The deterministic tail of a steady-state run: ingest the labeled wave
    (rows stamped with run_id), materialize into `library`, verify, and append a
    run row. On an ingest error nothing is materialized and the row is `error`.
    Returns (run_row, digest)."""
    reg = registry.load(cfg.topics_path)
    inbox_manifest = manifest.build(cfg.corpus_path, cfg)
    from librarian.update import load_legacy
    legacy = load_legacy(cfg.legacy_labels)
    summary = ingest_wave.ingest(json_paths, inbox_manifest, legacy, reg, cfg,
                                 today, run_id=run_id)
    if summary["errors"]:
        row = _row(run_id, started_at, finished_at, source, fetched, new, 0, 0,
                   0, "error", lang)
        ledger.append(cfg.runs_path, row)
        return row, ledger.digest(row)
    materialize.materialize(cfg, write=True, out=library, lang=lang)
    man_rows = None
    if cfg.manifest_path.exists():
        _header, man_rows = tsv.read_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS)
    problems = verify.run(store.load(cfg.labels_path), registry.load(cfg.topics_path),
                          library, cfg.categories, cfg, manifest_rows=man_rows, lang=lang)
    status = "ok" if not problems else "error"
    row = _row(run_id, started_at, finished_at, source, fetched, new,
               summary["merged"], len(summary["proposals"]), summary["review"],
               status, lang)
    ledger.append(cfg.runs_path, row)
    return row, ledger.digest(row)
```

- [ ] **Step 4: Run tests**

Run: `pytest librarian/tests/test_steady_state.py -q`
Expected: PASS (4 tests).

Run: `pytest -q`
Expected: PASS — full suite green; report the count.

- [ ] **Step 5: Commit**

```bash
git add librarian/orchestrate/steady_state.py librarian/tests/test_steady_state.py
git commit -m "feat(librarian): orchestrate.steady_state — run-ledger writer (spec §7)"
```

---

## Task 5: Move `status` under `orchestrate/`

**Files:**
- Move: `librarian/status.py` → `librarian/orchestrate/status.py`
- Modify: `librarian/update.py` (import), `librarian/tests/test_status.py` (import)

Context (spec §3 layout): `status` is an orchestration entry point and belongs in `orchestrate/` alongside `materialize`/`steady_state`/`build_wave`/`ingest_wave`. The module body is unchanged (its `from librarian import ...` imports still resolve); only its location and two importers change.

- [ ] **Step 1: Move the file with git**

```bash
git mv librarian/status.py librarian/orchestrate/status.py
```
(The module's internal imports — `from librarian import store, registry, audit, ledger, contract` — are unaffected by the move.)

- [ ] **Step 2: Update the importer in `update.py`**

In `librarian/update.py`, in `cmd_status`, replace:
```python
def cmd_status():
    from librarian import status
    print(status.render(cfg))
```
with:
```python
def cmd_status():
    from librarian.orchestrate import status
    print(status.render(cfg))
```

- [ ] **Step 3: Update the importer in the test**

In `librarian/tests/test_status.py`, replace the import line:
```python
from librarian import status, config, contract, tsv, store, ledger
```
with:
```python
from librarian.orchestrate import status
from librarian import config, contract, tsv, store, ledger
```

- [ ] **Step 4: Run the affected + full suite**

Run: `pytest librarian/tests/test_status.py -q`
Expected: PASS (4 tests).

Run: `pytest -q`
Expected: PASS — full suite green; report the count.

- [ ] **Step 5: Commit**

```bash
git add librarian/status.py librarian/orchestrate/status.py librarian/update.py librarian/tests/test_status.py
git commit -m "refactor(librarian): move status under orchestrate/ (spec §3 layout)"
```

---

## Self-Review (run after all tasks)

**1. Spec coverage (spec §7 steady-state + §3 orchestrate layout + §4 model knob + carried hardening):**
- §3 `orchestrate/materialize.py` → Task 1 (extracted, cfg-explicit). ✓
- §3 `orchestrate/steady_state.py` + `orchestrate/status.py` → Tasks 4, 5. (The full `orchestrate/` set — build_wave, ingest_wave, materialize, steady_state, status — now exists.) ✓
- §7 steady-state flow: diff net-new (`diff_new`), zero-new clean no-op (`record_nothing_new`, no LLM spend), label→file→verify→digest (`finish`), idempotent/non-destructive (reuses materialize's move-by-url) → Task 4. The external fetch + LLM dispatch are correctly deferred to the wrapper/SKILL (packaging plan). ✓
- §7/§9 digest "N new · M proposed · K flagged" from the ledger row → `finish`/`record_nothing_new` return `ledger.digest(row)`. ✓
- §9 status enum drives the run row (`ok`/`nothing_new`/`error`); `finish` sets `error` on ingest failure or verify problems. (`auth_failed` is a fetch-side status the wrapper sets — not reachable from this deterministic tail; noted.) ✓
- §4 `model` labeling knob → Task 2 (`label_model`). ✓
- Hardening ingest vs malformed/non-list/missing-key agent JSON (deferred from Plan 2) → Task 3. ✓
- **Out of scope, correctly deferred:** `SKILL.md` + `references/` + `templates/` + `schedule/` (wrapper.sh + launchd plist) — the skill assembly + scheduling (spec §3 packaging, §10), which wires the real `claude -p` + zhihu-fetcher and a recurring `update-library` CLI. ✓

**2. Placeholder scan:** every step has literal code or an exact old→new edit + an exact `pytest` command with expected result. The materialize extraction reproduces the functions verbatim (cfg-parameterized); no "TBD"/"handle errors".

**3. Type/signature consistency across tasks:**
- `materialize.materialize(cfg, write=False, out=None, lang="en")` + `_to_library(cfg, rows, reg, library, write, lang="en")` + `_free_dest(library, primary, base, url, taken)` — Task 1; called by `update.cmd_materialize` (delegator) and `steady_state.finish` (Task 4). ✓
- `steady_state.diff_new(cfg, library)`, `record_nothing_new(cfg, *, run_id, started_at, finished_at, source, fetched, lang) -> (row, digest)`, `finish(cfg, library, json_paths, *, run_id, started_at, finished_at, today, source, fetched, new, lang) -> (row, digest)` — Task 4; rows built via the local `_row` in `RUN_COLUMNS` order, appended with `ledger.append`, digested with `ledger.digest`. ✓
- `ingest_wave.ingest(..., run_id="")` return dict `{merged, review, errors, skipped, proposals}` — unchanged shape after Task 3 hardening; consumed by `steady_state.finish`. ✓
- `cfg.label_model` (Task 2), `cfg.runs_path`/`contract.RUN_COLUMNS`/`ledger.*` (Plan 4), `verify.run(..., lang=)` (Plan 3) — all reused as defined. ✓
- `orchestrate.status.render(cfg)` — relocated Task 5; `update.cmd_status` imports `from librarian.orchestrate import status`. ✓
- Import-cycle check: `steady_state` imports `orchestrate.{ingest_wave, materialize}` + `librarian.{...}` and defers `from librarian.update import load_legacy` inside `finish`; `materialize` imports only `librarian.{...}` (not `update`); `update.cmd_materialize` defers `from librarian.orchestrate import materialize`. No cycle. ✓

**Note on `diff_new` duplication:** `update._new_inbox_rows` already implements the same net-new-by-url logic against the module-level `cfg`. `steady_state.diff_new` is the cfg-explicit twin (a ~6-line overlap). They are intentionally left as parallel implementations to avoid an `update ↔ steady_state` import cycle; if a future plan unifies them, `update._new_inbox_rows` should delegate to `steady_state.diff_new(cfg, library)`.

---

## Execution note

Plan 5 is behaviour-preserving for materialize (verbatim relocation; the existing materialize/two-vault suites are the regression guard) and otherwise additive. The completion signal is a green full suite (Task 1 Step 5, Task 4 Step 4, Task 5 Step 4). After this, the `librarian/` toolkit is functionally complete for both bootstrap and steady-state; the only remaining work is the **skill assembly** (`SKILL.md` + `references/` + `templates/` + `schedule/`) that wraps these deterministic functions with the real `claude -p` labeling dispatch + zhihu-fetcher + launchd scheduling — the final packaging plan.
