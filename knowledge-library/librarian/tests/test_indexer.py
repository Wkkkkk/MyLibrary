import numpy as np
from librarian import config, store, contract
from librarian.search import indexer
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder
from librarian.search.index_store import IndexStore


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db", "embed_batch_size": 2})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _write_article(cfg, rel, url, body="body text"):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")


def _label(rel, h):
    # LABEL_COLUMNS order; primary=3, topics=4, summary=7, content_hash=12
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "Title", "文学", "诗; 词", "sum", h
    return r


class SpyFake(FakeEmbedder):
    def __init__(self):
        self.calls = 0

    def embed(self, texts, *, is_query=False):
        self.calls += len(texts)
        return super().embed(texts, is_query=is_query)


def test_build_inputs_skips_missing_url(tmp_path):
    cfg = _cfg(tmp_path)
    _write_article(cfg, "文学/a.md", "u-a")
    (cfg.library_path / "文学/b.md").write_text("---\ntitle: NoUrl\n---\nx\n",
                                               encoding="utf-8")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h2")])
    records, skipped = indexer.build_inputs(cfg)
    assert [r["url"] for r in records] == ["u-a"]
    assert skipped == ["文学/b.md"]
    assert "body text" in records[0]["_text"] and "sum" in records[0]["_text"]


def test_first_index_embeds_all_then_incremental(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    spy = SpyFake()
    out = indexer.update_index(cfg, s, spy)
    assert out["embedded"] == 2 and out["total"] == 2 and spy.calls == 2

    # Re-run with no changes -> embeds nothing.
    spy2 = SpyFake()
    out2 = indexer.update_index(cfg, s, spy2)
    assert out2["embedded"] == 0 and spy2.calls == 0 and out2["total"] == 2


def test_changed_hash_reembeds_only_that_row(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    store.merge(cfg.labels_path, [_label("文学/b.md", "h2")])   # b changed
    spy = SpyFake()
    out = indexer.update_index(cfg, s, spy)
    assert spy.calls == 1 and out["embedded"] == 1


def test_deleted_article_removed_from_index(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    _write_article(cfg, "文学/b.md", "u-b")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1"),
                                  _label("文学/b.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    store.delete(cfg.labels_path, ["文学/b.md"])
    out = indexer.update_index(cfg, s, FakeEmbedder())
    assert out["deleted"] == 1 and out["total"] == 1


def test_model_change_forces_rebuild(tmp_path):
    cfg = _cfg(tmp_path); s = from_config(cfg)
    _write_article(cfg, "文学/a.md", "u-a")
    store.merge(cfg.labels_path, [_label("文学/a.md", "h1")])
    indexer.update_index(cfg, s, FakeEmbedder())
    cfg2 = _cfg(tmp_path)
    cfg2.search["embed_model"] = "different-model"
    s2 = from_config(cfg2)
    spy = SpyFake()
    out = indexer.update_index(cfg2, s2, spy)   # hash unchanged, but model changed
    assert spy.calls == 1 and out["embedded"] == 1
