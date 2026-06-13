"""Materialize labeled articles into a browsable vault (spec §5 step 8): refile
into <primary_category>/ folders, write topic hub notes, apply managed
frontmatter, and rebuild the manifest. `lang` selects the display language for
folders / hub names / headers (spec §4b). Extracted from update.py so the CLI
and steady_state share one implementation; cfg is passed explicitly."""
import shutil
from pathlib import Path
from librarian import (contract, tsv, manifest, registry, store, hubgen,
                       frontmatter, refile)


def materialize(cfg, write=False, out=None, lang="en"):
    rows = store.load(cfg.labels_path)
    reg = registry.load(cfg.topics_path)
    if out is not None and out != cfg.corpus_path:
        return _to_library(cfg, rows, reg, out, write, lang)
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
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS,
                   manifest.build(cfg.corpus_path, cfg))
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


def _to_library(cfg, rows, reg, library, write, lang="en"):
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
