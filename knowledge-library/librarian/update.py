"""Incremental update orchestrator.

  python3 -m librarian.update diff
  python3 -m librarian.update queue
  python3 -m librarian.update ingest F
  python3 -m librarian.update materialize [--write]
  python3 -m librarian.update verify
  python3 -m librarian.update status
"""
import shutil
import sys
from datetime import date
from pathlib import Path
from librarian import (config, contract, tsv, manifest, registry, batches,
                       validate, store, hubgen, frontmatter, refile, verify,
                       audit, proposals)

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
    Returns {} if the file is missing. v1 schema differs from mybooks, so this
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
    reg = registry.load(cfg.topics_path)
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
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if out is not None and out != cfg.corpus_path:
        return _materialize_to_library(rows, reg, out, write, lang)
    moves = refile.plan(rows, cfg.corpus_path, cfg, lang)
    plans = hubgen.plan(rows, reg, cfg.corpus_path, cfg, lang)
    print(f"would move {len(moves)} files, write {len(plans)} hub notes")
    if not write:
        print("dry run; pass --write")
        return
    move_log = refile.apply(moves, cfg.corpus_path)
    if move_log:
        log_path = cfg.migration_log_path
        tsv.write_rows(log_path, ["old_path", "new_path"], [list(m) for m in move_log])
        # refile.apply mutated each moved row's path in place; drop the stale
        # old-path rows so store.merge below can't leave duplicates behind.
        store.delete(cfg.labels_path, [old for old, _ in move_log])
        print(f"wrote {len(move_log)} moves to {log_path}")
    skipped = hubgen.apply(plans, cfg.corpus_path, cfg)
    stats = {}
    for r in rows:
        res = frontmatter.apply(cfg.corpus_path / r[0], r)
        stats[res] = stats.get(res, 0) + 1
    store.merge(cfg.labels_path, rows)
    # files moved on disk; rebuild the manifest so it matches the new layout.
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))
    print("frontmatter:", stats, "| hub notes skipped (hand-edited):", skipped)


def _free_dest(library, primary, base, url, taken):
    """Pick library-relative path <primary>/<base>, appending _N to dodge a
    title collision with a DIFFERENT article (different url) — never overwriting
    it. A slot already holding this same article (same url) is reused."""
    stem, ext = Path(base).stem, Path(base).suffix
    rel = f"{primary}/{base}"
    n = 2
    while rel in taken or (
        (library / rel).exists() and manifest.read_url(library / rel) != url
    ):
        rel = f"{primary}/{stem}_{n}{ext}"
        n += 1
    return rel


def _materialize_to_library(rows, reg, library, write, lang="en"):
    """Materialize labels into a separate library vault (e.g. 知乎收藏_v2).

    Each labeled article is copied from the inbox (cfg.corpus_path) into
    library/<primary_category>/, frontmatter + hub notes are written there, and
    the inbox original is removed (move semantics). Idempotent: on a re-run the
    inbox source is already gone, so it just refreshes the library in place.
    The labels TSV and manifest become library-relative.

    Single display language per library: `lang` must match the language used on
    the initial materialize — the idempotent re-run path keeps each article at
    its already-localized path, so switching lang on a populated library would
    leave folders disagreeing with their canonical primary_category.
    """
    src_paths = [r[0] for r in rows]
    if not write:
        plans = hubgen.plan(rows, reg, library, cfg, lang)
        print(f"would copy {len(rows)} files into {library}, write {len(plans)} hub notes")
        print("dry run; pass --write")
        return
    taken = set()
    for r in rows:
        src = cfg.corpus_path / r[0]
        if not src.exists() and (library / r[0]).exists():
            dst_rel = r[0]  # idempotent re-run: already at its final library path
        else:
            dst_rel = _free_dest(library, cfg.localize_category(r[3], lang),
                                 r[0].rsplit("/", 1)[-1],
                                 manifest.read_url(src), taken)
        taken.add(dst_rel)
        dst = library / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
            src.unlink()
        else:
            assert dst.exists(), (r[0], dst_rel)
        r[0] = dst_rel
    plans = hubgen.plan(rows, reg, library, cfg, lang)  # plan against the final paths
    skipped = hubgen.apply(plans, library, cfg)
    stats = {}
    for r in rows:
        res = frontmatter.apply(library / r[0], r)
        stats[res] = stats.get(res, 0) + 1
    store.delete(cfg.labels_path, src_paths)   # drop inbox-keyed rows
    store.merge(cfg.labels_path, rows)         # re-add at library paths
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(library, cfg))
    print(f"copied into {library}:", stats, "| hub notes skipped:", skipped)


def cmd_proposals(accept=False):
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
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
    reg = registry.load(cfg.topics_path)
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
    from librarian import status
    print(status.render(cfg))


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
    out = _opt("--out")
    lib = Path(out).expanduser() if out else None
    lang = _opt("--lang") or "en"
    handlers = {"diff": lambda: cmd_diff(library=lib),
                "queue": lambda: cmd_queue(library=lib),
                "verify": lambda: cmd_verify(library=lib, lang=lang),
                "materialize": lambda: cmd_materialize("--write" in sys.argv, out=lib, lang=lang),
                "proposals": lambda: cmd_proposals("--accept" in sys.argv),
                "ingest": lambda: cmd_ingest(sys.argv[2], library=lib),
                "status": lambda: cmd_status()}
    if cmd not in handlers:
        sys.exit(f"unknown command {cmd!r}; choose from {', '.join(handlers)}")
    handlers[cmd]()
