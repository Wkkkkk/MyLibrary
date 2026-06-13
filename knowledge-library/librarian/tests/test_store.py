from librarian import store, contract

def row(rel, primary="文学"):
    return [rel, "t", "旧", primary, "文学评论", "", "文学评论", "s",
            "high", "false", "", "", "h" * 16, "v1", "d"]

def test_merge_appends_and_replaces(tmp_path):
    p = tmp_path / "labels.tsv"
    store.merge(p, [row("a/1.md"), row("a/2.md")])
    store.merge(p, [row("a/2.md", primary="历史人文"), row("a/3.md")])
    rows = store.load(p)
    assert [r[0] for r in rows] == ["a/1.md", "a/2.md", "a/3.md"]
    assert rows[1][3] == "历史人文"

def test_delete_paths(tmp_path):
    p = tmp_path / "labels.tsv"
    store.merge(p, [row("a/1.md"), row("a/2.md")])
    store.delete(p, ["a/1.md"])
    assert [r[0] for r in store.load(p)] == ["a/2.md"]
