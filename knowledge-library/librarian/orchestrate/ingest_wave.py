"""Collect one wave's labeling output (spec §5 step 3): read the agent-written
JSON files, reconstruct full label rows using the FROZEN manifest fields (title,
content_hash) + legacy original_category — agents never supply those, so they
can't fabricate them — validate against the canon, and merge into the labels
store. Proposed topics are recorded (validate accepts them) but NOT promoted
here; promotion stays a deliberate gate action (proposals.accept, GATE 2)."""
import json
import unicodedata
from pathlib import Path
from librarian import (contract, tsv, manifest, registry, validate, store,
                       proposals)

PATH_I = contract.LABEL_COLUMNS.index("relative_path")
REVIEW_I = contract.LABEL_COLUMNS.index("needs_review")


def _multi(v):
    """Agent JSON gives topics/tags/proposed as a list; join to the TSV form
    (deduped, '; '-separated). A bare string is passed through trimmed."""
    if isinstance(v, list):
        return tsv.join_multi([str(x).strip() for x in v if str(x).strip()])
    return str(v).strip()


def _frozen_index(manifest_rows, legacy):
    """{NFC relative_path: (title, original_category, content_hash)}; the title
    and hash are frozen from the manifest. original_category prefers the legacy
    v1 mapping, falling back to the manifest's source `category:` column
    (finding #3) so a fresh ingest is not left blank."""
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    cat_i = contract.MANIFEST_COLUMNS.index("original_category")
    idx = {}
    for r in manifest_rows:
        rel = unicodedata.normalize("NFC", r[0])
        v1 = legacy_nfc.get(rel)
        manifest_cat = r[cat_i] if len(r) > cat_i else ""
        idx[rel] = (r[1], v1[0] if v1 else manifest_cat, r[3])
    return idx


def _row(j, frozen, cfg, today, run_id):
    """One full LABEL_COLUMNS row from an agent judgment object `j` and the
    frozen (title, original_category, content_hash) tuple."""
    title, original_category, content_hash = frozen
    return [
        unicodedata.normalize("NFC", j["relative_path"]),
        title,
        original_category,
        str(j.get("primary_category", "")).strip(),
        _multi(j.get("topics", [])),
        _multi(j.get("tags", [])),
        str(j.get("article_type", "")).strip(),
        str(j.get("summary", "")).strip(),
        str(j.get("confidence", "")).strip(),
        "true" if j.get("needs_review") else "false",
        str(j.get("review_reason", "")).strip(),
        _multi(j.get("proposed_topics", [])),
        content_hash,
        cfg.extractor_version,
        today,
        run_id,
    ]


def ingest(json_paths, manifest_rows, legacy, reg, cfg, today, run_id=""):
    """Read agent JSON outputs and merge validated rows into cfg.labels_path,
    stamping each row's first_seen_run with `run_id` (spec §9 provenance).
    Rows whose path is not in the manifest are skipped (fabricated). On ANY
    validation error nothing is written. Returns a summary dict:
      {"merged", "review", "errors": [...], "skipped": [...], "proposals": [...]}
    """
    frozen = _frozen_index(manifest_rows, legacy)
    rows, skipped, parse_errors = [], [], []
    for jp in sorted(str(p) for p in json_paths):
        try:
            data = json.loads(Path(jp).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            parse_errors.append(f"{jp}: invalid JSON ({e})")
            continue
        if not isinstance(data, list):
            parse_errors.append(
                f"{jp}: expected a JSON array, got {type(data).__name__}")
            continue
        for j in data:
            if not isinstance(j, dict) or not j.get("relative_path"):
                parse_errors.append(f"{jp}: item missing 'relative_path'")
                continue
            rel = unicodedata.normalize("NFC", j["relative_path"])
            if rel not in frozen:
                skipped.append(rel)
                continue
            rows.append(_row(j, frozen[rel], cfg, today, run_id))
    if parse_errors:
        return {"merged": 0, "review": 0, "errors": parse_errors,
                "skipped": skipped, "proposals": []}
    expected = [r[PATH_I] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        return {"merged": 0, "review": 0, "errors": errors,
                "skipped": skipped, "proposals": []}
    store.merge(cfg.labels_path, rows)
    n_review = sum(1 for r in rows if r[REVIEW_I] == "true")
    validate.log_progress(cfg.progress_path, "wave", len(rows), n_review)
    pend = [p[0] for p in proposals.pending(store.load(cfg.labels_path), reg)]
    return {"merged": len(rows), "review": n_review, "errors": [],
            "skipped": skipped, "proposals": pend}


def run(cfg, paths=None, today=None, run_id=""):
    """Wire one wave's ingest from config (the CLI entry point). The canon may
    not exist yet during bootstrap, so load_or_empty (finding #2)."""
    from datetime import date
    from librarian.update import load_legacy   # function-local: avoids import cycle
    if paths is None:
        paths = [str(p) for p in sorted(cfg.wave_out_dir.glob("*.json"))]
    manifest_rows = manifest.build(cfg.corpus_path, cfg)
    legacy = load_legacy(cfg.legacy_labels)
    reg = registry.load_or_empty(cfg.topics_path)
    return ingest(paths, manifest_rows, legacy, reg, cfg,
                  today or str(date.today()), run_id=run_id)


if __name__ == "__main__":
    import os
    import sys
    from librarian import config
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    paths = sys.argv[1:] or None
    summary = run(cfg, paths)
    if summary["errors"]:
        print("\n".join(summary["errors"]))
        sys.exit(1)
    print(f"merged {summary['merged']} rows · {summary['review']} flagged · "
          f"{len(summary['proposals'])} pending proposal(s) · "
          f"{len(summary['skipped'])} skipped")
