"""Tests for librarian.update.cmd_materialize consistency after re-filing.

When materialize moves an article into its primary_category folder, the labels
TSV, the manifest, and the on-disk vault must all agree afterwards: exactly one
row per article (at its NEW path), and the manifest rebuilt from disk.
"""
from librarian import update, config, contract, tsv, manifest


def _patch(monkeypatch, vault, data, categories=("文学", "历史人文", "AI与机器学习")):
    c = config.Config(corpus_path=vault, library_path=vault, data_dir=data,
                      categories=set(categories))
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS, [])
    monkeypatch.setattr(update, "cfg", c)
    return c.labels_path, c.topics_path, c.manifest_path


def _lrow(rel, primary):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3] = rel, "t", primary  # path, title, primary_category
    r[12] = "hash0"
    return r


def _article(vault, rel, primary):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntitle: \"t\"\nprimary_category: \"{primary}\"\n---\n\n# t\n",
                 encoding="utf-8")


def test_materialize_refile_leaves_no_duplicate_label_rows(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    data.mkdir()
    # article sits in 文学/ but its label re-shelves it to 历史人文
    _article(vault, "文学/a.md", "历史人文")
    labels, _, man = _patch(monkeypatch, vault, data)
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("文学/a.md", "历史人文")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(vault, update.cfg))

    update.cmd_materialize(write=True)

    _, rows = tsv.read_rows(labels, contract.LABEL_COLUMNS)
    paths = [r[0] for r in rows]
    assert paths == ["历史人文/a.md"], f"expected one row at new path, got {paths}"


def test_materialize_to_library_copies_into_primary_and_removes_source(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    lib.mkdir()
    # article arrives in the inbox under its zhihu folder; label re-shelves it
    _article(inbox, "AI与人工智能/a.md", "AI与机器学习")
    labels, _, man = _patch(monkeypatch, inbox, data)  # cfg.corpus_path == inbox
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("AI与人工智能/a.md", "AI与机器学习")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(inbox, update.cfg))

    update.cmd_materialize(write=True, out=lib)

    assert (lib / "AI与机器学习" / "a.md").exists()        # copied into library/<primary>/
    assert not (inbox / "AI与人工智能" / "a.md").exists()   # original removed from inbox
    _, rows = tsv.read_rows(labels, contract.LABEL_COLUMNS)
    assert [r[0] for r in rows] == ["AI与机器学习/a.md"]     # label path is now library-relative
    # manifest now describes the library, matching what's on disk there
    _, stored = tsv.read_rows(man, contract.MANIFEST_COLUMNS)
    assert {r[0] for r in stored} == {r[0] for r in manifest.build(lib, update.cfg)} == {"AI与机器学习/a.md"}


def _article_url(vault, rel, url, body="x"):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "t"\nurl: "{url}"\n---\n\n# t\n{body}\n', encoding="utf-8")


def test_materialize_to_library_avoids_overwriting_a_title_collision(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    # an existing v2 article: same title/basename, but a DIFFERENT article (url)
    _article_url(lib, "文学/X.md", "https://zhihu.com/p/OLD", body="the original")
    # inbox: a different article that happens to share the title -> same basename
    _article_url(inbox, "AI与人工智能/X.md", "https://zhihu.com/p/NEW", body="the new one")
    labels, _, man = _patch(monkeypatch, inbox, data)
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("AI与人工智能/X.md", "文学")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(inbox, update.cfg))

    update.cmd_materialize(write=True, out=lib)

    # the existing article must NOT be clobbered
    assert "the original" in (lib / "文学" / "X.md").read_text(encoding="utf-8")
    assert manifest.read_url(lib / "文学" / "X.md") == "https://zhihu.com/p/OLD"
    # the new article is filed alongside it with a _2 suffix
    assert (lib / "文学" / "X_2.md").exists()
    assert manifest.read_url(lib / "文学" / "X_2.md") == "https://zhihu.com/p/NEW"
    _, rows = tsv.read_rows(labels, contract.LABEL_COLUMNS)
    assert [r[0] for r in rows] == ["文学/X_2.md"]


def test_materialize_to_library_is_idempotent_when_source_already_gone(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    inbox.mkdir()
    # article already lives in the library; inbox is empty; label key is the v2 path
    _article(lib, "AI与机器学习/a.md", "AI与机器学习")
    labels, _, man = _patch(monkeypatch, inbox, data)
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("AI与机器学习/a.md", "AI与机器学习")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(lib, update.cfg))

    update.cmd_materialize(write=True, out=lib)  # must not raise

    assert (lib / "AI与机器学习" / "a.md").exists()
    _, rows = tsv.read_rows(labels, contract.LABEL_COLUMNS)
    assert [r[0] for r in rows] == ["AI与机器学习/a.md"]


def test_materialize_refile_refreshes_manifest_to_match_disk(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    data.mkdir()
    _article(vault, "文学/a.md", "历史人文")
    labels, _, man = _patch(monkeypatch, vault, data)
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("文学/a.md", "历史人文")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, manifest.build(vault, update.cfg))

    update.cmd_materialize(write=True)

    _, stored = tsv.read_rows(man, contract.MANIFEST_COLUMNS)
    assert {r[0] for r in stored} == {r[0] for r in manifest.build(vault, update.cfg)}
    assert {r[0] for r in stored} == {"历史人文/a.md"}
