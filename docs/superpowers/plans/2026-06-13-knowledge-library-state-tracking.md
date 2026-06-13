# Knowledge-Library State & Run Tracking Implementation Plan (Plan 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the state & run-tracking layer (spec §9) — an append-only run ledger, a `first_seen_run` provenance column, and a `librarian status` command — plus a synthetic end-to-end test that exercises the whole pipeline against real `manifest.build` output, and two small cleanups.

**Architecture:** A new `librarian/ledger.py` owns `data/runs.tsv` (append-only, one row per run; columns per spec §9 extended with the materialize `lang`). `first_seen_run` is appended as the LAST `LABEL_COLUMNS` entry — exactly the pattern Plan 1 used for `name_zh` — so every existing positional read (`r[0..14]`) is unchanged and only fixtures that round-trip through width-checking paths need a trailing field; `ingest_wave` stamps it from a caller-supplied `run_id`. A new `librarian/status.py` renders the on-demand status string by reading the ledger, labels, registry, and the `audit.report` queues (read-only). The synthetic E2E test drives `adapter → ingest_to_inbox → manifest.build → build_wave → ingest_wave → materialize → verify` end-to-end.

**Tech Stack:** Python 3, stdlib only (`json`, `datetime`) + existing `librarian` modules (`tsv`, `contract`, `store`, `registry`, `audit`, `manifest`, `proposals`). Tests: `pytest`, run from `knowledge-library/`.

**Scope (Plan 4 = "state tracking + E2E + cleanups", per user decision):** run ledger + `first_seen_run` + `librarian status` + synthetic E2E test + (unify the `data_dir` mkdir guard, MyBooks→knowledge-library branding sweep). **Non-goals (deferred):** the steady-state `update-library` recurring entry point that WRITES ledger rows during a run (spec §7 — Plan 5; this plan builds the ledger primitives + reader, not the run-writer); the `orchestrate/materialize.py` extraction (spec §3); skill packaging/scheduling (Plan 5).

**Working directory for all commands:** `/Users/kunwu/Workspace/MyLibrary/knowledge-library`
**Run tests with:** `pytest -q` (the `conftest.py` there puts `librarian` on `sys.path`; bare `python`/`python3` is 3.14 without pytest — use the `pytest` command).

**Migration note:** the corpus is fresh/empty (spec §4b), so there is no legacy 15-column labels TSV to migrate — adding the 16th column is safe.

---

## File Structure

| File | Responsibility |
|---|---|
| `librarian/contract.py` *(modify)* | Append `first_seen_run` to `LABEL_COLUMNS`; add `RUN_COLUMNS` + `RUN_STATUS`. |
| `librarian/config.py` *(modify)* | Add `runs_path` property. |
| `librarian/orchestrate/ingest_wave.py` *(modify)* | `ingest(..., run_id="")` stamps `first_seen_run` via `_row(..., run_id)`. |
| `librarian/ledger.py` *(create)* | `data/runs.tsv` append-only: `load`/`append`/`latest`/`digest`. |
| `librarian/status.py` *(create)* | `render(cfg)` — the on-demand status string (spec §9). |
| `librarian/update.py` *(modify)* | `cmd_status()` + `status` CLI subcommand. |
| `librarian/tsv.py` *(modify)* | `write_rows` ensures the parent dir exists (unifies the mkdir guard). |
| `librarian/orchestrate/ingest_wave.py` *(modify, cleanup)* | drop the now-redundant `cfg.labels_path.parent.mkdir`. |
| `librarian/batches.py` *(modify, cleanup)* | branding: "MyBooks"→"knowledge-library" in the batch header. |
| `librarian/{config,reconcile,update}.py` *(modify, cleanup)* | branding: stale "mybooks" mentions in docstrings/comments. |
| `librarian/tests/test_contract.py` *(modify)* | assert the new `first_seen_run` column. |
| `librarian/tests/test_{store,validate,verify}.py` *(modify)* | +1 trailing field on the fixed-width label-row builders. |
| `librarian/tests/test_ingest_wave.py` *(modify)* | new `first_seen_run` stamping test. |
| `librarian/tests/test_ledger.py` *(create)* | ledger behaviour. |
| `librarian/tests/test_status.py` *(create)* | status rendering. |
| `librarian/tests/test_e2e.py` *(create)* | synthetic end-to-end pipeline. |
| `librarian/tests/test_tsv.py` *(modify)* | write_rows creates parent dir. |

