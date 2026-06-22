from librarian import config, store, contract
from librarian.search import indexer, query
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path, **search):
    s = {"index_path": "idx.db"}
    s.update(search)
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学", "历史人文"},
                      search=s)
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, body, primary, topics, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, body[:5], primary, topics, body, h
    return r


def _build(cfg):
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())


def test_empty_index_returns_empty(tmp_path):
    cfg = _cfg(tmp_path)
    out = query.search(cfg, from_config(cfg), FakeEmbedder(), "anything")
    assert out == []


def test_ranks_most_similar_first(tmp_path):
    cfg = _cfg(tmp_path)
    rows = [_article(cfg, "文学/a.md", "u-a", "alpha alpha", "文学", "诗", "h"),
            _article(cfg, "文学/b.md", "u-b", "beta beta", "文学", "词", "h")]
    store.merge(cfg.labels_path, rows)
    _build(cfg)
    # Query with article a's OWN embed text: its query vector is identical to
    # a's stored vector, so cosine similarity is 1.0 — a must rank first by
    # construction, independent of the embedder's internal hashing. A genuine
    # ranking assertion, not a pin on whatever the fake happens to score first.
    a_text = next(r["_text"] for r in indexer.build_inputs(cfg)[0]
                  if r["url"] == "u-a")
    out = query.search(cfg, from_config(cfg), FakeEmbedder(), a_text)
    assert out[0].url == "u-a"
    assert out[0].score >= out[1].score


def test_limit_caps_results(tmp_path):
    cfg = _cfg(tmp_path, default_limit=1)
    store.merge(cfg.labels_path, [
        _article(cfg, "文学/a.md", "u-a", "x", "文学", "诗", "h"),
        _article(cfg, "文学/b.md", "u-b", "y", "文学", "词", "h")])
    _build(cfg)
    assert len(query.search(cfg, from_config(cfg), FakeEmbedder(), "x")) == 1
    assert len(query.search(cfg, from_config(cfg), FakeEmbedder(), "x", limit=2)) == 2


def test_dim_mismatch_raises_clear_error(tmp_path):
    import numpy as np
    import pytest
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "x", "文学", "诗", "h")])
    _build(cfg)  # index built with FakeEmbedder (dim 16)

    class WrongDim:
        dim = 4
        def embed(self, texts, *, is_query=False):
            return np.ones((len(texts), 4), dtype=np.float32)

    with pytest.raises(RuntimeError, match="different embedding model"):
        query.search(cfg, from_config(cfg), WrongDim(), "x")


def test_category_and_topic_filters(tmp_path):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [
        _article(cfg, "文学/a.md", "u-a", "x", "文学", "诗; 散文", "h"),
        _article(cfg, "历史人文/b.md", "u-b", "x", "历史人文", "战争", "h")])
    _build(cfg)
    s = from_config(cfg)
    cat = query.search(cfg, s, FakeEmbedder(), "x", category="历史人文", limit=10)
    assert [r.url for r in cat] == ["u-b"]
    top = query.search(cfg, s, FakeEmbedder(), "x", topic="散文", limit=10)
    assert [r.url for r in top] == ["u-a"]
