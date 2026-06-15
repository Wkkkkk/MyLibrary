from librarian import refile, config


def _cfg(tmp_path, categories, localization=None):
    return config.Config(
        corpus_path=tmp_path, library_path=tmp_path, data_dir=tmp_path / "d",
        categories=set(categories), label_language="en",
        category_localization=localization or {})


def lrow(rel, primary):
    return [rel, "", "", primary, "t", *[""] * 10]


def make(vault, rel):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x", encoding="utf-8")


def test_swap_between_folders(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "历史"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path, cfg)
    log = refile.apply(moves, tmp_path)
    assert (tmp_path / "历史" / "a.md").exists() and (tmp_path / "文学" / "a.md").exists()
    assert rows[0][0] == "历史/a.md" and rows[1][0] == "文学/a.md"
    assert len(log) == 2


def test_collision_gets_suffix(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    make(tmp_path, "文学/a.md"); make(tmp_path, "历史/a.md")
    rows = [lrow("文学/a.md", "文学"), lrow("历史/a.md", "文学")]
    moves = refile.plan(rows, tmp_path, cfg)
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").exists()
    assert (tmp_path / "文学" / "a_2.md").exists()


def test_in_place_no_move(tmp_path):
    cfg = _cfg(tmp_path, ["文学"])
    make(tmp_path, "文学/a.md")
    rows = [lrow("文学/a.md", "文学")]
    assert refile.plan(rows, tmp_path, cfg) == []


def test_collision_with_preexisting_offset_file(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    # 文学/a_2.md already on disk but NOT in the label set
    make(tmp_path, "历史/a.md"); make(tmp_path, "文学/a.md"); make(tmp_path, "文学/a_2.md")
    rows = [lrow("历史/a.md", "文学")]   # only this one is re-filed, into 文学
    moves = refile.plan(rows, tmp_path, cfg)
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_2.md").read_text(encoding="utf-8") == "x"
    assert (tmp_path / "文学" / "a_3.md").exists()
    assert rows[0][0] == "文学/a_3.md"


def test_resolve_name_matches_across_normalization_forms():
    import unicodedata
    nfc = unicodedata.normalize("NFC", "café.md")
    nfd = unicodedata.normalize("NFD", "café.md")
    assert nfc != nfd
    assert refile._resolve_name(nfc, [nfd, "other.md"]) == nfd
    assert refile._resolve_name(nfd, [nfc, "other.md"]) == nfc
    assert refile._resolve_name(nfc, ["other.md"]) is None


def test_lang_zh_files_into_localized_folder(tmp_path):
    # canonical category "Literature" localizes to 文学 under --lang zh
    cfg = _cfg(tmp_path, ["Literature"], {"Literature": {"zh": "文学"}})
    make(tmp_path, "inbox/a.md")
    rows = [lrow("inbox/a.md", "Literature")]
    moves = refile.plan(rows, tmp_path, cfg, lang="zh")
    refile.apply(moves, tmp_path)
    assert (tmp_path / "文学" / "a.md").exists()       # localized folder
    assert not (tmp_path / "Literature").exists()       # NOT the canonical name
    assert rows[0][0] == "文学/a.md"


def test_lang_en_files_into_canonical_folder(tmp_path):
    cfg = _cfg(tmp_path, ["Literature"], {"Literature": {"zh": "文学"}})
    make(tmp_path, "inbox/a.md")
    rows = [lrow("inbox/a.md", "Literature")]
    moves = refile.plan(rows, tmp_path, cfg, lang="en")
    refile.apply(moves, tmp_path)
    assert (tmp_path / "Literature" / "a.md").exists()   # verbatim canon
    assert rows[0][0] == "Literature/a.md"


def test_unresolved_sources_flags_missing_and_passes_present(tmp_path):
    cfg = _cfg(tmp_path, ["文学", "历史"])
    make(tmp_path, "文学/here.md")   # present on disk
    # gone.md is labeled but absent (corrupted state from a prior --out run)
    rows = [lrow("文学/here.md", "历史"), lrow("文学/gone.md", "历史")]
    moves = refile.plan(rows, tmp_path, cfg)
    assert refile.unresolved_sources(moves, tmp_path) == ["文学/gone.md"]