---

## Task 1: Add the `first_seen_run` provenance column

**Files:**
- Modify: `librarian/contract.py`, `librarian/orchestrate/ingest_wave.py`
- Test: `librarian/tests/test_contract.py`, `test_store.py`, `test_validate.py`, `test_verify.py`, `test_ingest_wave.py`

Context: `first_seen_run` traces each article to the run that introduced it (spec §9). Appended LAST in `LABEL_COLUMNS` so positional reads `r[0..14]` are unchanged (mirrors `name_zh` in `TOPIC_COLUMNS`). Only fixtures that pass through `tsv.write_rows`/`validate.check`/`verify.run` (which check row width against `len(LABEL_COLUMNS)`) need a trailing field; builders using `[""] * len(contract.LABEL_COLUMNS)` auto-adapt.

- [ ] **Step 1: Update `test_contract.py` (failing first)**

In `librarian/tests/test_contract.py`, replace `test_label_columns_complete_and_ordered`:

```python
def test_label_columns_complete_and_ordered():
    assert contract.LABEL_COLUMNS[0] == "relative_path"
    assert contract.LABEL_COLUMNS[-1] == "labeled_at"
    assert len(contract.LABEL_COLUMNS) == 15
    assert len(set(contract.LABEL_COLUMNS)) == 15
```
with:
```python
def test_label_columns_complete_and_ordered():
    assert contract.LABEL_COLUMNS[0] == "relative_path"
    # first_seen_run is APPENDED last (spec §9 provenance) so positional reads
    # r[0]..r[14] in store/validate/verify/ingest_wave stay unchanged; labeled_at
    # is now second-to-last.
    assert contract.LABEL_COLUMNS[-2] == "labeled_at"
    assert contract.LABEL_COLUMNS[-1] == "first_seen_run"
    assert len(contract.LABEL_COLUMNS) == 16
    assert len(set(contract.LABEL_COLUMNS)) == 16
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_contract.py::test_label_columns_complete_and_ordered -q`
Expected: FAIL (length is 15, last is "labeled_at").

- [ ] **Step 3: Append the column in `contract.py`**

In `librarian/contract.py`, replace:
```python
LABEL_COLUMNS = ["relative_path", "title", "original_category",
                 "primary_category", "topics", "tags", "article_type",
                 "summary", "confidence", "needs_review", "review_reason",
                 "proposed_topics", "content_hash", "extractor_version",
                 "labeled_at"]
```
with:
```python
# first_seen_run is APPENDED last (spec §9): it traces an article to the run
# that introduced it. Appended so store/validate/verify/ingest_wave positional
# reads (r[0]..r[14]) are unchanged — same discipline as TOPIC_COLUMNS.name_zh.
LABEL_COLUMNS = ["relative_path", "title", "original_category",
                 "primary_category", "topics", "tags", "article_type",
                 "summary", "confidence", "needs_review", "review_reason",
                 "proposed_topics", "content_hash", "extractor_version",
                 "labeled_at", "first_seen_run"]
```

- [ ] **Step 4: Stamp it in `ingest_wave.py`**

In `librarian/orchestrate/ingest_wave.py`, change `_row`'s signature:
```python
def _row(j, frozen, cfg, today):
```
to:
```python
def _row(j, frozen, cfg, today, run_id):
```
and append `run_id` as the final list element — replace:
```python
        cfg.extractor_version,
        today,
    ]
```
with:
```python
        cfg.extractor_version,
        today,
        run_id,
    ]
```
Change `ingest`'s signature:
```python
def ingest(json_paths, manifest_rows, legacy, reg, cfg, today):
```
to:
```python
def ingest(json_paths, manifest_rows, legacy, reg, cfg, today, run_id=""):
```
Update the `_row` call inside `ingest` — replace:
```python
            rows.append(_row(j, frozen[rel], cfg, today))
```
with:
```python
            rows.append(_row(j, frozen[rel], cfg, today, run_id))
```
Update the docstring of `ingest` — replace its first line:
```python
    """Read agent JSON outputs and merge validated rows into cfg.labels_path.
```
with:
```python
    """Read agent JSON outputs and merge validated rows into cfg.labels_path,
    stamping each row's first_seen_run with `run_id` (spec §9 provenance).
```

- [ ] **Step 5: Add the +1 trailing field to the three width-checked fixtures**

