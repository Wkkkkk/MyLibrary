import dataclasses

from librarian import hubgen, registry, tsv, contract


def reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T0001", "文学评论", "", "文学理论", "active", "细读与评论", "", ""],
                    ["T0002", "文学理论", "", "", "active", "", "", ""],
                    ["T0003", "冷门", "", "", "active", "", "", ""]])
    return registry.load(p)

def lrow(rel, topics, summary="一句话。"):
    return [rel, rel.split("/")[-1][:-3], "", "文学", topics, "", "", summary,
            "high", "false", "", "", "h" * 16, "v1", "d"]

LABELS = [lrow("文学/a.md", "文学评论"), lrow("文学/b.md", "文学评论; 文学理论"),
          lrow("文学/c.md", "文学评论"), lrow("文学/d.md", "冷门")]

def test_generates_only_above_threshold(tmp_path, cfg):
    vault = tmp_path / "vault"; vault.mkdir()
    plans = hubgen.plan(LABELS, reg(tmp_path), vault, dataclasses.replace(cfg, hub_min_articles=3))
    names = {p.name for p, _ in plans}
    assert names == {"文学评论.md"}  # 冷门=1, 文学理论=1 below threshold

def test_hub_content(tmp_path, cfg):
    vault = tmp_path / "vault"; vault.mkdir()
    [(path, text)] = hubgen.plan(LABELS, reg(tmp_path), vault, dataclasses.replace(cfg, hub_min_articles=3))
    assert cfg.generated_marker in text
    assert "[[a]]" in text and "一句话。" in text
    assert "Parent topic: [[文学理论]]" in text
    assert "## Related topics" in text and "[[文学理论]] (1)" in text
    assert "## Reading list" in text

def test_inactive_topic_excluded_despite_count(tmp_path, cfg):
    p = tmp_path / "topics2.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T0001", "活跃话题", "", "", "active", "", "", ""],
                    ["T0002", "停用话题", "", "", "proposed", "", "", ""]])
    r = registry.load(p)
    labels = [lrow("文学/x.md", "活跃话题; 停用话题"),
              lrow("文学/y.md", "活跃话题; 停用话题"),
              lrow("文学/z.md", "活跃话题; 停用话题")]
    plans = hubgen.plan(labels, r, tmp_path / "v", dataclasses.replace(cfg, hub_min_articles=3))
    names = {pp.name for pp, _ in plans}
    assert names == {"活跃话题.md"}  # 停用话题 has 3 articles but is not active

def test_refuses_to_overwrite_unmarked(tmp_path, cfg):
    vault = tmp_path / "vault"; (vault / cfg.hub_dir).mkdir(parents=True)
    (vault / cfg.hub_dir / "文学评论.md").write_text("my own note", encoding="utf-8")
    plans = hubgen.plan(LABELS, reg(tmp_path), vault, dataclasses.replace(cfg, hub_min_articles=3))
    skipped = hubgen.apply(plans, vault, cfg)
    assert skipped == ["文学评论.md"]
    assert (vault / cfg.hub_dir / "文学评论.md").read_text(encoding="utf-8") == "my own note"

def test_lang_zh_localizes_filename_links_and_headers(tmp_path, cfg):
    import dataclasses
    vault = tmp_path / "vault"; vault.mkdir()
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "Lit Theory", "active", "desc", "", "文学评论"],
                    ["T2", "Lit Theory", "", "", "active", "", "", "文学理论"]])
    reg_zh = registry.load(p)
    labels = [lrow("X/a.md", "Lit Crit"), lrow("X/b.md", "Lit Crit; Lit Theory"),
              lrow("X/c.md", "Lit Crit")]
    cfg3 = dataclasses.replace(cfg, hub_min_articles=3, label_language="en")
    plans = hubgen.plan(labels, reg_zh, vault, cfg3, lang="zh")
    by_name = {pp.name: text for pp, text in plans}
    assert "文学评论.md" in by_name            # filename localized via name_zh
    text = by_name["文学评论.md"]
    assert "# 文学评论" in text                 # heading localized
    assert "父话题: [[文学理论]]" in text        # parent header + link localized
    assert "## 阅读清单 (3)" in text            # section header in zh
    assert "## 相关话题" in text                # related header in zh
    assert "[[文学理论]] (1)" in text           # related link localized
    assert "[[a]]" in text                      # article basenames NOT localized
