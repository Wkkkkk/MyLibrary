from collections import Counter
from itertools import combinations
from librarian import tsv


def weights(label_rows):
    w = Counter()
    for r in label_rows:
        for a, b in combinations(sorted(tsv.split_multi(r[4])), 2):
            w[(a, b)] += 1
    return w


def related(w, topic, k):
    scores = Counter()
    for (a, b), n in w.items():
        if a == topic:
            scores[b] = n
        elif b == topic:
            scores[a] = n
    # deterministic: weight desc, then topic name asc (Counter.most_common breaks
    # ties by insertion order, which depends on label ordering — not reproducible).
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
