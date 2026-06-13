import re
import unicodedata

from librarian import tsv, contract


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def run(label_rows, reg, vault, categories, cfg, manifest_rows=None):
    problems = []
    labeled = set()
    active = reg.active_names()
    for r in label_rows:
        if len(r) != len(contract.LABEL_COLUMNS):
            problems.append(f"{r[0]}: bad field count {len(r)}")
            continue
        rel = _nfc(r[0])
        if rel in labeled:
            problems.append(f"duplicate label row: {rel}")
        labeled.add(rel)
        if r[3] not in categories:
            problems.append(f"{rel}: primary off canon {r[3]!r}")
        topics = tsv.split_multi(r[4])
        if not topics:
            problems.append(f"{rel}: no topics")
        for t in topics:
            if t not in active:
                problems.append(f"{rel}: topic not active in registry: {t!r}")
        if r[8] not in contract.CONFIDENCE:
            problems.append(f"{rel}: bad confidence {r[8]!r}")
        if r[9] not in contract.BOOL:
            problems.append(f"{rel}: bad needs_review {r[9]!r}")
        if rel.split("/")[0] != r[3]:
            problems.append(f"{rel}: folder != primary {r[3]!r}")
    disk = set()
    for d in sorted(p for p in vault.iterdir() if p.is_dir()):
        if d.name in cfg.skip_dirs:
            continue
        for f in d.glob("*.md"):
            disk.add(_nfc(f"{d.name}/{f.name}"))
    for p in sorted(disk - labeled):
        problems.append(f"on disk but unlabeled (ghost): {p}")
    for p in sorted(labeled - disk):
        problems.append(f"labeled but missing on disk: {p}")

    # INVARIANT A: manifest leg of the three-way closure
    if manifest_rows is not None:
        man = {_nfc(r[0]) for r in manifest_rows}
        for p in sorted(man - labeled):
            problems.append(f"in manifest but unlabeled: {p}")
        for p in sorted(labeled - man):
            problems.append(f"labeled but not in manifest: {p}")

    # INVARIANTS B & C: hub note checks
    hub_dir = vault / cfg.hub_dir
    if hub_dir.is_dir():
        # expected hubs: active topics with >= hub_min_articles articles
        counts = {}
        topics_by_article = []
        for r in label_rows:
            ts = tsv.split_multi(r[4])
            topics_by_article.append((r, ts))
            for t in ts:
                counts[_nfc(t)] = counts.get(_nfc(t), 0) + 1
        active_nfc = {_nfc(n) for n in active}
        expected = {t for t, c in counts.items()
                    if c >= cfg.hub_min_articles and t in active_nfc}
        for f in sorted(hub_dir.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            if cfg.generated_marker not in text:
                continue
            stem = _nfc(f.stem)
            if stem not in expected:
                problems.append(
                    f"orphaned hub note (topic not active/below threshold): {stem}")
                continue
            # INVARIANT C: reading-list matches the TSV
            links = {_nfc(m) for m in
                     re.findall(r'^- \[\[(.+)\]\](?= —|$)', text, re.M)}
            exp_basenames = set()
            for r, ts in topics_by_article:
                if stem in {_nfc(t) for t in ts}:
                    base = r[0].rsplit("/", 1)[-1]
                    if base.endswith(".md"):
                        base = base[:-3]
                    exp_basenames.add(_nfc(base))
            if links != exp_basenames:
                extra = links - exp_basenames
                missing = exp_basenames - links
                problems.append(
                    f"hub list mismatch for {stem}: "
                    f"+{sorted(extra)} -{sorted(missing)}")

    return problems
