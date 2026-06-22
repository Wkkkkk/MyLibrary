"""Build/refresh the vector index from label state. Reads each labeled article's
body + summary + title as the embed text, diffs against the store by content_hash
(spec §5), embeds only new/changed rows in batches, upserts, and drops removed
articles. The embed model is recorded in meta; a model change forces a rebuild."""
from librarian import store, manifest
from librarian.search.index_store import IndexStore

# LABEL_COLUMNS positional indices (see contract.py / Global Constraints).
_REL, _TITLE, _PRIMARY, _TOPICS, _SUMMARY, _HASH = 0, 1, 3, 4, 7, 12


def build_inputs(cfg):
    records, skipped = [], []
    for r in store.load(cfg.labels_path):
        rel = r[_REL]
        path = cfg.library_path / rel
        url = manifest.read_url(path)
        if not url:
            skipped.append(rel)
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            skipped.append(rel)
            continue
        text = "\n\n".join(p for p in (r[_TITLE], r[_SUMMARY], body) if p)
        records.append({
            "url": url, "relative_path": rel, "title": r[_TITLE],
            "summary": r[_SUMMARY], "primary_category": r[_PRIMARY],
            "topics": r[_TOPICS], "content_hash": r[_HASH], "_text": text})
    return records, skipped


def update_index(cfg, settings, embedder, *, rebuild=False, store_factory=None):
    open_store = store_factory or IndexStore.open
    idx = open_store(settings.index_path)
    try:
        if idx.get_meta("embed_model") not in (None, settings.embed_model):
            rebuild = True
        if rebuild:
            idx.delete(list(idx.hashes()))

        records, skipped = build_inputs(cfg)
        existing = idx.hashes()
        want = {rec["url"] for rec in records}
        to_embed = [rec for rec in records
                    if existing.get(rec["url"]) != rec["content_hash"]]
        deleted = [u for u in existing if u not in want]

        bs = max(1, settings.embed_batch_size)
        embedded = 0
        for i in range(0, len(to_embed), bs):
            batch = to_embed[i:i + bs]
            vecs = embedder.embed([rec["_text"] for rec in batch])
            payload = []
            for rec, vec in zip(batch, vecs):
                clean = {k: v for k, v in rec.items() if k != "_text"}
                clean["vector"] = vec
                payload.append(clean)
            idx.upsert(payload)            # commits per batch (transactional)
            embedded += len(payload)

        idx.delete(deleted)
        idx.set_meta("embed_model", settings.embed_model)
        return {"embedded": embedded, "deleted": len(deleted),
                "skipped": skipped, "total": idx.count()}
    finally:
        idx.close()
