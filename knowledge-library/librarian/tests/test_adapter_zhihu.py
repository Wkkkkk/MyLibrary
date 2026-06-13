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
