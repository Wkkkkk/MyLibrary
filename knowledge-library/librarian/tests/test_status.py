from librarian import status, config, contract, tsv, store, ledger


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "v", library_path=tmp_path / "v",
                      data_dir=tmp_path / "d", categories={"Literature"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _lrow(rel, topics="Lit Crit", review="false", proposed=""):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[3], r[4] = rel, "Literature", topics
    r[9], r[11] = review, proposed
    return r


def _seed_topics(cfg):
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])


def _run(run_id, new="3", flagged="0", status="ok"):
    return [run_id, "2026-05-01T09:00", "2026-06-13T10:05", "zhihu", "10",
            new, new, "0", flagged, status, "en"]


def test_status_empty_ledger(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_topics(cfg)
    store.merge(cfg.labels_path, [_lrow("Literature/a.md")])
    out = status.render(cfg)
    assert "Library: 1 articles · canon 1 topics" in out
    assert "Last run: never" in out
    assert "History: 0 runs" in out


def test_status_with_runs_and_queues(tmp_path):
    cfg = _cfg(tmp_path)
    _seed_topics(cfg)
    store.merge(cfg.labels_path, [
        _lrow("Literature/a.md", review="true"),
        _lrow("Literature/b.md", topics="新话题", proposed="新话题")])
    ledger.append(cfg.runs_path, _run("r1", status="auth_failed"))
    ledger.append(cfg.runs_path, _run("r2", new="3", flagged="1", status="ok"))
    out = status.render(cfg)
    assert "Last run: 2026-06-13T10:05  +3 new, 1 flagged   [ok]" in out
    assert "Pending: 1 proposed topics · 1 needs-review" in out
    assert "History: 2 runs since 2026-05-01T09:00" in out
    assert "last auth_failed: 2026-06-13T10:05" in out


def test_status_no_topics_file(tmp_path):
    cfg = _cfg(tmp_path)  # no topics.tsv written
    out = status.render(cfg)
    assert "Library: 0 articles · canon 0 topics" in out
