import unicodedata
import pytest
from librarian import manifest


def make_vault(tmp_path):
    (tmp_path / "文学").mkdir()
    (tmp_path / "_images").mkdir()
    (tmp_path / "文学" / "a.md").write_text("---\ntitle: A\n---\nbody", encoding="utf-8")
    (tmp_path / "_images" / "x.md").write_text("skip me", encoding="utf-8")
    return tmp_path

def test_build_skips_non_article_dirs(tmp_path, cfg):
    rows = manifest.build(make_vault(tmp_path), cfg)
    assert [r[0] for r in rows] == ["文学/a.md"]
    assert rows[0][1] == "A" and rows[0][2] == "文学" and len(rows[0][3]) == 16

def test_build_bad_encoding_names_file(tmp_path, cfg):
    vault = make_vault(tmp_path)
    bad = vault / "文学" / "bad.md"
    bad.write_bytes(b"\xff\xfe invalid utf-8 \x80")
    with pytest.raises(ValueError, match="bad.md"):
        manifest.build(vault, cfg)

def test_build_nfc_normalizes_paths(tmp_path, cfg):
    nfc = "文学/café.md"                       # é composed (NFC)
    nfd = unicodedata.normalize("NFD", nfc)
    f = tmp_path / nfd
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("---\ntitle: X\n---\nbody\n", encoding="utf-8")
    rows = manifest.build(tmp_path, cfg)
    paths = [r[0] for r in rows]
    assert nfc in paths
    assert nfd not in paths or nfc == nfd

def test_build_extracts_source_category_frontmatter(tmp_path, cfg):
    # The source `category:` frontmatter is the article's original (e.g. legacy
    # mybooks) category — distinct from both the containing folder and the
    # eventual primary_category. Captured as the manifest's last column so it can
    # seed original_category on a fresh ingest (finding #3).
    (tmp_path / "文学").mkdir()
    (tmp_path / "文学" / "a.md").write_text(
        '---\ntitle: A\ncategory: "职场与成长"\n---\nbody', encoding="utf-8")
    (tmp_path / "文学" / "b.md").write_text(
        "---\ntitle: B\n---\nbody", encoding="utf-8")     # no category frontmatter
    rows = {r[0]: r for r in manifest.build(tmp_path, cfg)}
    oc = manifest.contract.MANIFEST_COLUMNS.index("original_category")
    assert rows["文学/a.md"][oc] == "职场与成长"
    assert rows["文学/b.md"][oc] == ""


def test_diff(tmp_path, cfg):
    vault = make_vault(tmp_path)
    old = manifest.build(vault, cfg)
    (vault / "文学" / "a.md").write_text("---\ntitle: A\n---\nCHANGED", encoding="utf-8")
    (vault / "文学" / "b.md").write_text("---\ntitle: B\n---\n.", encoding="utf-8")
    new = manifest.build(vault, cfg)
    added, changed, deleted = manifest.diff(old, new)
    assert added == ["文学/b.md"] and changed == ["文学/a.md"] and deleted == []
