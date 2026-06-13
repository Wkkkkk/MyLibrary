"""Steady-state deterministic glue (spec §7): diff_new / finish / record_nothing_new."""
import json

from librarian import config, contract, tsv, manifest, registry, store, ledger
from librarian.orchestrate import steady_state


def _cfg(tmp_path, inbox_name="inbox"):
    inbox = tmp_path / inbox_name
    c = config.Config(corpus_path=inbox, library_path=tmp_path / "lib",
                      data_dir=tmp_path / "data", categories={"Literature"},
                      label_language="en", hub_min_articles=1)
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _node(vault, rel, url):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "{rel}"\nsource: blog\nurl: "{url}"\n---\n\nBody.\n',
                 encoding="utf-8")


def _lrow(rel, url=None):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[3], r[4] = rel, "Literature", "Lit Crit"
    return r


def _reg(cfg):
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])


def test_diff_new_is_net_new_by_url(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    # library already has article with url U1 (filed under Literature/)
    _node(lib, "Literature/a.md", "https://x/1")
    store.merge(cfg.labels_path, [_lrow("Literature/a.md")])
    # inbox has a re-fetch of U1 (known) + a brand-new U2
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    _node(cfg.corpus_path, "blog/b.md", "https://x/2")
    new = steady_state.diff_new(cfg, lib)
    assert [r[0] for r in new] == ["blog/b.md"]


def test_record_nothing_new_logs_zero_cost_run(tmp_path):
    cfg = _cfg(tmp_path)
    row, digest = steady_state.record_nothing_new(
        cfg, run_id="r1", started_at="2026-06-13T10:00", finished_at="2026-06-13T10:00")
    assert digest == "0 new · 0 proposed · 0 flagged"
    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "nothing_new"
    assert ledger.latest(cfg.runs_path)[i("run_id")] == "r1"


def test_finish_ingests_materializes_verifies_and_logs_ok(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    lib.mkdir(parents=True, exist_ok=True)
    _reg(cfg)
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    objs = [{"relative_path": "blog/a.md", "primary_category": "Literature",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []}]
    jp = cfg.data_dir / "wave.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    row, digest = steady_state.finish(
        cfg, lib, [str(jp)], run_id="r1", started_at="2026-06-13T10:00",
        finished_at="2026-06-13T10:05", today="2026-06-13", fetched=1, new=1)

    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "ok"
    assert row[i("labeled")] == "1"
    assert digest == "1 new · 0 proposed · 0 flagged"
    assert (lib / "Literature" / "a.md").exists()      # materialized into the library
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert all(r[fsr] == "r1" for r in store.load(cfg.labels_path))
    assert ledger.latest(cfg.runs_path)[i("status")] == "ok"


def test_finish_off_canon_logs_error_and_materializes_nothing(tmp_path):
    cfg = _cfg(tmp_path)
    lib = cfg.library_path
    lib.mkdir(parents=True, exist_ok=True)
    _reg(cfg)
    _node(cfg.corpus_path, "blog/a.md", "https://x/1")
    objs = [{"relative_path": "blog/a.md", "primary_category": "NotACategory",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []}]
    jp = cfg.data_dir / "wave.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    row, _ = steady_state.finish(
        cfg, lib, [str(jp)], run_id="r1", started_at="2026-06-13T10:00",
        finished_at="2026-06-13T10:05", today="2026-06-13", fetched=1, new=1)

    i = contract.RUN_COLUMNS.index
    assert row[i("status")] == "error"
    assert store.load(cfg.labels_path) == []           # nothing ingested
    assert not (lib / "Literature").exists()           # nothing materialized
    assert ledger.latest(cfg.runs_path)[i("status")] == "error"
