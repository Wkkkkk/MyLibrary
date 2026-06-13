import unicodedata


def paths(manifest_rows, size):
    ps = [r[0] for r in manifest_rows]
    return [ps[i:i + size] for i in range(0, len(ps), size)]


def make(manifest_rows, legacy, out_dir, size, vault):
    """Write batch files; returns (files, hit_count) where hit_count is the
    number of items that matched a legacy row. Lookup keys are normalized to
    NFC on both sides so CJK NFC/NFD drift between TSV and disk cannot
    silently zero out v1 references."""
    out_dir.mkdir(parents=True, exist_ok=True)
    legacy_nfc = {unicodedata.normalize("NFC", k): v for k, v in legacy.items()}
    files = []
    hit_count = 0
    chunks = [manifest_rows[i:i + size] for i in range(0, len(manifest_rows), size)]
    for n, chunk in enumerate(chunks, start=1):
        lines = [f"# knowledge-library Labeling Batch {n:03d} / {len(chunks)}\n",
                 "Use rules/taxonomy_rules.md. Read each article's FULL text at source_path.\n"]
        for j, r in enumerate(chunk, start=1):
            rel, title = r[0], r[1]
            v1 = legacy_nfc.get(unicodedata.normalize("NFC", rel))
            if v1:
                hit_count += 1
            ref = f"{v1[0]} | {v1[1]}" if v1 else "none"
            lines += [f"\n## Item {j}\n",
                      f"relative_path: {rel}\n",
                      f"title: {title}\n",
                      f"source_path: {vault}/{rel}\n",
                      f"v1_reference: {ref}\n"]
        p = out_dir / f"batch_{n:03d}.md"
        p.write_text("".join(lines), encoding="utf-8")
        files.append(p)
    return files, hit_count