In `librarian/tests/test_store.py`, replace the `row` helper:
```python
def row(rel, primary="文学"):
    return [rel, "t", "旧", primary, "文学评论", "", "文学评论", "s",
            "high", "false", "", "", "h" * 16, "v1", "d"]
```
with:
```python
def row(rel, primary="文学"):
    return [rel, "t", "旧", primary, "文学评论", "", "文学评论", "s",
            "high", "false", "", "", "h" * 16, "v1", "d", ""]
```

In `librarian/tests/test_validate.py`, replace the `row` helper:
```python
def row(rel="文学/a.md", primary="文学", topics="文学评论", proposed="",
        conf="high", review="false"):
    return [rel, "t", "旧类", primary, topics, "tag1", "文学评论", "摘要。",
            conf, review, "", proposed, "h" * 16, "v1", "2026-06-11"]
```
with:
```python
def row(rel="文学/a.md", primary="文学", topics="文学评论", proposed="",
        conf="high", review="false"):
    return [rel, "t", "旧类", primary, topics, "tag1", "文学评论", "摘要。",
            conf, review, "", proposed, "h" * 16, "v1", "2026-06-11", ""]
```

In `librarian/tests/test_verify.py`, replace the `lrow` helper:
```python
def lrow(rel, primary="文学", topics="文学评论"):
    return [rel, "", "", primary, topics, "", "", "s", "high", "false", "",
            "", "h" * 16, "v1", "d"]
```
with:
```python
def lrow(rel, primary="文学", topics="文学评论"):
    return [rel, "", "", primary, topics, "", "", "s", "high", "false", "",
            "", "h" * 16, "v1", "d", ""]
```
and in the same file, both `lr = [...]` lists inside `test_lang_zh_localized_vault_verifies_clean` and `test_lang_zh_wrong_localized_folder_flagged` end with `"h" * 16, "v1", "d"]` — append `, ""` to each so they read `... "h" * 16, "v1", "d", ""]`.

- [ ] **Step 6: Add a `first_seen_run` stamping test to `test_ingest_wave.py`**

Append to `librarian/tests/test_ingest_wave.py`:

```python
def test_first_seen_run_is_stamped(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13",
                       run_id="run-7")
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert store.load(cfg.labels_path)[0][fsr] == "run-7"


def test_first_seen_run_defaults_to_empty(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert store.load(cfg.labels_path)[0][fsr] == ""
```

- [ ] **Step 7: Run the FULL suite to verify green**

Run: `pytest -q`
Expected: PASS — all tests, including the updated contract/store/validate/verify and the new ingest_wave stamping tests. (Builders using `[""] * len(contract.LABEL_COLUMNS)` auto-adapt to 16; only the three fixed-width fixtures needed the trailing field.)

- [ ] **Step 8: Commit**

```bash
git add librarian/contract.py librarian/orchestrate/ingest_wave.py librarian/tests/test_contract.py librarian/tests/test_store.py librarian/tests/test_validate.py librarian/tests/test_verify.py librarian/tests/test_ingest_wave.py
git commit -m "feat(librarian): add first_seen_run provenance column (spec §9)"
```

---

## Task 2: Run ledger — `librarian/ledger.py`

**Files:**
- Create: `librarian/ledger.py`
- Modify: `librarian/contract.py` (add `RUN_COLUMNS` + `RUN_STATUS`), `librarian/config.py` (add `runs_path`)
- Test: `librarian/tests/test_ledger.py`

Context (spec §9): `data/runs.tsv` is append-only, one row per run. Columns are the spec schema extended with a trailing `lang` (the materialize display language a library was built with — the Plan 3 carry-forward note, so a future steady-state never re-runs a `zh` library under `en`). The §7 digest renders the latest row.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_ledger.py`:

```python
from librarian import ledger, contract, config


def _cfg(tmp_path):
    # create data_dir so the ledger tests pass independently of Task 6's
    # tsv.write_rows parent-dir guard.
    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"Literature"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _run(run_id, new="3", flagged="0", proposed="1", status="ok", lang="en"):
    # RUN_COLUMNS order: run_id, started_at, finished_at, source, fetched, new,
    # labeled, proposed_topics, flagged, status, lang
    return [run_id, "2026-06-13T10:00", "2026-06-13T10:05", "zhihu", "10",
            new, new, proposed, flagged, status, lang]


