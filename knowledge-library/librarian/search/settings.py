"""Resolve the `search:` config block into a typed SearchSettings, applying
defaults (spec §4) and resolving index_path against data_dir. Keeps all search
defaults in one place so core config.py only stores the raw dict."""
from dataclasses import dataclass
from pathlib import Path

# Prepended to query text only (document text is embedded raw) — Qwen3-Embedding
# is instruction-aware and this asymmetry improves retrieval (spec §6).
QUERY_INSTRUCTION = ("Instruct: Given a search query, retrieve relevant "
                     "library articles that answer it\nQuery: ")

DEFAULTS = {
    "embed_backend": "ollama",
    "ollama_host": "http://localhost:11434",
    "embed_model": "qwen3-embedding",
    "embed_batch_size": 16,
    "auto_pull": True,
    "index_path": "search_index.db",
    "default_limit": 10,
    # Cap on embed-text length. Ollama's /api/embed rejects (HTTP 400) inputs
    # over the model's context, so over-long article bodies are truncated to
    # this many characters before embedding (spec §5). title + summary lead the
    # text, so they always survive; only a long body's tail is trimmed.
    "max_embed_chars": 12000,
}


@dataclass
class SearchSettings:
    embed_backend: str
    ollama_host: str
    embed_model: str
    embed_batch_size: int
    auto_pull: bool
    index_path: Path
    default_limit: int
    max_embed_chars: int


def from_config(cfg):
    raw = dict(DEFAULTS)
    raw.update(getattr(cfg, "search", None) or {})
    index_path = Path(str(raw["index_path"])).expanduser()
    if not index_path.is_absolute():
        index_path = cfg.data_dir / index_path
    return SearchSettings(
        embed_backend=str(raw["embed_backend"]),
        ollama_host=str(raw["ollama_host"]).rstrip("/"),
        embed_model=str(raw["embed_model"]),
        embed_batch_size=int(raw["embed_batch_size"]),
        auto_pull=bool(raw["auto_pull"]),
        index_path=index_path,
        default_limit=int(raw["default_limit"]),
        max_embed_chars=int(raw["max_embed_chars"]),
    )
