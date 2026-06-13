import unicodedata

from librarian import batches

MANIFEST = [[f"文学/a{i}.md", f"a{i}", "文学", "h" * 16] for i in range(5)]
LEGACY = {"文学/a0.md": ("文学", "文学评论; 思想史")}

def test_batch_files_written(tmp_path):
    files, hits = batches.make(MANIFEST, LEGACY, tmp_path, size=2, vault="/V")
    assert [f.name for f in files] == ["batch_001.md", "batch_002.md", "batch_003.md"]
    assert hits == 1
    text = files[0].read_text(encoding="utf-8")
    assert "## Item 1" in text and "## Item 3" not in text
    assert "source_path: /V/文学/a0.md" in text
    assert "v1_reference: 文学 | 文学评论; 思想史" in text
    assert "v1_reference: none" in text  # a1 has no legacy row

def test_legacy_lookup_is_nfc_safe(tmp_path):
    # CJK ideographs are NFC/NFD-invariant, so use a kana path that actually
    # decomposes (ポ -> ホ + combining handakuten) to simulate disk/TSV drift.
    rel = "文学/ポップ.md"
    manifest = [[rel, "ポップ", "文学", "h" * 16]]
    nfd_key = unicodedata.normalize("NFD", rel)
    assert nfd_key != rel  # sanity: keys differ at the byte level
    legacy = {nfd_key: ("文学", "文学评论")}
    files, hits = batches.make(manifest, legacy, tmp_path, size=2, vault="/V")
    assert hits == 1
    text = files[0].read_text(encoding="utf-8")
    assert "v1_reference: 文学 | 文学评论" in text

def test_paths_function():
    assert batches.paths(MANIFEST, size=2)[0] == ["文学/a0.md", "文学/a1.md"]
