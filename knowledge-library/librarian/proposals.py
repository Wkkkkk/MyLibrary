"""Proposal triage.

`ingest` accepts a topic value if it is declared in that row's proposed_topics,
but `verify` requires every topic to resolve to an ACTIVE registry entry. These
helpers aggregate pending proposals for a human decision pass and promote the
accepted ones into the topic registry as active entries.
"""
from librarian import tsv, contract

PROPOSED_I = contract.LABEL_COLUMNS.index("proposed_topics")
TITLE_I = contract.LABEL_COLUMNS.index("title")


def pending(label_rows, reg):
    """Aggregate proposed_topics that are not yet active in the registry.

    Returns [(name, count, [example_titles]), ...] sorted by count desc, name asc.
    """
    active = reg.active_names()
    agg = {}
    for r in label_rows:
        for name in tsv.split_multi(r[PROPOSED_I]):
            if name in active:
                continue
            agg.setdefault(name, []).append(r[TITLE_I])
    out = [(name, len(titles), titles) for name, titles in agg.items()]
    out.sort(key=lambda t: (-t[1], t[0]))
    return out


def _next_id(reg_rows):
    n = 0
    for r in reg_rows:
        tid = r[0]
        if tid[:1] == "T" and tid[1:].isdigit():
            n = max(n, int(tid[1:]))
    return n + 1


def accept(reg_rows, names, created_at):
    """Return reg_rows plus one active row per name not already present (by name).

    Mints sequential T#### ids continuing from the existing maximum.
    """
    existing = {r[1] for r in reg_rows}
    rows = [list(r) for r in reg_rows]
    nid = _next_id(reg_rows)
    for name in names:
        if name in existing:
            continue
        existing.add(name)
        row = [""] * len(contract.TOPIC_COLUMNS)
        row[0], row[1], row[4], row[6] = f"T{nid:04d}", name, "active", created_at
        nid += 1
        rows.append(row)
    return rows
