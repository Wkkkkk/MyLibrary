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


def test_cmd_audit_prints_report(tmp_path, monkeypatch, capsys):
    from librarian import update, config, contract, store

    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"文学"},
                      topic_split_threshold=2, hub_min_articles=2)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update, "cfg", c)

    def lr(rel, topics, proposed=""):
        r = [""] * len(contract.LABEL_COLUMNS)
        r[0], r[3], r[4], r[11] = rel, "文学", topics, proposed
        return r

    store.merge(c.labels_path, [lr("文学/a.md", "大话题"), lr("文学/b.md", "大话题"),
                                lr("文学/c.md", "大话题"),
                                lr("文学/p.md", "新话题", "新话题")])
    update.cmd_audit()
    out = capsys.readouterr().out
    assert "split candidates" in out
    assert "大话题" in out          # 3 articles > threshold 2 -> split candidate
    assert "新话题" in out          # a pending proposal
