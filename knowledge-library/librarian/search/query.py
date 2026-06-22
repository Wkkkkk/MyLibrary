"""One semantic query: embed it (with the query instruction), score against the
stored matrix via dot product (vectors are pre-normalized, so this is cosine),
apply optional category/topic filters, and return the top-N ranked results."""
from dataclasses import dataclass

import numpy as np

from librarian.search.index_store import IndexStore


@dataclass
class SearchResult:
    score: float
    title: str
    summary: str
    primary_category: str
    topics: str
    relative_path: str
    url: str


def _topics(s):
    return [t.strip() for t in s.split(";") if t.strip()]


def search(cfg, settings, embedder, query, *, limit=None, category=None,
           topic=None, store_factory=None):
    open_store = store_factory or IndexStore.open
    limit = limit or settings.default_limit
    idx = open_store(settings.index_path)
    try:
        metas, matrix = idx.load_matrix()
    finally:
        idx.close()
    if not metas:
        return []
    qvec = np.asarray(embedder.embed([query], is_query=True)[0], dtype=np.float32)
    scores = matrix @ qvec
    results = []
    for i in np.argsort(-scores):
        m = metas[i]
        if category and m["primary_category"] != category:
            continue
        if topic and topic not in _topics(m["topics"]):
            continue
        results.append(SearchResult(
            score=float(scores[i]), title=m["title"], summary=m["summary"],
            primary_category=m["primary_category"], topics=m["topics"],
            relative_path=m["relative_path"], url=m["url"]))
        if len(results) >= limit:
            break
    return results
