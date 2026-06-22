"""MCP server exposing the library's semantic search as a `search_library` tool,
for any MCP client (Claude, QwenPaw — both support MCP). Run:

  KNOWLEDGE_LIBRARY_CONFIG=config.yaml python -m librarian.search.mcp_server

`run_search` is the pure, importable seam (no `mcp` dependency); `build_server`
is the thin FastMCP wiring and requires `pip install mcp`."""
import os

from librarian import config
from librarian.search import settings as ssettings
from librarian.search import embedder as semb
from librarian.search import query as q


def _load():
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    return cfg, ssettings.from_config(cfg)


def run_search(query, limit=None, category=None, topic=None, *, _ctx=None):
    cfg, s = _ctx or _load()
    emb = semb.OllamaEmbedder(s)
    results = q.search(cfg, s, emb, query, limit=limit, category=category,
                       topic=topic)
    return [{"score": r.score, "title": r.title, "summary": r.summary,
             "primary_category": r.primary_category, "topics": r.topics,
             "relative_path": r.relative_path, "url": r.url}
            for r in results]


def build_server():
    from mcp.server.fastmcp import FastMCP
    ctx = _load()
    server = FastMCP("knowledge-library")

    @server.tool()
    def search_library(query: str, limit: int = 0, category: str = "",
                       topic: str = "") -> list:
        """Semantic search over the knowledge library. Returns the most relevant
        notes (title, summary, category, topics, vault path) ranked by meaning."""
        return run_search(query, limit=limit or None, category=category or None,
                          topic=topic or None, _ctx=ctx)

    return server


if __name__ == "__main__":
    build_server().run()
