import numpy as np
import pytest
from librarian.search import embedder as emb
from librarian.search.settings import from_config, QUERY_INSTRUCTION
from librarian import config


def _settings(tmp_path, **search):
    cfg = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                        data_dir=tmp_path / "d", categories={"文学"}, search=search)
    return from_config(cfg)


def test_fake_embedder_deterministic_and_normalized():
    f = emb.FakeEmbedder()
    a = f.embed(["hello", "world"])
    b = f.embed(["hello", "world"])
    assert a.shape == (2, 16)
    np.testing.assert_allclose(a, b)                      # deterministic
    np.testing.assert_allclose(np.linalg.norm(a, axis=1), [1.0, 1.0], atol=1e-6)
    assert not np.allclose(a[0], a[1])                    # different text -> different vec


def test_ollama_embed_shapes_request_and_normalizes(tmp_path, monkeypatch):
    captured = {}

    def fake_post(self, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"embeddings": [[3.0, 4.0]]}              # not unit length

    monkeypatch.setattr(emb.OllamaEmbedder, "_post", fake_post)
    e = emb.OllamaEmbedder(_settings(tmp_path, embed_model="m1"))
    vecs = e.embed(["doc text"])
    assert captured["path"] == "/api/embed"
    assert captured["payload"] == {"model": "m1", "input": ["doc text"]}
    np.testing.assert_allclose(vecs[0], [0.6, 0.8], atol=1e-6)   # L2-normalized
    assert e.dim == 2


def test_ollama_query_prepends_instruction(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(emb.OllamaEmbedder, "_post",
                        lambda self, p, payload: captured.update(payload)
                        or {"embeddings": [[1.0, 0.0]]})
    e = emb.OllamaEmbedder(_settings(tmp_path))
    e.embed(["who?"], is_query=True)
    assert captured["input"] == [QUERY_INSTRUCTION + "who?"]


def test_ensure_model_present_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: {"qwen3-embedding"})
    emb.ensure_model(_settings(tmp_path), runner=lambda *a, **k: pytest.fail("no pull"))


def test_ensure_model_pulls_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: set())
    calls = []

    class R:
        returncode = 0

    emb.ensure_model(_settings(tmp_path, embed_model="m"),
                     runner=lambda cmd, **k: calls.append(cmd) or R(), log=lambda *a: None)
    assert calls == [["ollama", "pull", "m"]]


def test_ensure_model_unreachable_raises(tmp_path, monkeypatch):
    def boom(s):
        raise OSError("connection refused")
    monkeypatch.setattr(emb, "_list_models", boom)
    with pytest.raises(RuntimeError, match="unreachable"):
        emb.ensure_model(_settings(tmp_path))


def test_ensure_model_missing_no_autopull_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "_list_models", lambda s: set())
    with pytest.raises(RuntimeError, match="auto_pull"):
        emb.ensure_model(_settings(tmp_path, auto_pull=False))
