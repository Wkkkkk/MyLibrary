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
    and hash are frozen from the manifest, original_category from legacy v1."""
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    idx = {}
    for r in manifest_rows:
        rel = unicodedata.normalize("NFC", r[0])
        v1 = legacy_nfc.get(rel)
        idx[rel] = (r[1], v1[0] if v1 else "", r[3])
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
    rows, skipped = [], []
    for jp in sorted(str(p) for p in json_paths):
        for j in json.loads(Path(jp).read_text(encoding="utf-8")):
            rel = unicodedata.normalize("NFC", j["relative_path"])
            if rel not in frozen:
                skipped.append(rel)
                continue
            rows.append(_row(j, frozen[rel], cfg, today, run_id))
    expected = [r[PATH_I] for r in rows]
    rows, errors = validate.check(rows, expected, reg, cfg.categories)
    if errors:
        return {"merged": 0, "review": 0, "errors": errors,
                "skipped": skipped, "proposals": []}
    cfg.labels_path.parent.mkdir(parents=True, exist_ok=True)
    store.merge(cfg.labels_path, rows)
    n_review = sum(1 for r in rows if r[REVIEW_I] == "true")
    validate.log_progress(cfg.progress_path, "wave", len(rows), n_review)
    pend = [p[0] for p in proposals.pending(store.load(cfg.labels_path), reg)]
    return {"merged": len(rows), "review": n_review, "errors": [],
            "skipped": skipped, "proposals": pend}


if __name__ == "__main__":
    import os
    import sys
    from datetime import date
    from librarian import config
    from librarian.update import load_legacy
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    paths = sys.argv[1:] or [str(p) for p in sorted(cfg.wave_out_dir.glob("*.json"))]
    manifest_rows = manifest.build(cfg.corpus_path, cfg)
    legacy = load_legacy(cfg.legacy_labels)
    reg = registry.load(cfg.topics_path)
    summary = ingest(paths, manifest_rows, legacy, reg, cfg, str(date.today()))
    if summary["errors"]:
        print("\n".join(summary["errors"]))
        sys.exit(1)
    print(f"merged {summary['merged']} rows · {summary['review']} flagged · "
          f"{len(summary['proposals'])} pending proposal(s) · "
          f"{len(summary['skipped'])} skipped")
