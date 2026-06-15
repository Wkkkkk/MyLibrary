import json

from librarian import contract, tsv, registry, store
from librarian.orchestrate import ingest_wave

MANIFEST = [["zhihu/a0.md", "Title Zero", "zhihu", "0" * 16, "源类零"],
            ["zhihu/a1.md", "Title One", "zhihu", "1" * 16, "源类一"]]
REG_ROWS = [["T0001", "深度学习", "", "", "active", "", "", ""]]


def _reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS, REG_ROWS)
    return registry.load(p)


def _judgment(rel="zhihu/a0.md", primary="AI与机器学习", topics=None,
              proposed=None, review=False):
    return {"relative_path": rel, "primary_category": primary,
            "topics": topics or ["深度学习"], "tags": ["YOLO"],
            "article_type": "学术解读", "summary": "摘要。",
            "confidence": "high", "needs_review": review,
            "review_reason": "", "proposed_topics": proposed or []}


def _write_json(tmp_path, objs, name="wave01_agent1.json"):
    p = tmp_path / name
    p.write_text(json.dumps(objs, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _cfg(cfg):
    cfg.categories = {"AI与机器学习"}
    return cfg


def test_run_bootstraps_without_topics_file(cfg):
    # finding #2: a wave must ingest before any topics.tsv exists — proposed
    # topics are accepted via that row's proposed_topics, no canon needed yet.
    inbox = cfg.corpus_path / "zhihu"
    inbox.mkdir(parents=True)
    (inbox / "a.md").write_text(
        '---\ntitle: "A"\nsource: zhihu\nurl: "u1"\n---\nbody\n', encoding="utf-8")
    cfg.wave_out_dir.mkdir(parents=True, exist_ok=True)
    (cfg.wave_out_dir / "w.json").write_text(json.dumps([{
        "relative_path": "zhihu/a.md", "primary_category": "文学",
        "topics": ["新话题"], "proposed_topics": ["新话题"], "tags": [],
        "article_type": "x", "summary": "s", "confidence": "high",
        "needs_review": False, "review_reason": ""}], ensure_ascii=False),
        encoding="utf-8")
    assert not cfg.topics_path.exists()
    summary = ingest_wave.run(cfg, today="2026-06-15")   # must not raise
    assert summary["errors"] == []
    assert summary["merged"] == 1


def test_ingest_merges_rows_with_frozen_fields(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    summary = ingest_wave.ingest([jp], MANIFEST, legacy={}, reg=_reg(tmp_path),
                                 cfg=cfg, today="2026-06-13")
    assert summary["errors"] == []
    assert summary["merged"] == 1
    rows = store.load(cfg.labels_path)
    r = rows[0]
    assert r[0] == "zhihu/a0.md"
    assert r[1] == "Title Zero"          # frozen title from manifest
    assert r[3] == "AI与机器学习"          # primary from agent
    assert r[4] == "深度学习"             # topics joined
    assert r[12] == "0" * 16             # frozen content_hash from manifest
    assert r[13] == cfg.extractor_version
    assert r[14] == "2026-06-13"


def test_original_category_comes_from_legacy(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    legacy = {"zhihu/a0.md": ("旧类", "旧子类")}
    ingest_wave.ingest([jp], MANIFEST, legacy, _reg(tmp_path), cfg, "2026-06-13")
    assert store.load(cfg.labels_path)[0][2] == "旧类"   # legacy v1 wins


def test_original_category_falls_back_to_manifest_when_no_legacy(cfg, tmp_path):
    # finding #3: with no legacy v1 mapping, original_category is seeded from the
    # manifest's source `category:` column instead of being left blank.
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    ingest_wave.ingest([jp], MANIFEST, legacy={}, reg=_reg(tmp_path),
                       cfg=cfg, today="2026-06-13")
    assert store.load(cfg.labels_path)[0][2] == "源类零"


def test_needs_review_bool_becomes_lowercase_string(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(review=True)])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["review"] == 1
    assert store.load(cfg.labels_path)[0][9] == "true"


def test_off_canon_primary_blocks_the_whole_wave(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(primary="不存在类")])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("primary" in e for e in summary["errors"])
    assert store.load(cfg.labels_path) == []


def test_fabricated_path_is_skipped_not_merged(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment(rel="zhihu/ghost.md")])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["skipped"] == ["zhihu/ghost.md"]
    assert summary["merged"] == 0


def test_proposed_topic_is_recorded_and_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    reg = _reg(tmp_path)
    jp = _write_json(tmp_path, [_judgment(topics=["新话题"], proposed=["新话题"])])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, reg, cfg, "2026-06-13")
    assert summary["merged"] == 1
    assert "新话题" in summary["proposals"]
    # canon untouched — proposal recorded, not promoted (in-memory reg unchanged)
    assert "新话题" not in reg.active_names()
    # ingest must not persist the registry — that is a gate action, not ingest's job
    assert not cfg.topics_path.exists()


def test_first_seen_run_is_stamped(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13",
                       run_id="run-7")
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert store.load(cfg.labels_path)[0][fsr] == "run-7"


def test_first_seen_run_defaults_to_empty(cfg, tmp_path):
    cfg = _cfg(cfg)
    jp = _write_json(tmp_path, [_judgment()])
    ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert store.load(cfg.labels_path)[0][fsr] == ""


def test_invalid_json_is_reported_not_raised(cfg, tmp_path):
    cfg = _cfg(cfg)
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    summary = ingest_wave.ingest([str(bad)], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("invalid JSON" in e for e in summary["errors"])
    assert store.load(cfg.labels_path) == []


def test_non_list_payload_is_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    obj = _write_json(tmp_path, _judgment(), name="obj.json")  # a dict, not a list
    summary = ingest_wave.ingest([obj], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("expected a JSON array" in e for e in summary["errors"])


def test_item_missing_relative_path_is_reported(cfg, tmp_path):
    cfg = _cfg(cfg)
    j = _judgment()
    del j["relative_path"]
    jp = _write_json(tmp_path, [j])
    summary = ingest_wave.ingest([jp], MANIFEST, {}, _reg(tmp_path), cfg, "2026-06-13")
    assert summary["merged"] == 0
    assert any("relative_path" in e for e in summary["errors"])
