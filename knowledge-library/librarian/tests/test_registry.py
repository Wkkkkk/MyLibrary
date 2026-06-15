import pytest
from librarian import registry, tsv, contract

def write_topics(tmp_path, rows):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, rows)
    return p

GOOD = [
    ["T0001", "制度经济学", "institutional economics", "经济学", "active", "", "2026-06-11", ""],
    ["T0002", "经济学", "", "", "active", "", "2026-06-11", ""],
    ["T0003", "旧名", "", "", "merged", "", "2026-06-11", ""],
]

def test_load_and_resolve(tmp_path):
    reg = registry.load(write_topics(tmp_path, GOOD))
    assert reg.resolve("制度经济学") == "制度经济学"
    assert reg.resolve("institutional economics") == "制度经济学"
    assert reg.resolve("nope") is None
    assert reg.active_names() == {"制度经济学", "经济学"}

def test_duplicate_name_rejected(tmp_path):
    rows = GOOD + [["T0004", "制度经济学", "", "", "active", "", "2026-06-11", ""]]
    with pytest.raises(ValueError, match="duplicate"):
        registry.load(write_topics(tmp_path, rows))

def test_merged_name_redirects_via_alias(tmp_path):
    rows = [
        ["T0001", "制度经济学", "旧名", "", "active", "", "2026-06-11", ""],
        ["T0002", "旧名", "", "", "merged", "", "2026-06-11", ""],
    ]
    reg = registry.load(write_topics(tmp_path, rows))  # must load fine
    assert reg.resolve("旧名") == "制度经济学"

def test_merged_name_without_redirect_resolves_to_none(tmp_path):
    reg = registry.load(write_topics(tmp_path, GOOD))
    assert reg.resolve("旧名") is None

def test_alias_colliding_with_active_name_rejected(tmp_path):
    rows = [
        ["T0001", "制度经济学", "经济学", "", "active", "", "2026-06-11", ""],
        ["T0002", "经济学", "", "", "active", "", "2026-06-11", ""],
    ]
    with pytest.raises(ValueError, match="duplicate"):
        registry.load(write_topics(tmp_path, rows))

def test_parent_cycle_rejected(tmp_path):
    rows = [["T0001", "甲", "", "乙", "active", "", "", ""],
            ["T0002", "乙", "", "甲", "active", "", "", ""]]
    with pytest.raises(ValueError, match="cycle"):
        registry.load(write_topics(tmp_path, rows))

def test_unknown_parent_rejected(tmp_path):
    rows = [["T0001", "甲", "", "不存在", "active", "", "", ""]]
    with pytest.raises(ValueError, match="parent"):
        registry.load(write_topics(tmp_path, rows))

def test_load_or_empty_missing_file_returns_empty_registry(tmp_path):
    # Bootstrap: the canon doesn't exist until the first proposals are accepted.
    reg = registry.load_or_empty(tmp_path / "does_not_exist.tsv")
    assert reg.active_names() == set()
    assert reg.resolve("anything") is None

def test_load_or_empty_existing_file_loads_normally(tmp_path):
    reg = registry.load_or_empty(write_topics(tmp_path, GOOD))
    assert reg.active_names() == {"制度经济学", "经济学"}
