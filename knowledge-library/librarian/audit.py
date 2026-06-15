from collections import Counter
from librarian import tsv


def report(label_rows, cfg, reg=None):
    cat = Counter(r[3] for r in label_rows)
    topic = Counter(t for r in label_rows for t in tsv.split_multi(r[4]))
    proposals = Counter(t for r in label_rows for t in tsv.split_multi(r[11]))
    if reg is not None:
        # Drop proposals already promoted to active topics — once GATE 2 accepts
        # them they are no longer pending (finding #5). Mirrors proposals.pending.
        active = reg.active_names()
        proposals = Counter({t: n for t, n in proposals.items() if t not in active})
    return {
        "category_sizes": dict(cat),
        "topic_sizes": dict(topic),
        "split_candidates": sorted(t for t, n in topic.items()
                                   if n > cfg.topic_split_threshold),
        "merge_candidates": sorted(t for t, n in topic.items()
                                   if n < cfg.hub_min_articles),
        "proposals": dict(proposals),
        "review_open": sum(1 for r in label_rows if r[9] == "true"),
    }
