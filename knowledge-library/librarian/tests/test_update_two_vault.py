"""Two-vault (inbox -> library) steady-state semantics for librarian.update.

Inbox == cfg.corpus_path (知乎收藏, a drop-zone emptied by materialize).
Library == 知乎收藏_v2 (the canonical vault the manifest + verify describe).
"""
from librarian import update, config, contract, tsv, manifest, registry


def _patch(monkeypatch, inbox, data, categories=("文学", "历史人文", "AI与机器学习")):
    c = config.Config(corpus_path=inbox, library_path=inbox, data_dir=data,
                      categories=set(categories))
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS, [])
    monkeypatch.setattr(update, "cfg", c)
    return c.labels_path, c.topics_path, c.manifest_path


def _lrow(rel, primary, content_hash):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[12] = rel, "t", primary, content_hash
    r[8], r[9] = "high", "false"  # confidence, needs_review enums
    return r


def _article(vault, rel, body="x"):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: \"t\"\n---\n\n# t\n{body}\n", encoding="utf-8")


def test_verify_library_mode_checks_the_library_not_the_inbox(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    inbox.mkdir()
    # article lives in the library; inbox is empty (already materialized)
    _article(lib, "历史人文/a.md")
    labels, _, man = _patch(monkeypatch, inbox, data)
    h = next(r[3] for r in manifest.build(lib, update.cfg) if r[0] == "历史人文/a.md")
    row = _lrow("历史人文/a.md", "历史人文", h)
    row[4] = ""  # no topics -> still need >=1; give it one active topic
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [row])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(lib, update.cfg))
    # registry with one active topic so the row can carry a valid topic
    tsv.write_rows(data / "topics.tsv", contract.TOPIC_COLUMNS,
                   [["T1", "历史写作", "", "", "active", "", "2026-06-12", ""]])
    row[4] = "历史写作"
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [row])

    problems = update.verify_problems(library=lib)

    assert problems == [], problems


def test_ingest_library_mode_merges_without_deleting_existing_library_labels(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    # an article already filed in the library; its inbox original is long gone
    _article(lib, "历史人文/old.md")
    labels, _, man = _patch(monkeypatch, inbox, data)
    old_h = next(r[3] for r in manifest.build(lib, update.cfg) if r[0] == "历史人文/old.md")
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("历史人文/old.md", "历史人文", old_h)])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(lib, update.cfg))
    # registry needs an active topic for the new row to validate
    tsv.write_rows(data / "topics.tsv", contract.TOPIC_COLUMNS,
                   [["T1", "大模型与智能体", "", "", "active", "", "2026-06-12", ""]])
    # a freshly-labeled new article still sitting in the inbox
    _article(inbox, "AI与人工智能/new.md", body="fresh")
    new_h = next(r[3] for r in manifest.build(inbox, update.cfg) if r[0] == "AI与人工智能/new.md")
    new_row = _lrow("AI与人工智能/new.md", "AI与机器学习", new_h)
    new_row[4] = "大模型与智能体"  # topics
    batch = data / "batch_out.tsv"
    tsv.write_rows(batch, contract.LABEL_COLUMNS, [new_row])

    update.cmd_ingest(str(batch), library=lib)

    paths = {r[0] for r in tsv.read_rows(labels, contract.LABEL_COLUMNS)[1]}
    assert paths == {"历史人文/old.md", "AI与人工智能/new.md"}  # existing label NOT deleted
    # manifest still describes the library, untouched by ingest
    assert {r[0] for r in tsv.read_rows(man, contract.MANIFEST_COLUMNS)[1]} == {"历史人文/old.md"}
