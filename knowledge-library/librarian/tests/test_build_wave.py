from librarian import contract, tsv, registry
from librarian.orchestrate import build_wave

MANIFEST = [[f"zhihu/a{i}.md", f"title{i}", "zhihu", f"{i:016x}"] for i in range(6)]
REG_ROWS = [["T0001", "文学评论", "", "", "active", "", "", ""],
            ["T0002", "思想史", "", "", "proposed", "", "", ""]]


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, REG_ROWS)
    return registry.load(p)


def test_select_skips_labeled_and_caps():
    rows = build_wave.select(MANIFEST, labeled_paths=["zhihu/a0.md"], limit=3)
    assert [r[0] for r in rows] == ["zhihu/a1.md", "zhihu/a2.md", "zhihu/a3.md"]


def test_assignments_split_near_even():
    rows = MANIFEST[:5]
    slices = build_wave.assignments(rows, n_agents=2)
    assert [len(s) for s in slices] == [3, 2]


def test_assignments_drop_empty_slices():
    slices = build_wave.assignments(MANIFEST[:1], n_agents=4)
    assert len(slices) == 1


def test_canon_line_is_active_topics_only(tmp_path):
    assert build_wave.canon_line(_reg(tmp_path)) == "文学评论"


def test_build_writes_one_file_per_agent(cfg, tmp_path):
    cfg.agents_per_wave = 2
    cfg.articles_per_agent = 2
    legacy = {"zhihu/a0.md": ("AI与机器学习", "深度学习")}
    files, canon = build_wave.build(
        MANIFEST, labeled_paths=[], reg=_reg(tmp_path), legacy=legacy,
        out_dir=cfg.wave_assign_dir, vault=cfg.corpus_path, cfg=cfg, wave_no=1)
    assert [f.name for f in files] == ["wave01_agent1.md", "wave01_agent2.md"]
    text = files[0].read_text(encoding="utf-8")
    assert "wave 1, agent 1" in text
    assert "Active topics: 文学评论" in text
    assert "relative_path\tzhihu/a0.md" in text
    assert "original_category\tAI与机器学习" in text
    assert f"source_path\t{cfg.corpus_path}/zhihu/a0.md" in text
    assert "v1_reference\tAI与机器学习 | 深度学习" in text
    # a1 has no legacy row
    assert "v1_reference\tnone" in files[1].read_text(encoding="utf-8")


def test_build_caps_total_at_wave_size(cfg, tmp_path):
    cfg.agents_per_wave = 2
    cfg.articles_per_agent = 2          # wave size 4
    files, _ = build_wave.build(
        MANIFEST, labeled_paths=[], reg=_reg(tmp_path), legacy={},
        out_dir=cfg.wave_assign_dir, vault=cfg.corpus_path, cfg=cfg, wave_no=1)
    total = sum(t.count("## Article ")
                for t in (f.read_text(encoding="utf-8") for f in files))
    assert total == 4
