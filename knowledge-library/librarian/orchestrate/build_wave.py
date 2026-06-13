"""Build one labeling wave (spec §5 step 3): select the next slice of unlabeled
articles, split them across N agents, and write one assignment file per agent
embedding the active topic canon. The parallel dispatch + JSON write is done by
the orchestrating skill (dispatching-parallel-agents); this module only prepares
the assignments — ingest_wave later collects the results."""
import unicodedata
from librarian import manifest, registry, store


def select(manifest_rows, labeled_paths, limit):
    """The first `limit` manifest rows whose relative_path is not yet labeled.
    Paths are NFC-normalized on both sides so CJK NFC/NFD drift can't leak an
    already-labeled article back into a wave."""
    done = {unicodedata.normalize("NFC", p) for p in labeled_paths}
    todo = [r for r in manifest_rows
            if unicodedata.normalize("NFC", r[0]) not in done]
    return todo[:limit]


def assignments(rows, n_agents):
    """Split rows into n_agents near-even contiguous slices (earlier slices may
    be one longer). Empty slices are dropped."""
    if n_agents < 1:
        raise ValueError("n_agents must be >= 1")
    per = -(-len(rows) // n_agents)  # ceil
    slices = [rows[i:i + per] for i in range(0, len(rows), per)] if per else []
    return [s for s in slices if s]


def canon_line(reg):
    """Semicolon-joined active topic names, for embedding in the agent prompt."""
    return "; ".join(sorted(reg.active_names()))


def _agent_file(wave_no, agent_no, rows, legacy_nfc, canon, vault):
    out = [f"# Labeling — wave {wave_no}, agent {agent_no} ({len(rows)} articles)\n",
           "Read each article's FULL text at source_path. Classify into the "
           "active canon below; propose new topics (in the canon language) only "
           "when nothing fits. Write the summary in the article's own language.\n",
           f"\nActive topics: {canon or '(none yet — seed the canon)'}\n"]
    for j, r in enumerate(rows, start=1):
        rel, title = r[0], r[1]
        v1 = legacy_nfc.get(unicodedata.normalize("NFC", rel))
        ref = f"{v1[0]} | {v1[1]}" if v1 else "none"
        out += [f"\n## Article {j}\n",
                f"relative_path\t{rel}\n",
                f"title\t{title}\n",
                f"original_category\t{v1[0] if v1 else ''}\n",
                f"content_hash\t{r[3]}\n",
                f"source_path\t{vault}/{rel}\n",
                f"v1_reference\t{ref}\n"]
    return "".join(out)


def build(manifest_rows, labeled_paths, reg, legacy, out_dir, vault, cfg, wave_no):
    """Write one assignment .md per agent into out_dir. Wave size =
    cfg.agents_per_wave * cfg.articles_per_agent. Returns (files, canon)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    limit = cfg.agents_per_wave * cfg.articles_per_agent
    rows = select(manifest_rows, labeled_paths, limit)
    canon = canon_line(reg)
    files = []
    for ai, slice_rows in enumerate(assignments(rows, cfg.agents_per_wave), start=1):
        p = out_dir / f"wave{wave_no:02d}_agent{ai}.md"
        p.write_text(_agent_file(wave_no, ai, slice_rows, legacy_nfc, canon, vault),
                     encoding="utf-8")
        files.append(p)
    return files, canon


if __name__ == "__main__":
    import os
    import sys
    from librarian import config
    from librarian.update import load_legacy
    cfg = config.load(os.environ.get("KNOWLEDGE_LIBRARY_CONFIG", "config.yaml"))
    wave_no = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    manifest_rows = manifest.build(cfg.corpus_path, cfg)
    labeled = [r[0] for r in store.load(cfg.labels_path)]
    reg = registry.load(cfg.topics_path)
    legacy = load_legacy(cfg.legacy_labels)
    files, canon = build(manifest_rows, labeled, reg, legacy,
                         cfg.wave_assign_dir, cfg.corpus_path, cfg, wave_no)
    print(f"wave {wave_no}: wrote {len(files)} agent assignment(s) "
          f"to {cfg.wave_assign_dir}; have agents write JSON to {cfg.wave_out_dir}")
