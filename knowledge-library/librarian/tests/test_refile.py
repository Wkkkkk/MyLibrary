from librarian import refile

def lrow(rel, primary):
    return [rel, "", "", primary, "t", *[""] * 10]

def make(vault, rel):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")

def test_swap_between_folders(tmp_path):
    # a.md sits in 文学 but belongs to 历史; b.md (same name!) the reverse
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "历史"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path)
    log = refile.apply(moves, tmp_path)
    assert (tmp_path / "历史" / "a.md").exists() and (tmp_path / "文学" / "a.md").exists()
    assert rows[0][0] == "历史/a.md" and rows[1][0] == "文学/a.md"
    assert len(log) == 2

def test_collision_gets_suffix(tmp_path):
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "文学"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path)
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").exists()
    assert (tmp_path / "文学" / "a_2.md").exists()

def test_in_place_no_move(tmp_path):
    make(tmp_path, "文学/a.md")
    rows = [lrow("文学/a.md", "文学")]
    assert refile.plan(rows, tmp_path) == []

def test_collision_with_preexisting_offset_file(tmp_path):
    # 文学/a_2.md already on disk but NOT in the label set
    make(tmp_path, "历史/a.md"); make(tmp_path, "文学/a.md"); make(tmp_path, "文学/a_2.md")
    rows = [lrow("历史/a.md", "文学")]   # only this one is re-filed, into 文学
    moves = refile.plan(rows, tmp_path)
    refile.apply(moves, tmp_path)
    # the mover must NOT clobber the pre-existing a.md or a_2.md
    assert (tmp_path / "文学" / "a.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_2.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_3.md").exists()   # mover lands here
    assert rows[0][0] == "文学/a_3.md"

def test_resolve_name_matches_across_normalization_forms():
    import unicodedata
    # "é" composed (NFC) vs decomposed (NFD) — same string, different bytes
    nfc = unicodedata.normalize("NFC", "café.md")
    nfd = unicodedata.normalize("NFD", "café.md")
    assert nfc != nfd  # guard: the two forms really do differ as plain strings
    # looking up the NFC target against a dir that stores the NFD form must hit
    assert refile._resolve_name(nfc, [nfd, "other.md"]) == nfd
    # and vice versa
    assert refile._resolve_name(nfd, [nfc, "other.md"]) == nfc
    # no match returns None
    assert refile._resolve_name(nfc, ["other.md"]) is None
