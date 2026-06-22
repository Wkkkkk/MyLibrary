from librarian import update, config, store, contract
from librarian.search import indexer
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


def test_cmd_index_uses_fake_embedder(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    monkeypatch.setattr(update, "cfg", cfg)
    # Inject the fake embedder + no-op preflight so no real Ollama is touched.
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.ensure_model",
                        lambda *a, **k: None)
    update.cmd_index()
    assert "embedded 1" in capsys.readouterr().out


def test_cmd_search_prints_results(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("alpha", limit=5)
    out = capsys.readouterr().out
    assert "Alpha Doc" in out and "文学/a.md" in out


def test_cmd_search_empty_index_hints(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("anything")
    assert "index" in capsys.readouterr().out.lower()


def test_cmd_search_warns_when_index_is_stale(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    # Index one article, then add a second label row that is NOT indexed.
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "alpha", "h")])
    indexer.update_index(cfg, from_config(cfg), FakeEmbedder())
    store.merge(cfg.labels_path, [_article(cfg, "文学/b.md", "u-b", "beta", "h")])
    monkeypatch.setattr(update, "cfg", cfg)
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    update.cmd_search("alpha", limit=5)
    assert "not yet indexed" in capsys.readouterr().out
