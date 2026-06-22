from pathlib import Path
from librarian import config
from librarian.search import settings as ss


def _cfg(tmp_path, search=None):
    return config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "data", categories={"文学"},
        search=search or {})


def test_defaults_when_no_search_block(tmp_path):
    s = ss.from_config(_cfg(tmp_path))
    assert s.embed_backend == "ollama"
    assert s.ollama_host == "http://localhost:11434"
    assert s.embed_model == "qwen3-embedding"
    assert s.embed_batch_size == 16
    assert s.auto_pull is True
    assert s.default_limit == 10
    # relative index_path resolves under data_dir
    assert s.index_path == tmp_path / "data" / "search_index.db"


def test_overrides_and_host_trailing_slash(tmp_path):
    s = ss.from_config(_cfg(tmp_path, {
        "embed_model": "qwen3-embedding:4b", "ollama_host": "http://h:1234/",
        "auto_pull": False, "default_limit": 5, "embed_batch_size": 8}))
    assert s.embed_model == "qwen3-embedding:4b"
    assert s.ollama_host == "http://h:1234"   # trailing slash stripped
    assert s.auto_pull is False
    assert s.default_limit == 5
    assert s.embed_batch_size == 8


def test_absolute_index_path_kept(tmp_path):
    s = ss.from_config(_cfg(tmp_path, {"index_path": "/abs/idx.db"}))
    assert s.index_path == Path("/abs/idx.db")
