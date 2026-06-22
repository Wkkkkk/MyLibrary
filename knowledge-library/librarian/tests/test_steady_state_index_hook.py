from librarian import config, store, contract
from librarian.orchestrate import steady_state
from librarian.search.settings import from_config
from librarian.search.index_store import IndexStore
from librarian.search.embedder import FakeEmbedder


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "lib", library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"文学"},
                      search={"index_path": "idx.db"})
    (tmp_path / "lib").mkdir(parents=True, exist_ok=True)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _article(cfg, rel, url, h):
    p = cfg.library_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\nurl: {url}\ntitle: T\n---\nbody\n", encoding="utf-8")
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[4], r[7], r[12] = rel, "T", "文学", "诗", "s", h
    return r


def test_hook_refreshes_index(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "h")])
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())
    monkeypatch.setattr("librarian.search.embedder.ensure_model",
                        lambda *a, **k: None)
    steady_state._index_after_materialize(cfg)
    idx = IndexStore.open(from_config(cfg).index_path)
    assert idx.count() == 1


def test_hook_is_non_fatal_on_embedder_error(tmp_path, monkeypatch, capsys):
    cfg = _cfg(tmp_path)
    store.merge(cfg.labels_path, [_article(cfg, "文学/a.md", "u-a", "h")])
    monkeypatch.setattr("librarian.search.embedder.OllamaEmbedder",
                        lambda settings: FakeEmbedder())

    def boom(*a, **k):
        raise RuntimeError("Ollama unreachable")
    monkeypatch.setattr("librarian.search.embedder.ensure_model", boom)
    steady_state._index_after_materialize(cfg)        # must NOT raise
    assert "not refreshed" in capsys.readouterr().out
