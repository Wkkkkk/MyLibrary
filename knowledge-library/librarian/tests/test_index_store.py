import numpy as np
from librarian.search.index_store import IndexStore


def _rec(url, h, vec):
    return {"url": url, "relative_path": f"文学/{url}.md", "title": f"t-{url}",
            "summary": "s", "primary_category": "文学", "topics": "a; b",
            "content_hash": h, "vector": vec}


def test_upsert_roundtrip_and_matrix_order(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("b", "h2", [0.0, 1.0]), _rec("a", "h1", [1.0, 0.0])])
    metas, matrix = store.load_matrix()
    assert [m["url"] for m in metas] == ["a", "b"]      # ordered by url
    assert matrix.shape == (2, 2)
    assert matrix.dtype == np.float32
    np.testing.assert_allclose(matrix[0], [1.0, 0.0])
    assert metas[0]["primary_category"] == "文学"
    assert store.count() == 2


def test_upsert_updates_in_place(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("a", "h1", [1.0, 0.0])])
    store.upsert([_rec("a", "h2", [0.0, 1.0])])
    assert store.count() == 1
    assert store.hashes() == {"a": "h2"}
    _, matrix = store.load_matrix()
    np.testing.assert_allclose(matrix[0], [0.0, 1.0])


def test_delete_and_empty_matrix(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    store.upsert([_rec("a", "h1", [1.0, 0.0])])
    store.delete(["a"])
    metas, matrix = store.load_matrix()
    assert metas == []
    assert matrix.shape == (0, 0)


def test_meta_roundtrip(tmp_path):
    store = IndexStore.open(tmp_path / "idx.db")
    assert store.get_meta("embed_model") is None
    store.set_meta("embed_model", "qwen3-embedding")
    store.set_meta("embed_model", "qwen3-embedding:4b")   # upsert
    assert store.get_meta("embed_model") == "qwen3-embedding:4b"


def test_persists_across_reopen(tmp_path):
    p = tmp_path / "idx.db"
    s1 = IndexStore.open(p); s1.upsert([_rec("a", "h1", [1.0, 0.0])]); s1.close()
    s2 = IndexStore.open(p)
    assert s2.count() == 1
