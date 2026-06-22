from librarian import config, store, contract
from librarian.search import indexer, mcp_server
from librarian.search.settings import from_config
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db"})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, body, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\n{body}\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "Alpha Doc", "文学", "诗", body, h
    return r


def test_run_search_returns_structured_dicts(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    s = from_config(cfg)
    indexer.update_index(cfg, s, FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    out = mcp_server.run_search("alpha", limit=5, _ctx=(cfg, s))
    assert isinstance(out, list) and isinstance(out[0], dict)
    assert set(out[0]) == {"score", "title", "summary", "primary_category",
                           "topics", "relative_path", "url"}
    assert out[0]["url"] == "u-a"
