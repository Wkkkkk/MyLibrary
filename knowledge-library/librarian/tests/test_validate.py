from librarian import validate, registry, tsv, contract

REG_ROWS = [["T0001", "文学评论", "", "", "active", "", "", ""],
            ["T0002", "思想史", "", "", "active", "", "", ""]]

def reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, REG_ROWS)
    return registry.load(p)

def row(rel="文学/a.md", primary="文学", topics="文学评论", proposed="",
        conf="high", review="false"):
    return [rel, "t", "旧类", primary, topics, "tag1", "文学评论", "摘要。",
            conf, review, "", proposed, "h" * 16, "v1", "2026-06-11", ""]

def test_good_row_passes(tmp_path):
    rows, errors = validate.check([row()], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert errors == [] and len(rows) == 1

def test_fabricated_path_rejected(tmp_path):
    _, errors = validate.check([row(rel="文学/ghost.md")], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("path" in e for e in errors)

def test_off_canon_primary_rejected(tmp_path):
    _, errors = validate.check([row(primary="不存在类")], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("primary" in e for e in errors)

def test_unknown_topic_needs_proposal(tmp_path):
    _, errors = validate.check([row(topics="新话题")], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("topic" in e for e in errors)
    rows, errors = validate.check([row(topics="新话题", proposed="新话题")],
                                  ["文学/a.md"], reg(tmp_path), {"文学"})
    assert errors == []

def test_alias_normalized(tmp_path):
    p = tmp_path / "t2.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T0001", "文学评论", "lit-crit", "", "active", "", "", ""]])
    rows, errors = validate.check([row(topics="lit-crit")], ["文学/a.md"],
                                  registry.load(p), {"文学"})
    assert errors == [] and rows[0][4] == "文学评论"

def test_enum_case(tmp_path):
    _, errors = validate.check([row(review="False")], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("needs_review" in e for e in errors)

def test_duplicate_path_rejected(tmp_path):
    _, errors = validate.check([row(), row()], ["文学/a.md", "文学/a.md"],
                               reg(tmp_path), {"文学"})
    assert any("duplicate" in e for e in errors)

def test_row_count_mismatch_flagged(tmp_path):
    _, errors = validate.check([row()], ["文学/a.md", "文学/b.md"], reg(tmp_path), {"文学"})
    assert any("row count" in e for e in errors)

def test_short_row_flagged(tmp_path):
    _, errors = validate.check([["文学/a.md", "t"]], ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("fields" in e for e in errors)

def test_slash_in_topic_rejected(tmp_path):
    _, errors = validate.check([row(topics="C/C++开发", proposed="C/C++开发")],
                               ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("path-unsafe" in e for e in errors)

def test_colon_in_topic_rejected(tmp_path):
    _, errors = validate.check([row(topics="ratio: 比例", proposed="ratio: 比例")],
                               ["文学/a.md"], reg(tmp_path), {"文学"})
    assert any("path-unsafe" in e for e in errors)

def test_clean_topic_still_passes(tmp_path):
    # a normal topic with no path chars must remain valid (regression guard)
    rows, errors = validate.check([row(topics="文学评论", proposed="")],
                                  ["文学/a.md"], reg(tmp_path), {"文学"})
    assert errors == []
