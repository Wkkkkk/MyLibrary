"""diff (library mode) must dedup inbox articles by their stable zhihu url, not
by content_hash — re-fetched articles have the same url but different bytes.
"""
from librarian import update, config, contract, tsv, manifest


def _patch(monkeypatch, inbox, data, categories=("文学", "效率与工具", "AI与机器学习")):
    c = config.Config(corpus_path=inbox, library_path=inbox, data_dir=data,
                      categories=set(categories))
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS, [])
    monkeypatch.setattr(update, "cfg", c)
    return c.labels_path


def _article(vault, rel, url, body="x"):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "t"\nurl: "{url}"\n---\n\n# t\n{body}\n', encoding="utf-8")


def _lrow(rel):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[12] = rel, "t", "文学", "deadbeef"
    return r


def test_read_url_extracts_frontmatter_url(tmp_path):
    p = tmp_path / "a.md"
    p.write_text('---\ntitle: "t"\nurl: "https://zhuanlan.zhihu.com/p/123"\n---\n\nbody\n',
                 encoding="utf-8")
    assert manifest.read_url(p) == "https://zhuanlan.zhihu.com/p/123"


def test_diff_dedups_by_url_despite_different_content(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    lib = tmp_path / "lib"
    data = tmp_path / "data"
    data.mkdir()
    # library has an article with url U1 (its own, frontmatter-rewritten content)
    _article(lib, "文学/dup.md", "https://zhihu.com/p/1", body="library copy")
    labels = _patch(monkeypatch, inbox, data)
    tsv.write_rows(labels, contract.LABEL_COLUMNS, [_lrow("文学/dup.md")])
    # inbox: a re-fetch of U1 (different bytes) + a genuinely new article U2
    _article(inbox, "AI与人工智能/dup.md", "https://zhihu.com/p/1", body="re-fetched, differs")
    _article(inbox, "效率与工具/fresh.md", "https://zhihu.com/p/2", body="brand new")

    new = update.cmd_diff(library=lib)

    assert {r[0] for r in new} == {"效率与工具/fresh.md"}  # U1 recognized as already present
