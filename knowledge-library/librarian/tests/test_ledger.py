from librarian import ledger, contract, config


def _cfg(tmp_path):
    # create data_dir so the ledger tests pass independently of Task 6's
    # tsv.write_rows parent-dir guard.
    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"Literature"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _run(run_id, new="3", flagged="0", proposed="1", status="ok", lang="en"):
    # RUN_COLUMNS order: run_id, started_at, finished_at, source, fetched, new,
    # labeled, proposed_topics, flagged, status, lang
    return [run_id, "2026-06-13T10:00", "2026-06-13T10:05", "zhihu", "10",
            new, new, proposed, flagged, status, lang]


def test_run_columns_and_status_enum():
    assert contract.RUN_COLUMNS == [
        "run_id", "started_at", "finished_at", "source", "fetched", "new",
        "labeled", "proposed_topics", "flagged", "status", "lang"]
    assert contract.RUN_STATUS == {"ok", "nothing_new", "auth_failed", "error"}


def test_runs_path_property(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.runs_path == cfg.data_dir / "runs.tsv"


def test_load_missing_ledger_is_empty(tmp_path):
    cfg = _cfg(tmp_path)
    assert ledger.load(cfg.runs_path) == []
    assert ledger.latest(cfg.runs_path) is None


def test_append_creates_and_accumulates(tmp_path):
    cfg = _cfg(tmp_path)
    ledger.append(cfg.runs_path, _run("r1"))
    ledger.append(cfg.runs_path, _run("r2", new="0", status="nothing_new"))
    rows = ledger.load(cfg.runs_path)
    assert [r[0] for r in rows] == ["r1", "r2"]
    assert ledger.latest(cfg.runs_path)[0] == "r2"


def test_append_rejects_wrong_width(tmp_path):
    cfg = _cfg(tmp_path)
    try:
        ledger.append(cfg.runs_path, ["r1", "only", "three"])
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_digest_renders_new_proposed_flagged():
    assert ledger.digest(_run("r1", new="3", proposed="1", flagged="2")) == \
        "3 new · 1 proposed · 2 flagged"
