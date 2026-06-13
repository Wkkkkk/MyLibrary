from librarian import localize, config, registry, tsv, contract


def _cfg(tmp_path, localization=None):
    return config.Config(
        corpus_path=tmp_path / "v", library_path=tmp_path / "v",
        data_dir=tmp_path / "d", categories={"Literature"},
        label_language="en", category_localization=localization or {})


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Machine Learning", "", "", "active", "", "", "机器学习"],
                    ["T2", "Robotics", "", "", "active", "", "", ""]])  # no name_zh
    return registry.load(p)


def test_headers_en_are_english():
    h = localize.headers("en")
    assert h["reading_list"] == "Reading list"
    assert h["related"] == "Related topics"
    assert h["parent"] == "Parent topic"
    assert h["children"] == "Subtopics"


def test_headers_zh_are_chinese():
    h = localize.headers("zh")
    assert h["reading_list"] == "阅读清单"
    assert h["related"] == "相关话题"
    assert h["parent"] == "父话题"
    assert h["children"] == "子话题"


def test_headers_unknown_lang_falls_back_to_english():
    assert localize.headers("fr") == localize.headers("en")


def test_topic_name_canon_lang_returns_verbatim(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Machine Learning", "en") == "Machine Learning"


def test_topic_name_zh_uses_name_zh_column(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Machine Learning", "zh") == "机器学习"


def test_topic_name_zh_falls_back_to_canon_when_no_name_zh(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Robotics", "zh") == "Robotics"


def test_topic_name_unknown_topic_returns_input(tmp_path):
    cfg = _cfg(tmp_path)
    reg = _reg(tmp_path)
    assert localize.topic_name(cfg, reg, "Nonexistent", "zh") == "Nonexistent"
