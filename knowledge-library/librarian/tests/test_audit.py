from librarian import audit, registry

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


def test_report_excludes_already_active_topics_from_proposals(cfg):
    # After GATE 2 accept, a proposed topic that is now active in the registry
    # must drop out of the pending-proposals count (finding #5).
    reg = registry.Registry([["T0001", "新话题", "", "", "active", "", "2026-06-15", ""]])
    rep = audit.report(LABELS, cfg, reg=reg)
    assert "新话题" not in rep["proposals"]


def test_report_without_registry_counts_all_proposals(cfg):
    # Backward compatible: no registry -> raw proposed_topics count.
    rep = audit.report(LABELS, cfg, reg=None)
    assert rep["proposals"]["新话题"] == 1


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


def test_cmd_audit_excludes_accepted_proposal(tmp_path, monkeypatch, capsys):
    from librarian import update, config, contract, store, tsv

    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"文学"},
                      topic_split_threshold=2, hub_min_articles=2)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(update, "cfg", c)
    # 新话题 has already been promoted to active in the canon.
    tsv.write_rows(c.topics_path, contract.TOPIC_COLUMNS,
                   [["T0001", "新话题", "", "", "active", "", "2026-06-15", ""]])

    def lr(rel, topics, proposed=""):
        r = [""] * len(contract.LABEL_COLUMNS)
        r[0], r[3], r[4], r[11] = rel, "文学", topics, proposed
        return r

    store.merge(c.labels_path, [lr("文学/p.md", "新话题", "新话题")])
    update.cmd_audit()
    out = capsys.readouterr().out
    assert "proposals: {}" in out   # nothing pending once accepted