def test_run_columns_and_status_enum():
    assert contract.RUN_COLUMNS == [
        "run_id", "started_at", "finished_at", "source", "fetched", "new",
        "labeled", "proposed_topics", "flagged", "status", "lang"]
    assert contract.RUN_STATUS == {"ok", "nothing_new", "auth_failed", "error"}


def test_runs_path_property(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.runs_path == cfg.data_dir / "runs.tsv"


def test_load_missing_ledger_is_empty(tmp_path):
    cfg = _cfg(tmp_path)
    assert ledger.load(cfg.runs_path) == []
    assert ledger.latest(cfg.runs_path) is None


def test_append_creates_and_accumulates(tmp_path):
    cfg = _cfg(tmp_path)
    ledger.append(cfg.runs_path, _run("r1"))
    ledger.append(cfg.runs_path, _run("r2", new="0", status="nothing_new"))
    rows = ledger.load(cfg.runs_path)
    assert [r[0] for r in rows] == ["r1", "r2"]
    assert ledger.latest(cfg.runs_path)[0] == "r2"


def test_append_rejects_wrong_width(tmp_path):
    cfg = _cfg(tmp_path)
    try:
        ledger.append(cfg.runs_path, ["r1", "only", "three"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_digest_renders_new_proposed_flagged():
    assert ledger.digest(_run("r1", new="3", proposed="1", flagged="2")) == \
        "3 new · 1 proposed · 2 flagged"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_ledger.py -q`
Expected: FAIL — `AttributeError: module 'librarian.contract' has no attribute 'RUN_COLUMNS'` / `No module named 'librarian.ledger'`.

- [ ] **Step 3: Add `RUN_COLUMNS` + `RUN_STATUS` to `contract.py`**

In `librarian/contract.py`, append after the existing enum definitions (after `TOPIC_STATUS = {...}`):

```python
# Run ledger (spec §9): one append-only row per run. `lang` (the materialize
# display language) extends the spec schema so a future steady-state never
# re-runs a localized library under a different display language.
RUN_COLUMNS = ["run_id", "started_at", "finished_at", "source", "fetched",
               "new", "labeled", "proposed_topics", "flagged", "status", "lang"]
RUN_STATUS = {"ok", "nothing_new", "auth_failed", "error"}
```

- [ ] **Step 4: Add the `runs_path` property to `config.py`**

In `librarian/config.py`, add after the `migration_log_path` property:

```python
    @property
    def runs_path(self):
        return self.data_dir / "runs.tsv"
```

- [ ] **Step 5: Write `ledger.py`**

Create `librarian/ledger.py`:

```python
"""Append-only run ledger (spec §9): one row per run in data/runs.tsv — the
human-facing answer to 'what did this run pull'. It sits above the fetcher
history + manifest dedup (which prevent re-download / re-label); the §7 digest
renders the latest row. The actual writing of rows during a run is the
steady-state orchestrator's job (deferred); this module is the primitive."""
from librarian import tsv, contract


def load(path):
    """All run rows in append order, or [] when the ledger does not exist yet."""
    if not path.exists():
        return []
    _header, rows = tsv.read_rows(path, contract.RUN_COLUMNS)
    return rows


def append(path, row):
    """Append one run row to the ledger (creating it with a header if absent).
    Raises ValueError on a wrong-width row. Returns all rows after the append."""
    if len(row) != len(contract.RUN_COLUMNS):
        raise ValueError(
            f"run row width {len(row)} != {len(contract.RUN_COLUMNS)}")
    rows = load(path) + [row]
    tsv.write_rows(path, contract.RUN_COLUMNS, rows)
    return rows


def latest(path):
    """The most recently appended run row, or None when the ledger is empty."""
    rows = load(path)
    return rows[-1] if rows else None


def digest(row):
    """The one-line steady-state digest (spec §7): 'N new · M proposed · K flagged'."""
    i = contract.RUN_COLUMNS.index
    return (f"{row[i('new')]} new · {row[i('proposed_topics')]} proposed · "
            f"{row[i('flagged')]} flagged")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest librarian/tests/test_ledger.py librarian/tests/test_contract.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add librarian/ledger.py librarian/contract.py librarian/config.py librarian/tests/test_ledger.py
git commit -m "feat(librarian): append-only run ledger (data/runs.tsv, spec §9)"
```

---

## Task 3: Status renderer — `librarian/status.py`

**Files:**
- Create: `librarian/status.py`
- Test: `librarian/tests/test_status.py`

Context (spec §9): `librarian status` reads the ledger + labels + registry + audit queues and prints a four-line summary on demand. This task builds the pure `render(cfg)` function; Task 4 wires the CLI. It must handle an empty ledger and a missing topics file gracefully.

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_status.py`:

```python
from librarian import status, config, contract, tsv, store, ledger


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"Literature"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _lrow(rel, topics="Lit Crit", review="false", proposed=""):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[3], r[4] = rel, "Literature", topics
    r[9], r[11] = review, proposed
    return r


def _seed_topics(cfg):
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])


def _run(run_id, new="3", flagged="0", status="ok"):
    return [run_id, "2026-05-01T09:00", "2026-06-13T10:05", "zhihu", "10",
            new, new, "0", flagged, status, "en"]


def test_status_empty_ledger(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_topics(cfg)
    store.merge(cfg.labels_path, [_lrow("Literature/a.md")])
    out = status.render(cfg)
    assert "Library: 1 articles · canon 1 topics" in out
    assert "Last run: never" in out
    assert "History: 0 runs" in out


def test_status_with_runs_and_queues(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_topics(cfg)
    store.merge(cfg.labels_path, [
        _lrow("Literature/a.md", review="true"),
        _lrow("Literature/b.md", topics="新话题", proposed="新话题")])
    ledger.append(cfg.runs_path, _run("r1", status="auth_failed"))
    ledger.append(cfg.runs_path, _run("r2", new="3", flagged="1", status="ok"))
    out = status.render(cfg)
    assert "Last run: 2026-06-13T10:05  +3 new, 1 flagged   [ok]" in out
    assert "Pending: 1 proposed topics · 1 needs-review" in out
    assert "History: 2 runs since 2026-05-01T09:00" in out
    assert "last auth_failed: 2026-06-13T10:05" in out


def test_status_no_topics_file(tmp_path):
    cfg = _cfg(tmp_path)  # no topics.tsv written
    out = status.render(cfg)
    assert "Library: 0 articles · canon 0 topics" in out
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_status.py -q`
Expected: FAIL — `No module named 'librarian.status'`.

- [ ] **Step 3: Write `status.py`**

Create `librarian/status.py`:

```python
"""Render the on-demand library status (spec §9): library size + canon size,
last run, pending queues, run history. Reads the ledger, labels store, registry,
and the audit queues — never mutates."""
from librarian import store, registry, audit, ledger, contract


def render(cfg):
    rows = store.load(cfg.labels_path)
    reg = (registry.load(cfg.topics_path)
           if cfg.topics_path.exists() else registry.Registry([]))
    rep = audit.report(rows, cfg)
    lines = [f"Library: {len(rows)} articles · canon {len(reg.active_names())} topics"]

    last = ledger.latest(cfg.runs_path)
    if last is None:
        lines.append("Last run: never")
    else:
        i = contract.RUN_COLUMNS.index
        lines.append(
            f"Last run: {last[i('finished_at')]}  "
            f"+{last[i('new')]} new, {last[i('flagged')]} flagged   "
            f"[{last[i('status')]}]")

    lines.append(
        f"Pending: {len(rep['proposals'])} proposed topics · "
        f"{rep['review_open']} needs-review")

    runs = ledger.load(cfg.runs_path)
    if runs:
        i = contract.RUN_COLUMNS.index
        auth = [r for r in runs if r[i('status')] == "auth_failed"]
        last_auth = auth[-1][i('finished_at')] if auth else "never"
        lines.append(
            f"History: {len(runs)} runs since {runs[0][i('started_at')]} "
            f"(last auth_failed: {last_auth})")
    else:
        lines.append("History: 0 runs")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_status.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/status.py librarian/tests/test_status.py
git commit -m "feat(librarian): status renderer (ledger + queues, spec §9)"
```

---

## Task 4: `status` CLI subcommand

**Files:**
- Modify: `librarian/update.py`
- Test: `librarian/tests/test_status.py` (add a CLI smoke test)

Context: expose `status` through the existing `update.py` CLI (the de-facto `librarian` entry point) so `python -m librarian.update status` prints the rendered status.

- [ ] **Step 1: Add a CLI smoke test**

Append to `librarian/tests/test_status.py`:

```python
def test_cmd_status_prints_render(tmp_path, monkeypatch, capsys):
    from librarian import update
    cfg = _cfg(tmp_path)
    _seed_topics(cfg)
    store.merge(cfg.labels_path, [_lrow("Literature/a.md")])
    monkeypatch.setattr(update, "cfg", cfg)
    update.cmd_status()
    out = capsys.readouterr().out
    assert "Library: 1 articles · canon 1 topics" in out
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_status.py::test_cmd_status_prints_render -q`
Expected: FAIL — `module 'librarian.update' has no attribute 'cmd_status'`.

- [ ] **Step 3: Add `cmd_status` + wire the handler in `update.py`**

In `librarian/update.py`, add this function (place it just before the `_opt` helper):

```python
def cmd_status():
    from librarian import status
    print(status.render(cfg))
```

Then in the `if __name__ == "__main__":` block, add `status` to the `handlers` dict — replace:
```python
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib)}
```
with:
```python
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib),
                "status": lambda: cmd_status()}
```

Also update the module docstring at the top of `update.py` — replace:
```python
  python3 -m librarian.update verify
"""
```
with:
```python
  python3 -m librarian.update verify
  python3 -m librarian.update status
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_status.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/update.py librarian/tests/test_status.py
git commit -m "feat(librarian): librarian status CLI subcommand"
```

---

## Task 5: Synthetic end-to-end test

**Files:**
- Create: `librarian/tests/test_e2e.py`

Context (spec §11): drive the whole pipeline against REAL `manifest.build` output — `adapter → ingest_to_inbox → manifest.build → build_wave → (simulated agent JSON) → ingest_wave → materialize → verify` — so the positional `MANIFEST_COLUMNS` coupling (build_wave/ingest_wave read `r[1]`=title, `r[3]`=hash) is verified against actual manifest rows, not hand-built literals. This closes the latent gap flagged in Plans 2–3.

- [ ] **Step 1: Write the end-to-end test**

Create `librarian/tests/test_e2e.py`:

```python
"""Synthetic end-to-end pipeline (spec §11): a handful of plain-markdown nodes
flow adapter -> inbox -> manifest -> build_wave -> ingest_wave -> materialize ->
verify, exercising every seam against real manifest.build output."""
import json

from librarian import config, contract, tsv, manifest, registry, store, update
from librarian.adapters import base, markdown_passthrough as mp
from librarian.orchestrate import build_wave, ingest_wave


def test_end_to_end_adapter_to_verify(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    data = tmp_path / "data"
    data.mkdir()
    cfg = config.Config(
        corpus_path=inbox, library_path=inbox, data_dir=data,
        categories={"Literature"}, label_language="en", hub_min_articles=1)
    monkeypatch.setattr(update, "cfg", cfg)

    # 1. a source directory of plain-markdown nodes (title/source/url + body)
    src = tmp_path / "src"
    src.mkdir()
    for i in range(3):
        (src / f"a{i}.md").write_text(
            f'---\ntitle: "T{i}"\nsource: blog\nurl: "https://x/{i}"\n---\n\nBody {i}.\n',
            encoding="utf-8")

    # 2. adapter normalizes them into the inbox under blog/
    written, rejected, skipped = base.ingest_to_inbox(
        mp.MarkdownPassthroughAdapter("blog"), src, cfg)
    assert len(written) == 3 and not rejected and not skipped

    # 3. manifest from the real inbox
    man = manifest.build(inbox, cfg)
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, man)
    assert {r[0] for r in man} == {"blog/a0.md", "blog/a1.md", "blog/a2.md"}

    # 4. a registry with one active topic
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])
    reg = registry.load(cfg.topics_path)

    # 5. build a wave — selection + per-agent assignment files
    files, canon = build_wave.build(man, [], reg, {}, cfg.wave_assign_dir,
                                    inbox, cfg, wave_no=1)
    assert files and canon == "Lit Crit"

    # 6. simulate the agents' JSON output, keyed by the manifest's real paths
    objs = [{"relative_path": r[0], "primary_category": "Literature",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []} for r in man]
    jp = data / "wave01.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    # 7. ingest the wave — reconstructs rows from FROZEN manifest fields
    summary = ingest_wave.ingest([str(jp)], man, {}, reg, cfg, "2026-06-13",
                                 run_id="r1")
    assert summary["errors"] == [] and summary["merged"] == 3
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert all(row[fsr] == "r1" for row in store.load(cfg.labels_path))
    # frozen title came from the manifest, not the agent JSON
    title_i = contract.LABEL_COLUMNS.index("title")
    assert {row[title_i] for row in store.load(cfg.labels_path)} == {"T0", "T1", "T2"}

    # 8. materialize — files into Literature/, writes topic hubs
    update.cmd_materialize(write=True)
    assert (inbox / "Literature").is_dir()
    assert (inbox / cfg.hub_dir / "Lit Crit.md").exists()

    # 9. verify — closure holds end-to-end
    assert update.verify_problems() == []
```

- [ ] **Step 2: Run it to verify it passes**

Run: `pytest librarian/tests/test_e2e.py -q`
Expected: PASS. (If it fails, that is a real integration defect — STOP and report it, do not weaken the test.)

- [ ] **Step 3: Commit**

```bash
git add librarian/tests/test_e2e.py
git commit -m "test(librarian): synthetic end-to-end pipeline (spec §11)"
```

---

## Task 6: Cleanups — unified mkdir guard + branding sweep

**Files:**
- Modify: `librarian/tsv.py`, `librarian/orchestrate/ingest_wave.py`
- Modify: `librarian/batches.py`, `librarian/config.py`, `librarian/reconcile.py`, `librarian/update.py`
- Test: `librarian/tests/test_tsv.py`

Context: every TSV writer currently assumes its parent dir exists; `ingest_wave` added an ad-hoc `cfg.labels_path.parent.mkdir`. Hoist the guard into `tsv.write_rows` so all writers (labels, topics, manifest, runs, progress) are uniformly safe, then drop the ad-hoc one. Also sweep the stale "MyBooks"/"mybooks" branding now that this is the `knowledge-library` package.

- [ ] **Step 1: Write the failing test**

Append to `librarian/tests/test_tsv.py`:

```python
def test_write_rows_creates_missing_parent_dir(tmp_path):
    from librarian import tsv
    target = tmp_path / "nested" / "deeper" / "out.tsv"   # parents do not exist
    tsv.write_rows(target, ["a", "b"], [["1", "2"]])
    _header, rows = tsv.read_rows(target, ["a", "b"])
    assert rows == [["1", "2"]]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest librarian/tests/test_tsv.py::test_write_rows_creates_missing_parent_dir -q`
Expected: FAIL — `FileNotFoundError` (the tmp file write into a non-existent dir).

- [ ] **Step 3: Hoist the mkdir into `tsv.write_rows`**

In `librarian/tsv.py`, in `write_rows`, add a `mkdir` immediately before the temp-file write. Replace:
```python
    out = ["\t".join(header)] + ["\t".join(r) for r in rows]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
```
with:
```python
    out = ["\t".join(header)] + ["\t".join(r) for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)
```

- [ ] **Step 4: Drop the now-redundant guard in `ingest_wave.py`**

In `librarian/orchestrate/ingest_wave.py`, remove the now-redundant line (the `store.merge` call below it writes via `tsv.write_rows`, which now creates the dir). Replace:
```python
    cfg.labels_path.parent.mkdir(parents=True, exist_ok=True)
    store.merge(cfg.labels_path, rows)
```
with:
```python
    store.merge(cfg.labels_path, rows)
```

- [ ] **Step 5: Branding sweep**

In `librarian/batches.py`, replace:
```python
        lines = [f"# MyBooks Labeling Batch {n:03d} / {len(chunks)}\n",
```
with:
```python
        lines = [f"# knowledge-library Labeling Batch {n:03d} / {len(chunks)}\n",
```

In `librarian/config.py`, replace the docstring line:
```python
that mybooks/schema.py used to hardcode. The fixed data contract lives in
```
with:
```python
that MyBooks' schema.py used to hardcode. The fixed data contract lives in
```

In `librarian/reconcile.py`, replace:
```python
mybooks.update --out <v2> flow describe v2 directly, each label's relative_path
```
with:
```python
the update --out <v2> flow describe v2 directly, each label's relative_path
```

In `librarian/update.py`, replace:
```python
    Returns {} if the file is missing. v1 schema differs from mybooks, so this
```
with:
```python
    Returns {} if the file is missing. v1 schema differs from the v2 contract, so this
```

- [ ] **Step 6: Run the FULL suite**

Run: `pytest -q`
Expected: PASS — all green (the branding edits are comment/string-only; `test_batches` asserts `## Item` / `source_path` / `v1_reference`, not the batch header, so it is unaffected).

- [ ] **Step 7: Commit**

```bash
git add librarian/tsv.py librarian/orchestrate/ingest_wave.py librarian/batches.py librarian/config.py librarian/reconcile.py librarian/update.py librarian/tests/test_tsv.py
git commit -m "refactor(librarian): unify tsv parent-dir guard + branding sweep"
```

---

## Self-Review (run after all tasks)

**1. Spec coverage (spec §9 state & run tracking + §11 testing + carried cleanups):**
- §9 run ledger (`data/runs.tsv`, append-only, schema `run_id…status`) → `ledger.py` + `contract.RUN_COLUMNS`/`RUN_STATUS` + `cfg.runs_path` (Task 2). Schema extended with `lang` per the Plan 3 carry-forward. ✓
- §9 provenance `first_seen_run` on the label schema → `LABEL_COLUMNS` append + `ingest_wave` stamp (Task 1). ✓
- §9 `librarian status` command (library/canon size, last run, pending queues, history) → `status.render` (Task 3) + CLI (Task 4). ✓
- §7 digest "N new · M proposed · K flagged" rendered from the latest ledger row → `ledger.digest` (Task 2). ✓
- §11 synthetic end-to-end fixture through materialize + verify → `test_e2e.py` (Task 5). ✓
- Cleanups (data_dir mkdir guard unification; MyBooks→knowledge-library branding) → Task 6. ✓
- **Out of scope, correctly deferred:** the steady-state `update-library` run-WRITER (§7 — Plan 5; this plan ships the ledger primitive + reader, not the per-run writer); `orchestrate/materialize.py` extraction (§3); skill packaging/scheduling (Plan 5). The ledger therefore starts empty in normal use until steady-state writes to it; `status` handles that ("Last run: never"). ✓

**2. Placeholder scan:** every step has literal code or an exact old→new edit; every command step has an exact `pytest` invocation + expected result. No "TBD"/"handle errors". The E2E test (Task 5 Step 2) explicitly says STOP-and-report on failure rather than weaken the test.

**3. Type/signature consistency across tasks:**
- `contract.LABEL_COLUMNS` (now 16, `first_seen_run` last) — Task 1; consumed by `ingest_wave._row`, the E2E test's `LABEL_COLUMNS.index("first_seen_run")` (Task 5), and `status`'s `audit.report` (positional `r[3]/r[4]/r[9]/r[11]` unchanged). ✓
- `ingest_wave.ingest(json_paths, manifest_rows, legacy, reg, cfg, today, run_id="")` and `_row(j, frozen, cfg, today, run_id)` — Task 1; called by the E2E test (Task 5) with `run_id="r1"`. ✓
- `contract.RUN_COLUMNS` (11 cols incl. `lang`) + `RUN_STATUS` — Task 2; consumed by `ledger` (Task 2) and `status` via `RUN_COLUMNS.index(...)` (Task 3). ✓
- `ledger.load/append/latest/digest(path|row)` — Task 2; `status.render` uses `ledger.latest`/`ledger.load` (Task 3); `test_status` seeds via `ledger.append` (Task 3). ✓
- `cfg.runs_path` — Task 2; used by `ledger`/`status`. ✓
- `status.render(cfg) -> str` — Task 3; called by `update.cmd_status` (Task 4). ✓
- `tsv.write_rows` now mkdirs parent — Task 6; relied on implicitly by `ledger.append` (Task 2) and everywhere. **Ordering caught in review:** Task 2's `ledger.append` writes via `tsv.write_rows`, but Task 6 (the parent-dir guard) runs later — so Task 2's `test_ledger._cfg` creates `data_dir` itself (applied in Task 2 Step 1), keeping Task 2 green independently. `test_status._cfg` already creates `data_dir`; `test_e2e` creates `data` explicitly. ✓

---

## Execution note

Plan 4 is additive. The one behaviour-visible change is the 16th `LABEL_COLUMNS` entry (`first_seen_run`); because the corpus is fresh (no legacy TSV to migrate) and the column is appended last, the blast radius is three width-checked fixtures plus `ingest_wave`. The completion signal is a green full suite (Task 1 Step 7, Task 5 Step 2, Task 6 Step 6). The new E2E test is the durable guard for the positional manifest-column coupling that Plans 2–3 left unverified. Steady-state (the run-WRITER that populates `runs.tsv` and supplies real `run_id`s, §7) and the `orchestrate/materialize.py` extraction (§3) build directly on these primitives in Plan 5.
