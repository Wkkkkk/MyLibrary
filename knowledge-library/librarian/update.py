"""Incremental update orchestrator.

  python3 -m librarian.update diff
  python3 -m librarian.update queue
  python3 -m librarian.update ingest F
  python3 -m librarian.update materialize [--write]
  python3 -m librarian.update verify
  python3 -m librarian.update status
  python3 -m librarian.update audit
  python3 -m librarian.update index [--rebuild]
  python3 -m librarian.update search "<query>" [--limit N] [--category C] [--topic T]
"""
import sys
from datetime import date
from pathlib import Path
from librarian import (config, contract, tsv, manifest, registry, batches,
                       validate, store, verify, audit, proposals)

# The active config. Set by configure() (or __main__); tests monkeypatch it.
cfg = None


def configure(c):
    """Install the active Config for this process."""
    global cfg
    cfg = c


def _manifest_rows():
    _, rows = tsv.read_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS)
    return rows


def load_legacy(path):
    """Read the v1 labels TSV → {relative_path: (primary_categories, subcategories)}.
    Returns {} if the file is missing. v1 schema differs from the v2 contract, so this
    reads raw rather than via tsv.read_rows."""
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    out = {}
    for line in lines[1:]:               # skip header
        f = line.split("\t")
        if len(f) > 4 and f[0]:
            out[f[0]] = (f[3], f[4])
    return out


def _new_inbox_rows(library):
    """Inbox articles not yet in the library, keyed by the stable zhihu `url`
    (survives re-fetch + frontmatter rewrite; a content hash does not). The known
    set is read from the labelled library files themselves."""
    known = {u for u in (manifest.read_url(library / r[0]) for r in store.load(cfg.labels_path)) if u}
    new = []
    for r in manifest.build(cfg.corpus_path, cfg):
        url = manifest.read_url(cfg.corpus_path / r[0])
        if url is None or url not in known:
            new.append(r)
    return new


def cmd_diff(library=None):
    if library is not None and library != cfg.corpus_path:
        new = _new_inbox_rows(library)
        print(f"{len(new)} new inbox article(s)")
        for r in new:
            print(" ", r[0])
        return new
    added, changed, deleted = manifest.diff(_manifest_rows(), manifest.build(cfg.corpus_path, cfg))
    print(f"added {len(added)}, changed {len(changed)}, deleted {len(deleted)}")
    for p in added + changed + deleted:
        print(" ", p)
    return added, changed, deleted


def cmd_queue(library=None):
    if library is not None and library != cfg.corpus_path:
        todo = _new_inbox_rows(library)
    else:
        added, changed, _ = cmd_diff()
        current = manifest.build(cfg.corpus_path, cfg)
        touched = set(added + changed)
        todo = [r for r in current if r[0] in touched]
    if not todo:
        print("nothing to label")
        return
    legacy = load_legacy(cfg.legacy_labels)
    files, hits = batches.make(todo, legacy, cfg.batches_dir, cfg.batch_size, cfg.corpus_path)
    print(f"wrote {len(files)} pending batch file(s); {hits} matched a v1 reference; label them, then `ingest`")


def cmd_ingest(out_tsv, library=None):
    reg = registry.load_or_empty(cfg.topics_path)
    _, rows = tsv.read_rows(Path(out_tsv), contract.LABEL_COLUMNS)
    manifest_paths = {r[0] for r in manifest.build(cfg.corpus_path, cfg)}
    ghosts = [r[0] for r in rows if r[0] not in manifest_paths]
    if ghosts:
        print("\n".join(f"fabricated/nonexistent path: {g}" for g in ghosts))
        sys.exit(1)
    expected = [r[0] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    store.merge(cfg.labels_path, rows)
    n_review = sum(1 for r in rows if r[9] == "true")
    validate.log_progress(cfg.progress_path, Path(out_tsv).name, len(rows), n_review)
    if library is not None and library != cfg.corpus_path:
        # Two-vault mode: the manifest describes the library and is owned by
        # materialize. The inbox is a transient drop-zone, so its diff must not
        # drive label deletion or rewrite the library manifest here.
        print(f"merged {len(rows)} rows; run materialize to file them into {library}")
        return
    added, changed, deleted = manifest.diff(_manifest_rows(), manifest.build(cfg.corpus_path, cfg))
    if deleted:
        store.delete(cfg.labels_path, deleted)
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))
    print(f"merged {len(rows)} rows; manifest refreshed ({date.today()})")


def cmd_materialize(write=False, out=None, lang="en"):
    from librarian.orchestrate import materialize
    return materialize.materialize(cfg, write=write, out=out, lang=lang)


def cmd_proposals(accept=False):
    rows = store.load(cfg.labels_path)
    reg = registry.load_or_empty(cfg.topics_path)
    pend = proposals.pending(rows, reg)
    if not pend:
        print("no pending proposals")
        return
    for name, count, examples in pend:
        print(f"  {name}\t{count} article(s)\te.g. {examples[0] if examples else ''}")
    if accept:
        new_rows = proposals.accept(reg.rows, [p[0] for p in pend], str(date.today()))
        tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS, new_rows)
        print(f"accepted {len(pend)} proposal(s) into {cfg.topics_path}; re-run materialize + verify")


