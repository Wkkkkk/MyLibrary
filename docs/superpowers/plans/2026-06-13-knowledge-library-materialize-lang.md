# Knowledge-Library Materialize Localization Implementation Plan (Plan 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make materialize language-aware — render the English-canonical library into a target display language at materialize time via `--lang en|zh`, localizing category folders, topic hub-note filenames + links, and hub section headers, with `verify`'s invariants comparing against the localized names.

**Architecture:** The controlled vocabulary stays English-canonical in the TSVs (spec §4b layer 1). Display rendering is a per-run choice threaded as a `lang` parameter (default `"en"`, which renders the canon verbatim with zero lookup) through the leaf modules `refile` (folder = localized category), `hubgen` (filename/heading/links = localized topic via the registry's `name_zh` column; section headers per-lang), and `verify` (folder-matches-primary + hub-name invariants compare against the localized form, spec §8). A new `librarian/localize.py` holds the per-language section-header strings and the topic-name localizer; category localization reuses the existing `cfg.localize_category` (Plan 1). `update.py`'s `cmd_materialize`/`verify` gain a `--lang` flag and thread it down. Article frontmatter is NOT localized (it stores the canon; spec §4b scopes display localization to folders/hub-filenames/section-headers).

**Tech Stack:** Python 3, stdlib only (`re`, `json`, `unicodedata`, `os`, `collections`) + existing `librarian` modules. Tests: `pytest`, run from `knowledge-library/`.

**Scope (Plan 3 = "language feature only", per user decision):** `localize.py` + lang-awareness in `refile`/`hubgen`/`verify` + `--lang` threading in `update.py` + the labeling-prompt canon-language refinement. **Non-goals (deferred):** extracting materialize into `orchestrate/materialize.py` (spec §3 architecture — its own later cleanup plan); steady-state/run-ledger (Plan 4); skill packaging/scheduling (Plan 5); localizing article frontmatter (out of §4b scope by design).

**Working directory for all commands:** `/Users/kunwu/Workspace/MyLibrary/knowledge-library`
**Run tests with:** `pytest -q` (the `conftest.py` there puts `librarian` on `sys.path`; bare `python`/`python3` is 3.14 without pytest — use the `pytest` command).

---

## File Structure

| File | Responsibility |
|---|---|
| `librarian/localize.py` *(create)* | Per-language section-header strings (`headers(lang)`) + topic-name localizer (`topic_name(cfg, reg, name, lang)` via the registry `name_zh` column). |
| `librarian/refile.py` *(modify)* | `plan(label_rows, vault, cfg, lang="en")` — destination folder = `cfg.localize_category(primary, lang)`. |
| `librarian/hubgen.py` *(modify)* | `plan(label_rows, reg, vault, cfg, lang="en")` — hub filename/heading/parent/child/related links localized; section headers via `localize.headers`. |
| `librarian/verify.py` *(modify)* | `run(..., lang="en")` — folder-matches-primary and hub-name/expected-set invariants compare against the localized forms (spec §8). |
| `librarian/update.py` *(modify)* | `cmd_materialize`/`_materialize_to_library`/`verify_problems`/`cmd_verify` take `lang`; CLI parses `--lang`; thread to refile/hubgen/verify. |
| `librarian/orchestrate/build_wave.py` *(modify)* | `_agent_file` names the canon language explicitly in the labeling instruction (spec §4b labeling rule). |
| `librarian/tests/test_localize.py` *(create)* | headers + topic_name behaviour. |
| `librarian/tests/test_refile.py` *(modify)* | pass `cfg`; add a `--lang zh` folder-localization test. |
| `librarian/tests/test_hubgen.py` *(modify)* | update default-`en` header assertions to English; add a `--lang zh` test. |
| `librarian/tests/test_verify.py` *(modify)* | add a `--lang zh` localized-invariant test (existing tests stay green under default `en`). |
| `librarian/tests/test_update_materialize.py` *(modify)* | add a `cmd_materialize(write=True, lang="zh")` end-to-end test. |
| `librarian/tests/test_build_wave.py` *(modify)* | assert the assignment names the canon language. |

---

## Task 1: Localization helpers — `librarian/localize.py`

**Files:**
- Create: `librarian/localize.py`
- Test: `librarian/tests/test_localize.py`

- [ ] **Step 1: Write the failing test**

Create `librarian/tests/test_localize.py`:

```python
from librarian import localize, config, registry, tsv, contract


def _cfg(tmp_path, localization=None):
    return config.Config(
        corpus_path=tmp_path / "v", library_path=tmp_path / "v",
        data_dir=tmp_path / "d", categories={"Literature"},
        label_language="en", category_localization=localization or {})


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Machine Learning", "", "", "active", "", "", "机器学习"],
                    ["T2", "Robotics", "", "", "active", "", "", ""]])  # no name_zh
    return registry.load(p)


def test_headers_en_are_english():
    h = localize.headers("en")
    assert h["reading_list"] == "Reading list"
    assert h["related"] == "Related topics"
    assert h["parent"] == "Parent topic"
    assert h["children"] == "Subtopics"


def test_headers_zh_are_chinese():
    h = localize.headers("zh")
    assert h["reading_list"] == "阅读清单"
    assert h["related"] == "相关话题"
    assert h["parent"] == "父话题"
    assert h["children"] == "子话题"


def test_headers_unknown_lang_falls_back_to_english():
    assert localize.headers("fr") == localize.headers("en")


def test_topic_name_canon_lang_returns_verbatim(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Machine Learning", "en") == "Machine Learning"


def test_topic_name_zh_uses_name_zh_column(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Machine Learning", "zh") == "机器学习"


def test_topic_name_zh_falls_back_to_canon_when_no_name_zh(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Robotics", "zh") == "Robotics"


def test_topic_name_unknown_topic_returns_input(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Nonexistent", "zh") == "Nonexistent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_localize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarian.localize'`

- [ ] **Step 3: Write the implementation**

Create `librarian/localize.py`:

```python
"""Display localization for materialize (spec §4b layer 2). The controlled
vocabulary is English-canonical in the TSVs; these helpers render it into a
target display language at materialize time. Category display names come from
cfg.localize_category (Plan 1); topic display names come from the registry's
name_zh column; section headers are fixed per-language strings here."""

# Hub-note section headers per display language. `en` is the no-lookup default
# (the canon language); `zh` is the worked example (spec §4b keeps it to zh for
# now — YAGNI). Unknown languages fall back to English.
SECTION_HEADERS = {
    "en": {"reading_list": "Reading list", "related": "Related topics",
           "parent": "Parent topic", "children": "Subtopics"},
    "zh": {"reading_list": "阅读清单", "related": "相关话题",
           "parent": "父话题", "children": "子话题"},
}


def headers(lang):
    """The section-header strings for `lang`, falling back to English."""
    return SECTION_HEADERS.get(lang, SECTION_HEADERS["en"])


def topic_name(cfg, reg, name, lang):
    """The display name for a canonical topic in `lang`. Returns the canonical
    name unchanged when lang is the canon language, the topic is unknown, or it
    has no name_zh; otherwise the registry's name_zh value (TOPIC_COLUMNS[7])."""
    if lang == cfg.label_language:
        return name
    row = reg.by_name.get(name)
    if row is not None and len(row) > 7 and row[7]:
        return row[7]
    return name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_localize.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/localize.py librarian/tests/test_localize.py
git commit -m "feat(librarian): localize helpers — section headers + topic name_zh"
```

---

## Task 2: Language-aware refile (folder = localized category)

**Files:**
- Modify: `librarian/refile.py`
- Test: `librarian/tests/test_refile.py`

Context: `refile.plan` currently builds destination folders from the raw `r[3]` (primary_category). Under `--lang zh` the folder must be `cfg.localize_category(r[3], lang)`. The function gains `cfg` and `lang` parameters. The existing tests call `refile.plan(rows, tmp_path)` with Chinese strings as the canonical categories and no localization configured, so they must pass a `cfg` (Chinese categories, default `en`) and continue to behave identically (verbatim folders).

- [ ] **Step 1: Update existing tests to pass `cfg`, and add a localization test**

Edit `librarian/tests/test_refile.py`. Replace the entire file with:

```python
from librarian import refile, config


def _cfg(tmp_path, categories, localization=None):
    return config.Config(
        corpus_path=tmp_path, library_path=tmp_path, data_dir=tmp_path / "d",
        categories=set(categories), label_language="en",
        category_localization=localization or {})


def lrow(rel, primary):
    return [rel, "", "", primary, "t", *[""] * 10]


def make(vault, rel):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_swap_between_folders(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "历史"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path, cfg)
    log = refile.apply(moves, tmp_path)
    assert (tmp_path / "历史" / "a.md").exists() and (tmp_path / "文学" / "a.md").exists()
    assert rows[0][0] == "历史/a.md" and rows[1][0] == "文学/a.md"
    assert len(log) == 2


def test_collision_gets_suffix(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "文学"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path, cfg)
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").exists()
    assert (tmp_path / "文学" / "a_2.md").exists()


def test_in_place_no_move(tmp_path):
    cfg = _cfg(tmp_path, ["文学"])
    make(tmp_path, "文学/a.md")
    rows = [lrow("文学/a.md", "文学")]
    assert refile.plan(rows, tmp_path, cfg) == []


def test_collision_with_preexisting_offset_file(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    # 文学/a_2.md already on disk but NOT in the label set
    make(tmp_path, "历史/a.md"); make(tmp_path, "文学/a.md"); make(tmp_path, "文学/a_2.md")
    rows = [lrow("历史/a.md", "文学")]   # only this one is re-filed, into 文学
    moves = refile.plan(rows, tmp_path, cfg)
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_2.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_3.md").exists()
    assert rows[0][0] == "文学/a_3.md"


def test_resolve_name_matches_across_normalization_forms():
    import unicodedata
    nfc = unicodedata.normalize("NFC", "café.md")
    nfd = unicodedata.normalize("NFD", "café.md")
    assert nfc != nfd
    assert refile._resolve_name(nfc, [nfd, "other.md"]) == nfd
    assert refile._resolve_name(nfd, [nfc, "other.md"]) == nfc
    assert refile._resolve_name(nfc, ["other.md"]) is None


def test_lang_zh_files_into_localized_folder(tmp_path):
    # canonical category "Literature" localizes to 文学 under --lang zh
    cfg = _cfg(tmp_path, ["Literature"], {"Literature": {"zh": "文学"}})
    make(tmp_path, "inbox/a.md")
    rows = [lrow("inbox/a.md", "Literature")]
    moves = refile.plan(rows, tmp_path, cfg, lang="zh")
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").exists()       # localized folder
    assert not (tmp_path / "Literature").exists()       # NOT the canonical name
    assert rows[0][0] == "文学/a.md"


def test_lang_en_files_into_canonical_folder(tmp_path):
    cfg = _cfg(tmp_path, ["Literature"], {"Literature": {"zh": "文学"}})
    make(tmp_path, "inbox/a.md")
    rows = [lrow("inbox/a.md", "Literature")]
    moves = refile.plan(rows, tmp_path, cfg, lang="en")
    refile.apply(moves, tmp_path)
    assert (tmp_path / "Literature" / "a.md").exists()   # verbatim canon
    assert rows[0][0] == "Literature/a.md"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest librarian/tests/test_refile.py -q`
Expected: FAIL — `TypeError: plan() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Make `refile.plan` language-aware**

In `librarian/refile.py`, replace the `plan` function (the `apply` and `_resolve_name` functions are unchanged) with:

```python
def plan(label_rows, vault, cfg, lang="en"):
    def folder_of(r):
        return cfg.localize_category(r[3], lang)
    taken = set()
    for r in label_rows:  # pass 1: in-place rows claim their names first
        base = r[0].rsplit("/", 1)[-1]
        if r[0] == f"{folder_of(r)}/{base}":
            taken.add(r[0])
    # seed `taken` with the actual on-disk contents of every target folder so a
    # pre-existing file NOT in label_rows can never be clobbered by a mover.
    # A mover's own source file vacates its slot, so it must not block itself:
    # exclude every row's current path (NFC) from the seeded set.
    own = {unicodedata.normalize("NFC", r[0]) for r in label_rows}
    for category in {folder_of(r) for r in label_rows}:
        folder = vault / category
        if folder.exists():
            for entry in os.listdir(folder):
                rel = f"{category}/{unicodedata.normalize('NFC', entry)}"
                if rel not in own:
                    taken.add(rel)
    moves = []
    for r in label_rows:
        base = r[0].rsplit("/", 1)[-1]
        stem, ext = os.path.splitext(base)
        new_rel = f"{folder_of(r)}/{base}"
        if r[0] == new_rel:
            continue
        n = 2
        while new_rel in taken:
            new_rel = f"{folder_of(r)}/{stem}_{n}{ext}"
            n += 1
        taken.add(new_rel)
        moves.append((r[0], new_rel, r))
    return moves
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_refile.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Run the update-materialize suite to catch the caller (expected to fail; fixed in Task 5)**

Run: `pytest librarian/tests/test_update_materialize.py -q`
Expected: FAIL — `update.cmd_materialize` still calls `refile.plan(rows, cfg.corpus_path)` (2 args). This is expected; Task 5 updates the caller. **Do not fix update.py in this task** — commit refile + its tests now.

- [ ] **Step 6: Commit**

```bash
git add librarian/refile.py librarian/tests/test_refile.py
git commit -m "feat(librarian): refile files into the localized category folder"
```

---

## Task 3: Language-aware hubgen (filename/links/headers)

**Files:**
- Modify: `librarian/hubgen.py`
- Test: `librarian/tests/test_hubgen.py`

Context: `hubgen.plan` currently hard-codes Chinese section headers (`阅读清单`, `相关话题`, `父话题`, `子话题`). It gains a `lang` parameter: the hub filename, the `# heading`, and the parent/child/related `[[wikilinks]]` use the localized topic name (`localize.topic_name`); the section headers come from `localize.headers(lang)`. Under the default `lang="en"` the headers become English (a change from the ported Chinese) and topic names render verbatim. The reading-list `[[basename]]` links are article filenames and are NOT localized.

- [ ] **Step 1: Update default-`en` header assertions and add a `zh` test**

Edit `librarian/tests/test_hubgen.py`. In `test_hub_content`, change the two header/link assertions:

Replace:
```python
    assert "父话题: [[文学理论]]" in text
    assert "## 相关话题" in text and "[[文学理论]] (1)" in text
```
with:
```python
    assert "Parent topic: [[文学理论]]" in text
    assert "## Related topics" in text and "[[文学理论]] (1)" in text
    assert "## Reading list" in text
```

Then append this new test to the end of the file:

```python
def test_lang_zh_localizes_filename_links_and_headers(tmp_path, cfg):
    import dataclasses
    vault = tmp_path / "vault"; vault.mkdir()
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "Lit Theory", "active", "desc", "", "文学评论"],
                    ["T2", "Lit Theory", "", "", "active", "", "", "文学理论"]])
    reg_zh = registry.load(p)
    labels = [lrow("X/a.md", "Lit Crit"), lrow("X/b.md", "Lit Crit; Lit Theory"),
              lrow("X/c.md", "Lit Crit")]
    cfg3 = dataclasses.replace(cfg, hub_min_articles=3, label_language="en")
    plans = hubgen.plan(labels, reg_zh, vault, cfg3, lang="zh")
    by_name = {pp.name: text for pp, text in plans}
    assert "文学评论.md" in by_name            # filename localized via name_zh
    text = by_name["文学评论.md"]
    assert "# 文学评论" in text                 # heading localized
    assert "父话题: [[文学理论]]" in text        # parent header + link localized
    assert "## 阅读清单 (3)" in text            # section header in zh
    assert "## 相关话题" in text                # related header in zh
    assert "[[文学理论]] (1)" in text           # related link localized
    assert "[[a]]" in text                      # article basenames NOT localized
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest librarian/tests/test_hubgen.py -q`
Expected: FAIL — `test_hub_content` fails on the new English assertions, and `test_lang_zh_localizes_filename_links_and_headers` fails (`plan()` has no `lang` parameter / headers still Chinese).

- [ ] **Step 3: Make `hubgen.plan` language-aware**

In `librarian/hubgen.py`, update the imports and the `plan` function (the `apply` function is unchanged).

Change the import line:
```python
from librarian import tsv, cooccur
```
to:
```python
from librarian import tsv, cooccur, localize
```

Replace the `plan` function with:

```python
def plan(label_rows, reg, vault, cfg, lang="en"):
    def disp(name):
        return localize.topic_name(cfg, reg, name, lang)
    h = localize.headers(lang)
    by_topic = defaultdict(list)
    for r in label_rows:
        for t in tsv.split_multi(r[4]):
            by_topic[t].append(r)
    w = cooccur.weights(label_rows)
    children = defaultdict(list)
    for row in reg.rows:
        if row[3]:
            children[row[3]].append(row[1])
    plans = []
    for topic in sorted(by_topic):
        arts = by_topic[topic]
        if len(arts) < cfg.hub_min_articles or topic not in reg.active_names():
            continue
        row = reg.by_name[topic]
        parent, desc = row[3], row[5]
        lines = ["---", cfg.generated_marker, f"articles: {len(arts)}"]
        aliases = tsv.split_multi(row[2])
        if aliases:
            joined = ", ".join(json.dumps(a, ensure_ascii=False) for a in aliases)
            lines.append(f"aliases: [{joined}]")
        lines += ["---", "", f"# {disp(topic)}", ""]
        if desc:
            lines += [desc, ""]
        if parent:
            lines += [f"{h['parent']}: [[{disp(parent)}]]", ""]
        if children.get(topic):
            lines += [f"{h['children']}: " +
                      " · ".join(f"[[{disp(c)}]]" for c in sorted(children[topic])), ""]
        lines += [f"## {h['reading_list']} ({len(arts)})", ""]
        for r in sorted(arts, key=lambda r: r[0]):
            note = r[0].rsplit("/", 1)[-1][:-3]
            lines.append(f"- [[{note}]] — {r[7]}")
        rel = cooccur.related(w, topic, k=8)
        if rel:
            lines += ["", f"## {h['related']}", ""]
            lines.append(" · ".join(f"[[{disp(t)}]] ({n})" for t, n in rel))
        plans.append((vault / cfg.hub_dir / f"{disp(topic)}.md", "\n".join(lines) + "\n"))
    return plans
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_hubgen.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add librarian/hubgen.py librarian/tests/test_hubgen.py
git commit -m "feat(librarian): hubgen localizes filenames, links, and section headers"
```

---

## Task 4: Language-aware verify (localized invariants)

**Files:**
- Modify: `librarian/verify.py`
- Test: `librarian/tests/test_verify.py`

Context (spec §8): `verify`'s "folder matches primary_category" check must compare the on-disk folder against `localize(primary_category, lang)`, and the hub-note invariants (expected hub set + per-article topic match) must use the localized topic names so a `--lang zh` vault with `文学/` folders and `机器学习.md` hubs verifies clean. `verify.run` gains `lang="en"`. Under the default `en`, every localized form equals the canonical form, so the existing tests stay green.

- [ ] **Step 1: Add a `--lang zh` verify test**

Append to `librarian/tests/test_verify.py`:

```python
def test_lang_zh_localized_vault_verifies_clean(tmp_path):
    import dataclasses
    from librarian import config
    cfg = config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "d", categories={"Literature"},
        label_language="en", category_localization={"Literature": {"zh": "文学"}},
        hub_min_articles=1)
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    reg_zh = registry.load(p)
    # on disk: localized folder 文学/, localized hub 文学评论.md
    v = make_vault(tmp_path, ["文学/a.md"])
    write_hub(v, "文学评论",
              f"---\n{cfg.generated_marker}\narticles: 1\n---\n\n"
              f"# 文学评论\n\n## 阅读清单 (1)\n\n- [[a]] — s\n", cfg)
    # label row: canonical primary Literature + canonical topic Lit Crit
    row = [v_rel for v_rel in ["文学/a.md"]]  # placeholder, replaced below
    lr = ["文学/a.md", "", "", "Literature", "Lit Crit", "", "", "s",
          "high", "false", "", "", "h" * 16, "v1", "d"]
    problems = verify.run([lr], reg_zh, v, {"Literature"}, cfg, lang="zh")
    assert problems == [], problems


def test_lang_zh_wrong_localized_folder_flagged(tmp_path):
    from librarian import config
    cfg = config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "d", categories={"Literature", "History"},
        label_language="en",
        category_localization={"Literature": {"zh": "文学"}, "History": {"zh": "历史"}},
        hub_min_articles=1)
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    reg_zh = registry.load(p)
    v = make_vault(tmp_path, ["历史/a.md"])   # filed under 历史 ...
    lr = ["历史/a.md", "", "", "Literature", "Lit Crit", "", "", "s",   # ... but primary is Literature->文学
          "high", "false", "", "", "h" * 16, "v1", "d"]
    problems = verify.run([lr], reg_zh, v, {"Literature", "History"}, cfg, lang="zh")
    assert any("folder" in p for p in problems)
```

Remove the stray placeholder line `row = [v_rel for v_rel in ["文学/a.md"]]  # placeholder, replaced below` — it is dead. (It is included above only to flag that the real row is `lr`; delete the `row = ...` line when transcribing.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest librarian/tests/test_verify.py -q`
Expected: FAIL — `run()` got an unexpected keyword argument `lang`.

- [ ] **Step 3: Make `verify.run` language-aware**

In `librarian/verify.py`, update the import and the `run` function.

Change the import:
```python
from librarian import tsv, contract
```
to:
```python
from librarian import tsv, contract, localize
```

Change the signature:
```python
def run(label_rows, reg, vault, categories, cfg, manifest_rows=None):
```
to:
```python
def run(label_rows, reg, vault, categories, cfg, manifest_rows=None, lang="en"):
```

Change the folder-matches-primary check. Replace:
```python
        if rel.split("/")[0] != r[3]:
            problems.append(f"{rel}: folder != primary {r[3]!r}")
```
with:
```python
        if rel.split("/")[0] != _nfc(cfg.localize_category(r[3], lang)):
            problems.append(f"{rel}: folder != primary {r[3]!r}")
```

Then localize the hub-note invariants. Replace this block:
```python
        counts = {}
        topics_by_article = []
        for r in label_rows:
            ts = tsv.split_multi(r[4])
            topics_by_article.append((r, ts))
            for t in ts:
                counts[_nfc(t)] = counts.get(_nfc(t), 0) + 1
        active_nfc = {_nfc(n) for n in active}
        expected = {t for t, c in counts.items()
                    if c >= cfg.hub_min_articles and t in active_nfc}
        for f in sorted(hub_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if cfg.generated_marker not in text:
                continue
            stem = _nfc(f.stem)
            if stem not in expected:
                problems.append(
                    f"orphaned hub note (topic not active/below threshold): {stem}")
                continue
            # INVARIANT C: reading-list matches the TSV
            links = {_nfc(m) for m in
                     re.findall(r'^- \[\[(.+)\]\](?= —|$)', text, re.M)}
            exp_basenames = set()
            for r, ts in topics_by_article:
                if stem in {_nfc(t) for t in ts}:
                    base = r[0].rsplit("/", 1)[-1]
                    if base.endswith(".md"):
                        base = base[:-3]
                    exp_basenames.add(_nfc(base))
            if links != exp_basenames:
                extra = links - exp_basenames
                missing = exp_basenames - links
                problems.append(
                    f"hub list mismatch for {stem}: "
                    f"+{sorted(extra)} -{sorted(missing)}")
```
with (the only changes: count/active/match keys are localized topic display names, so on-disk localized hub stems line up):
```python
        def _disp(t):
            return _nfc(localize.topic_name(cfg, reg, t, lang))
        counts = {}
        topics_by_article = []
        for r in label_rows:
            ts = tsv.split_multi(r[4])
            topics_by_article.append((r, ts))
            for t in ts:
                counts[_disp(t)] = counts.get(_disp(t), 0) + 1
        active_disp = {_disp(n) for n in active}
        expected = {t for t, c in counts.items()
                    if c >= cfg.hub_min_articles and t in active_disp}
        for f in sorted(hub_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if cfg.generated_marker not in text:
                continue
            stem = _nfc(f.stem)
            if stem not in expected:
                problems.append(
                    f"orphaned hub note (topic not active/below threshold): {stem}")
                continue
            # INVARIANT C: reading-list matches the TSV
            links = {_nfc(m) for m in
                     re.findall(r'^- \[\[(.+)\]\](?= —|$)', text, re.M)}
            exp_basenames = set()
            for r, ts in topics_by_article:
                if stem in {_disp(t) for t in ts}:
                    base = r[0].rsplit("/", 1)[-1]
                    if base.endswith(".md"):
                        base = base[:-3]
                    exp_basenames.add(_nfc(base))
            if links != exp_basenames:
                extra = links - exp_basenames
                missing = exp_basenames - links
                problems.append(
                    f"hub list mismatch for {stem}: "
                    f"+{sorted(extra)} -{sorted(missing)}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_verify.py -q`
Expected: PASS (existing tests + 2 new). Under default `en`, `_disp(t) == _nfc(t)` and `localize_category(c, "en") == c`, so the existing assertions are unaffected.

- [ ] **Step 5: Commit**

```bash
git add librarian/verify.py librarian/tests/test_verify.py
git commit -m "feat(librarian): verify invariants compare against localized names"
```

---

## Task 5: Thread `--lang` through `update.py` materialize/verify

**Files:**
- Modify: `librarian/update.py`
- Test: `librarian/tests/test_update_materialize.py`

Context: `update.cmd_materialize`, `_materialize_to_library`, `verify_problems`, and `cmd_verify` must accept a `lang` (default `"en"`) and thread it to `refile.plan` / `hubgen.plan` / `verify.run`. The `_materialize_to_library` destination folder must be the localized category. The CLI parses `--lang` (default `"en"`). This task also fixes the `refile.plan(rows, cfg.corpus_path)` call broken in Task 2.

- [ ] **Step 1: Add a `--lang zh` end-to-end materialize test**

Append to `librarian/tests/test_update_materialize.py`:

```python
def test_materialize_lang_zh_files_into_localized_folder_and_hub(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    data.mkdir()
    c = config.Config(
        corpus_path=vault, library_path=vault, data_dir=data,
        categories={"Literature"}, label_language="en",
        category_localization={"Literature": {"zh": "文学"}}, hub_min_articles=1)
    monkeypatch.setattr(update, "cfg", c)
    # one article, canonical primary "Literature", one active topic with name_zh
    _article(vault, "inbox/a.md", "Literature")
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    row = _lrow("inbox/a.md", "Literature")
    row[4] = "Lit Crit"           # topics
    row[7] = "s"                  # summary
    row[8], row[9] = "high", "false"
    tsv.write_rows(c.labels_path, contract.LABEL_COLUMNS, [row])
    tsv.write_rows(c.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(vault, c))

    update.cmd_materialize(write=True, lang="zh")

    # article filed into the localized folder
    assert (vault / "文学" / "a.md").exists()
    assert not (vault / "Literature").exists()
    # hub note named + headed in zh
    hub = vault / c.hub_dir / "文学评论.md"
    assert hub.exists()
    assert "## 阅读清单 (1)" in hub.read_text(encoding="utf-8")
    # verify the localized vault is clean under the same lang
    assert update.verify_problems(lang="zh") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_update_materialize.py -q`
Expected: FAIL — both the new test and the pre-existing tests fail (the latter because `cmd_materialize` still calls `refile.plan` with 2 args after Task 2). All are fixed in Step 3.

- [ ] **Step 3: Thread `lang` through `update.py`**

In `librarian/update.py`, make the following edits.

**(a)** `cmd_materialize` — change the signature and thread `lang`. Replace:
```python
def cmd_materialize(write=False, out=None):
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if out is not None and out != cfg.corpus_path:
        return _materialize_to_library(rows, reg, out, write)
    moves = refile.plan(rows, cfg.corpus_path)
    plans = hubgen.plan(rows, reg, cfg.corpus_path, cfg)
```
with:
```python
def cmd_materialize(write=False, out=None, lang="en"):
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if out is not None and out != cfg.corpus_path:
        return _materialize_to_library(rows, reg, out, write, lang)
    moves = refile.plan(rows, cfg.corpus_path, cfg, lang)
    plans = hubgen.plan(rows, reg, cfg.corpus_path, cfg, lang)
```

**(b)** `_materialize_to_library` — change the signature, localize the destination folder, and thread `lang` to `hubgen.plan` (both call sites). Replace:
```python
def _materialize_to_library(rows, reg, library, write):
```
with:
```python
def _materialize_to_library(rows, reg, library, write, lang="en"):
```
Then, inside it, replace the dry-run `hubgen.plan` call:
```python
    if not write:
        plans = hubgen.plan(rows, reg, library, cfg)
        print(f"would copy {len(rows)} files into {library}, write {len(plans)} hub notes")
        print("dry run; pass --write")
        return
```
with:
```python
    if not write:
        plans = hubgen.plan(rows, reg, library, cfg, lang)
        print(f"would copy {len(rows)} files into {library}, write {len(plans)} hub notes")
        print("dry run; pass --write")
        return
```
Then replace the `_free_dest` destination call:
```python
            dst_rel = _free_dest(library, r[3], r[0].rsplit("/", 1)[-1],
                                 manifest.read_url(src), taken)
```
with:
```python
            dst_rel = _free_dest(library, cfg.localize_category(r[3], lang),
                                 r[0].rsplit("/", 1)[-1],
                                 manifest.read_url(src), taken)
```
Then replace the post-copy `hubgen.plan` call:
```python
    plans = hubgen.plan(rows, reg, library, cfg)  # plan against the final paths
```
with:
```python
    plans = hubgen.plan(rows, reg, library, cfg, lang)  # plan against the final paths
```

**(c)** `verify_problems` — thread `lang`. Replace:
```python
def verify_problems(library=None):
    """Run the invariant checks against the library (defaults to cfg.corpus_path for
    the legacy single-vault mode). Returns the list of problems."""
    vault = library if library is not None else cfg.corpus_path
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if cfg.manifest_path.exists():
        return verify.run(rows, reg, vault, cfg.categories, cfg,
                          manifest_rows=_manifest_rows())
    return verify.run(rows, reg, vault, cfg.categories, cfg)
```
with:
```python
def verify_problems(library=None, lang="en"):
    """Run the invariant checks against the library (defaults to cfg.corpus_path for
    the legacy single-vault mode). Returns the list of problems."""
    vault = library if library is not None else cfg.corpus_path
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if cfg.manifest_path.exists():
        return verify.run(rows, reg, vault, cfg.categories, cfg,
                          manifest_rows=_manifest_rows(), lang=lang)
    return verify.run(rows, reg, vault, cfg.categories, cfg, lang=lang)
```

**(d)** `cmd_verify` — thread `lang`. Replace:
```python
def cmd_verify(library=None):
    problems = verify_problems(library=library)
```
with:
```python
def cmd_verify(library=None, lang="en"):
    problems = verify_problems(library=library, lang=lang)
```

**(e)** CLI `__main__` — parse `--lang` and pass it to the materialize/verify handlers. Replace:
```python
    out = _opt("--out")
    lib = Path(out).expanduser() if out else None
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib)}
```
with:
```python
    out = _opt("--out")
    lib = Path(out).expanduser() if out else None
    lang = _opt("--lang") or "en"
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib, lang=lang),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib, lang=lang),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_update_materialize.py librarian/tests/test_update_two_vault.py -q`
Expected: PASS (the pre-existing tests, now passing the localized-folder default-`en` path verbatim, plus the new `zh` test).

- [ ] **Step 5: Run the FULL suite to confirm no regression**

Run: `pytest -q`
Expected: PASS — the whole suite green (Plans 1–2 + the new Plan 3 tests).

- [ ] **Step 6: Commit**

```bash
git add librarian/update.py librarian/tests/test_update_materialize.py
git commit -m "feat(librarian): thread --lang through materialize and verify"
```

---

## Task 6: Name the canon language in the labeling prompt

**Files:**
- Modify: `librarian/orchestrate/build_wave.py`
- Test: `librarian/tests/test_build_wave.py`

Context (spec §4b labeling rule): the wave assignment already instructs the agent to classify into the canon and write summaries in the source language, but it says "the canon language" generically. Name the canon language explicitly (e.g. "English" for `label_language == "en"`) so the agent emits English labels reliably. `_agent_file` gains the canon-language name; `build` passes it from `cfg.label_language`.

- [ ] **Step 1: Add an assertion that the assignment names the canon language**

In `librarian/tests/test_build_wave.py`, inside `test_build_writes_one_file_per_agent`, add this assertion after the existing `assert "Active topics: 文学评论" in text` line:

```python
    assert "in English" in text   # canon language named (cfg.label_language == "en")
```

(The `cfg` fixture's `label_language` defaults to `"en"`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest librarian/tests/test_build_wave.py::test_build_writes_one_file_per_agent -q`
Expected: FAIL — the assignment text does not contain "in English".

- [ ] **Step 3: Name the canon language in `_agent_file`**

In `librarian/orchestrate/build_wave.py`, add a language-name map near the top (after the imports):

```python
# Human-readable names for the canon language code, for the labeling prompt.
LANGUAGE_NAMES = {"en": "English", "zh": "Chinese"}
```

Change `_agent_file`'s signature to accept the canon-language name:
```python
def _agent_file(wave_no, agent_no, rows, legacy_nfc, canon, vault):
```
to:
```python
def _agent_file(wave_no, agent_no, rows, legacy_nfc, canon, vault, canon_lang):
```

Replace the instruction line:
```python
           "Read each article's FULL text at source_path. Classify into the "
           "active canon below; propose new topics (in the canon language) only "
           "when nothing fits. Write the summary in the article's own language.\n",
```
with:
```python
           "Read each article's FULL text at source_path. Classify into the "
           f"active canon below; propose new topics in {canon_lang} only when "
           "nothing fits. Write the summary in the article's own language.\n",
```

In `build`, pass the canon-language name. Replace:
```python
        text = _agent_file(wave_no, ai, slice_rows, legacy_nfc, canon, vault)
```
with:
```python
        canon_lang = LANGUAGE_NAMES.get(cfg.label_language, cfg.label_language)
        text = _agent_file(wave_no, ai, slice_rows, legacy_nfc, canon, vault, canon_lang)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest librarian/tests/test_build_wave.py -q`
Expected: PASS (6 tests — the existing ones still pass; the new assertion is satisfied).

- [ ] **Step 5: Run the FULL suite**

Run: `pytest -q`
Expected: PASS — whole suite green.

- [ ] **Step 6: Commit**

```bash
git add librarian/orchestrate/build_wave.py librarian/tests/test_build_wave.py
git commit -m "feat(librarian): name the canon language in the labeling prompt"
```

---

## Self-Review (run after all tasks)

**1. Spec coverage (spec §4b language & localization + §5 step 8 materialize + §8 invariant):**
- `--lang en|zh`, no config default, `en` renders canon verbatim (spec §4b layer 2) → `lang="en"` default everywhere; `cfg.localize_category`/`localize.topic_name` return verbatim when `lang == label_language` (Tasks 1–5). ✓
- Localization drives **folder names** → `refile` (Task 2) + `_materialize_to_library` dest (Task 5). ✓
- Localization drives **hub-note filenames** → `hubgen` filename via `localize.topic_name` (Task 3). ✓
- Localization drives **hub-note section headers** (`阅读清单`, `相关话题`, …) → `localize.headers` + `hubgen` (Tasks 1, 3). ✓
- Categories localized via `config.category_localization`; topics via the `name_zh` column appended in Plan 1 (`TOPIC_COLUMNS[7]`) → `localize.topic_name` (Task 1). ✓
- §8 invariant: `verify`'s folder-matches-primary compares against `localize(primary_category, lang)`, and the hub invariants use localized topic names → Task 4. ✓
- Labeling-prompt rule (classify into the English canon, propose new topics in English, summary in source language) → `build_wave._agent_file` names the canon language (Task 6); the summary-in-source-language clause already shipped in Plan 2. ✓
- Article body + `summary` stay source-language, never translated → frontmatter is NOT localized (decision recorded in Architecture; no task touches `frontmatter.apply`). ✓
- **Out of scope, correctly deferred:** `orchestrate/materialize.py` extraction (spec §3); steady-state/ledger (Plan 4); skill packaging/scheduling (Plan 5). ✓

**2. Placeholder scan:** every code step has literal code; every command step has an exact `pytest` invocation + expected result. The one judgement call is the dead `row = [...]` placeholder line in Task 4's test — it is explicitly called out with a "delete this line when transcribing" instruction, not left as a silent TODO.

**3. Type/signature consistency across tasks:**
- `localize.headers(lang) -> dict` with keys `reading_list`/`related`/`parent`/`children` — defined Task 1; consumed by `hubgen` (Task 3). ✓
- `localize.topic_name(cfg, reg, name, lang) -> str` — defined Task 1; consumed by `hubgen` (Task 3) and `verify` (Task 4). ✓
- `refile.plan(label_rows, vault, cfg, lang="en")` — defined Task 2; called by `update.cmd_materialize` (Task 5) and `test_refile` (Task 2). ✓
- `hubgen.plan(label_rows, reg, vault, cfg, lang="en")` — defined Task 3; called by `update.cmd_materialize` + `_materialize_to_library` (Task 5) and `test_hubgen` (Task 3). ✓
- `verify.run(label_rows, reg, vault, categories, cfg, manifest_rows=None, lang="en")` — `lang` appended after `manifest_rows` so existing keyword callers stay valid; defined Task 4; called by `update.verify_problems` (Task 5). ✓
- `update.cmd_materialize(write=False, out=None, lang="en")`, `_materialize_to_library(rows, reg, library, write, lang="en")`, `verify_problems(library=None, lang="en")`, `cmd_verify(library=None, lang="en")` — all defined + wired in Task 5; CLI passes `lang` from `_opt("--lang") or "en"`. ✓
- `build_wave._agent_file(..., canon_lang)` + `LANGUAGE_NAMES` — defined Task 6; `build` supplies `canon_lang` from `cfg.label_language`. ✓
- Reused unchanged: `cfg.localize_category(name, lang)` (Plan 1), `reg.by_name`/`reg.active_names()`, `cfg.label_language`, `refile.apply`, `hubgen.apply`, `cooccur.weights`/`related`. ✓

---

## Execution note

Plan 3 is additive plus three behaviour changes a reader should expect: (1) the default-`en` materialize now writes **English** hub section headers (the ported Chinese strings were a MyBooks holdover; the canon is English); (2) `refile.plan` now requires a `cfg` argument; (3) `verify.run`/`update` materialize/verify gain a `lang` keyword (default `en`, behaviour-preserving). The completion signal is a green full suite (Task 5 Step 5 / Task 6 Step 5). A `--lang zh` run now produces a fully Chinese-displayed vault (folders, hub filenames, links, section headers) that verifies clean, while the stored canon and article frontmatter remain English. The deferred `orchestrate/materialize.py` extraction (spec §3) can build directly on these lang-aware leaf modules.
