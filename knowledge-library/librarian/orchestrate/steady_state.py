"""Steady-state run orchestration (spec §7): the DETERMINISTIC glue around the
external steps. The zhihu-fetcher and the parallel LLM labeling live in the
schedule wrapper / SKILL, not here. `diff_new` finds net-new inbox articles by
url; `finish` runs the tail (ingest the labeled wave -> materialize into the
library -> verify) and appends one run-ledger row; `record_nothing_new` logs a
zero-cost empty pull. Each path returns (run_row, digest)."""
from librarian import (contract, tsv, manifest, registry, store, ledger, verify)
from librarian.orchestrate import ingest_wave, materialize


def diff_new(cfg, library):
    """Inbox articles whose stable url is not yet in `library` (net-new). Keyed
    by url so a re-fetch (same url, new bytes) is not treated as new — mirrors
    update's two-vault diff."""
    known = {u for u in (manifest.read_url(library / r[0])
                         for r in store.load(cfg.labels_path)) if u}
    new = []
    for r in manifest.build(cfg.corpus_path, cfg):
        url = manifest.read_url(cfg.corpus_path / r[0])
        if url is None or url not in known:
            new.append(r)
    return new


def _row(run_id, started_at, finished_at, source, fetched, new, labeled,
         proposed, flagged, status, lang):
    return [run_id, started_at, finished_at, source, str(fetched), str(new),
            str(labeled), str(proposed), str(flagged), status, lang]


def record_nothing_new(cfg, *, run_id, started_at, finished_at, source="zhihu",
                       fetched=0, lang="en"):
    """Append a `nothing_new` run row — a clean empty pull, no LLM spend."""
    row = _row(run_id, started_at, finished_at, source, fetched, 0, 0, 0, 0,
               "nothing_new", lang)
    ledger.append(cfg.runs_path, row)
    return row, ledger.digest(row)


def finish(cfg, library, json_paths, *, run_id, started_at, finished_at, today,
           source="zhihu", fetched=0, new=0, lang="en"):
    """The deterministic tail of a steady-state run: ingest the labeled wave
    (rows stamped with run_id), materialize into `library`, verify, and append a
    run row. On an ingest error nothing is materialized and the row is `error`.
    Returns (run_row, digest)."""
    reg = registry.load(cfg.topics_path)
    inbox_manifest = manifest.build(cfg.corpus_path, cfg)
    from librarian.update import load_legacy
    legacy = load_legacy(cfg.legacy_labels)
    summary = ingest_wave.ingest(json_paths, inbox_manifest, legacy, reg, cfg,
                                 today, run_id=run_id)
    if summary["errors"]:
        row = _row(run_id, started_at, finished_at, source, fetched, new, 0, 0,
                   0, "error", lang)
        ledger.append(cfg.runs_path, row)
        return row, ledger.digest(row)
    materialize.materialize(cfg, write=True, out=library, lang=lang)
    man_rows = None
    if cfg.manifest_path.exists():
        _header, man_rows = tsv.read_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS)
    problems = verify.run(store.load(cfg.labels_path), registry.load(cfg.topics_path),
                          library, cfg.categories, cfg, manifest_rows=man_rows, lang=lang)
    status = "ok" if not problems else "error"
    row = _row(run_id, started_at, finished_at, source, fetched, new,
               summary["merged"], len(summary["proposals"]), summary["review"],
               status, lang)
    ledger.append(cfg.runs_path, row)
    return row, ledger.digest(row)