def verify_problems(library=None, lang="en"):
    """Run the invariant checks against the library (defaults to cfg.corpus_path for
    the legacy single-vault mode). Returns the list of problems."""
    vault = library if library is not None else cfg.corpus_path
    rows = store.load(cfg.labels_path)
    reg = registry.load_or_empty(cfg.topics_path)
    if cfg.manifest_path.exists():
        return verify.run(rows, reg, vault, cfg.categories, cfg,
                          manifest_rows=_manifest_rows(), lang=lang)
    return verify.run(rows, reg, vault, cfg.categories, cfg, lang=lang)


def cmd_verify(library=None, lang="en"):
    problems = verify_problems(library=library, lang=lang)
    print("\n".join(problems) if problems else "all invariants green")
    print(audit.report(store.load(cfg.labels_path), cfg)["review_open"], "rows flagged for review")
    sys.exit(1 if problems else 0)


def cmd_status():
    from librarian.orchestrate import status
    print(status.render(cfg))


def cmd_audit():
    """Print the GATE 1 taxonomy audit (split/merge candidates, proposals,
    review count) — the audit report without an inline python -c."""
    rep = audit.report(store.load(cfg.labels_path), cfg,
                       reg=registry.load_or_empty(cfg.topics_path))
    print(f"category sizes: {rep['category_sizes']}")
    print(f"split candidates (> {cfg.topic_split_threshold}): {rep['split_candidates']}")
    print(f"merge candidates (< {cfg.hub_min_articles}): {rep['merge_candidates']}")
    print(f"proposals: {rep['proposals']}")
    print(f"review open: {rep['review_open']}")


def cmd_index(rebuild=False):
    """Build/refresh the semantic-search vector index (spec §5)."""
    from librarian.search import settings as ssettings, embedder as semb, indexer
    s = ssettings.from_config(cfg)
    emb = semb.OllamaEmbedder(s)
    semb.ensure_model(s)
    summary = indexer.update_index(cfg, s, emb, rebuild=rebuild)
    print(f"indexed: embedded {summary['embedded']}, deleted {summary['deleted']}, "
          f"total {summary['total']}, skipped {len(summary['skipped'])}")
    if summary["skipped"]:
        head = summary["skipped"][:5]
        more = " …" if len(summary["skipped"]) > 5 else ""
        print(f"  skipped (no url / unreadable): {head}{more}")


def _stale_count(cfg, settings):
    """Approximate count of labeled items not yet in the index: label rows minus
    indexed rows (spec §7). Heuristic — over-counts by any no-url/unreadable rows
    the indexer skips, which are rare. Cheap (no body reads)."""
    from librarian.search.index_store import IndexStore
    idx = IndexStore.open(settings.index_path)
    try:
        return max(0, len(store.load(cfg.labels_path)) - idx.count())
    finally:
        idx.close()


def cmd_search(query, limit=None, category=None, topic=None):
    """Semantic search over the library; prints ranked notes (spec §5)."""
    from librarian.search import settings as ssettings, embedder as semb, query as q
    s = ssettings.from_config(cfg)
    emb = semb.OllamaEmbedder(s)
    results = q.search(cfg, s, emb, query, limit=limit, category=category,
                       topic=topic)
    if not results:
        print("no results — is the index built? run "
              "`python -m librarian.update index`")
        return
    for r in results:
        print(f"[{r.score:.3f}] {r.title}  ·  {r.primary_category}")
        print(f"        {r.relative_path}")
        if r.summary:
            print(f"        {r.summary[:140]}")
    pending = _stale_count(cfg, s)
    if pending:
        print(f"note: ~{pending} labeled item(s) not yet indexed — run "
              f"`python -m librarian.update index` to refresh")


def _opt(flag):
    """Return the value following `flag` in argv, or None."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


if __name__ == "__main__":
    import os
    configure(config.load(os.environ.get(
        "KNOWLEDGE_LIBRARY_CONFIG", "config.yaml")))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "diff"
    if cmd == "ingest" and len(sys.argv) < 3:
        sys.exit("usage: python -m librarian.update ingest <out.tsv> [--out <library>]")
    if cmd == "search" and len(sys.argv) < 3:
        sys.exit('usage: python -m librarian.update search "<query>" '
                 '[--limit N] [--category C] [--topic T]')
    out = _opt("--out")
    lib = Path(out).expanduser() if out else None
    lang = _opt("--lang") or "en"
    limit = _opt("--limit")
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib, lang=lang),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib, lang=lang),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib),
                "status": lambda: cmd_status(),
                "audit": lambda: cmd_audit(),
                "index": lambda: cmd_index("--rebuild" in sys.argv),
                "search": lambda: cmd_search(
                    sys.argv[2], limit=int(limit) if limit else None,
                    category=_opt("--category"), topic=_opt("--topic"))}
    if cmd not in handlers:
        sys.exit(f"unknown command {cmd!r}; choose from {', '.join(handlers)}")
    handlers[cmd]()
