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


def test_materialize_to_library_lang_zh_localizes_folder(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    lib.mkdir()
    c = config.Config(
        corpus_path=inbox, library_path=lib, data_dir=data,
        categories={"Literature"}, label_language="en",
        category_localization={"Literature": {"zh": "文学"}}, hub_min_articles=1)
    monkeypatch.setattr(update, "cfg", c)
    _article(inbox, "AI/x.md", "Literature")   # arrives under a zhihu-ish folder
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    row = _lrow("AI/x.md", "Literature")
    row[4] = "Lit Crit"           # topics
    row[7] = "s"                  # summary
    row[8], row[9] = "high", "false"
    tsv.write_rows(c.labels_path, contract.LABEL_COLUMNS, [row])
    tsv.write_rows(c.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(inbox, c))

    update.cmd_materialize(write=True, out=lib, lang="zh")

    # filed into the localized library folder; inbox original removed
    assert (lib / "文学" / "x.md").exists()
    assert not (lib / "Literature").exists()
    assert not (inbox / "AI" / "x.md").exists()
    _, rows = tsv.read_rows(c.labels_path, contract.LABEL_COLUMNS)
    assert [r[0] for r in rows] == ["文学/x.md"]
    # the localized library verifies clean under the same lang
    assert update.verify_problems(library=lib, lang="zh") == []


def test_materialize_aborts_cleanly_when_source_missing(tmp_path, monkeypatch):
    # finding #8/#9: after a prior --out/--lang materialize, the shared labels
    # point at a vault/layout that no longer matches corpus_path. Re-materialize
    # must fail with a clear error BEFORE any move — never a mid-loop assert that
    # scatters a partial move and wedges the library.
    import pytest
    vault = tmp_path / "vault"
    data = tmp_path / "data"
    data.mkdir()
    vault.mkdir()
    labels, _, man = _patch(monkeypatch, vault, data)
    # label points at a file that does not exist on disk
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("文学/ghost.md", "历史人文")])
    tsv.write_rows(man, contract.MANIFEST_COLUMNS, [])

    with pytest.raises(ValueError, match="missing"):
        update.cmd_materialize(write=True)

    # nothing was mutated: no partial move folders, label row untouched
    assert not (vault / "历史人文").exists()
    _, rows = tsv.read_rows(labels, contract.LABEL_COLUMNS)
    assert [r[0] for r in rows] == ["文学/ghost.md"]
