from collections import Counter
from librarian import tsv


def report(label_rows, cfg):
    cat = Counter(r[3] for r in label_rows)
    topic = Counter(t for r in label_rows for t in tsv.split_multi(r[4]))
    proposals = Counter(t for r in label_rows for t in tsv.split_multi(r[11]))
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
