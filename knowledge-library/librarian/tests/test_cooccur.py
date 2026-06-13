from librarian import cooccur

LABELS = [["a", "", "", "文学", "文学评论; 思想史", *[""] * 10],
          ["b", "", "", "文学", "文学评论; 思想史", *[""] * 10],
          ["c", "", "", "历史", "思想史; 文化史", *[""] * 10]]

def test_weights():
    w = cooccur.weights(LABELS)
    assert w[("思想史", "文学评论")] == 2
    assert w[("思想史", "文化史")] == 1
    assert ("文学评论", "思想史") not in w  # keys are sorted pairs

def test_related():
    w = cooccur.weights(LABELS)
    assert cooccur.related(w, "思想史", k=5) == [("文学评论", 2), ("文化史", 1)]


def test_related_breaks_ties_by_name_independent_of_insertion_order():
    from collections import Counter
    # three topics co-occur with T at equal weight, inserted out of name order
    w = Counter({("T", "B"): 1, ("A", "T"): 1, ("T", "C"): 1})
    assert cooccur.related(w, "T", k=8) == [("A", 1), ("B", 1), ("C", 1)]
