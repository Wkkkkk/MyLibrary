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
