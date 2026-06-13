from librarian import audit

def lrow(rel, primary, topics, proposed=""):
    return [rel, "", "", primary, topics, "", "", "s", "high", "false", "",
            proposed, "h" * 16, "v1", "d"]

LABELS = ([lrow(f"文学/a{i}.md", "文学", "文学评论") for i in range(45)]
          + [lrow("文学/p.md", "文学", "新话题", proposed="新话题")])

def test_report_flags_oversized_and_proposals(cfg):
    rep = audit.report(LABELS, cfg)
    assert "文学评论" in rep["split_candidates"]
    assert rep["proposals"]["新话题"] == 1
    assert rep["category_sizes"]["文学"] == 46
