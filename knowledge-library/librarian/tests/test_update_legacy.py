def test_load_legacy(tmp_path):
    from librarian import update
    p = tmp_path / "v1.tsv"
    header = "relative_path\ttitle\toriginal_category\tprimary_categories\tsubcategories\tsecondary_categories\ttags\tarticle_type\tentities\tsummary\tconfidence\tneeds_review\treview_reason\tproposed_new_categories\tproposed_new_subcategories\ttaxonomy_notes"
    row = "文学/a.md\tX\t旧\t文学\t文学评论; 思想史\t\t\t\t\t\t\t\t\t\t\t"
    p.write_text(header + "\n" + row + "\n", encoding="utf-8")
    legacy = update.load_legacy(p)
    assert legacy["文学/a.md"] == ("文学", "文学评论; 思想史")


def test_load_legacy_missing(tmp_path):
    from librarian import update
    assert update.load_legacy(tmp_path / "nope.tsv") == {}
