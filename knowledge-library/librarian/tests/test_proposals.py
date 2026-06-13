"""Tests for proposal triage (Bug 2).

`ingest` accepts a topic declared in a row's proposed_topics, but `verify`
requires every topic to be an ACTIVE registry entry. Proposal triage promotes
accepted proposals into topics.tsv so the steady-state flow can close green.
"""
from librarian import proposals, registry, config, contract, tsv, update


def _reg(rows):
    return registry.Registry(rows)


def _treg(name, status="active", tid="T0001"):
    r = [""] * len(contract.TOPIC_COLUMNS)
    r[0], r[1], r[4], r[6] = tid, name, status, "2026-06-11"
    return r


def _lrow(title, topics, proposed):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[1], r[3] = title, "AI与机器学习"  # title, primary_category
    r[4], r[11] = topics, proposed       # topics, proposed_topics
    return r


def test_pending_aggregates_proposals_not_yet_active():
    reg = _reg([_treg("大模型与智能体")])
    rows = [
        _lrow("art1", "大模型与智能体; AI辅助开发", "AI辅助开发"),
        _lrow("art2", "AI辅助开发", "AI辅助开发"),
        _lrow("art3", "大模型与智能体", ""),
    ]
    pend = proposals.pending(rows, reg)
    # AI辅助开发 proposed by 2 articles; 大模型与智能体 already active -> excluded
    assert pend == [("AI辅助开发", 2, ["art1", "art2"])]


def test_pending_excludes_already_active_proposals():
    reg = _reg([_treg("AI辅助开发")])
    rows = [_lrow("art1", "AI辅助开发", "AI辅助开发")]
    assert proposals.pending(rows, reg) == []


def test_accept_appends_active_rows_with_sequential_ids():
    reg_rows = [_treg("大模型与智能体", tid="T0007")]
    out = proposals.accept(reg_rows, ["AI辅助开发"], "2026-06-12")
    assert len(out) == 2
    new = out[-1]
    assert new[1] == "AI辅助开发"           # name
    assert new[4] == "active"               # status
    assert new[0] == "T0008"                # next sequential id
    assert new[6] == "2026-06-12"           # created_at


def test_accept_is_idempotent_for_existing_names():
    reg_rows = [_treg("AI辅助开发", tid="T0007")]
    out = proposals.accept(reg_rows, ["AI辅助开发"], "2026-06-12")
    assert len(out) == 1  # already present, not duplicated


def test_cmd_proposals_accept_promotes_into_registry(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    c = config.Config(corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
                      data_dir=data, categories={"AI与机器学习"})
    labels = c.labels_path
    topics = c.topics_path
    tsv.write_rows(topics, contract.TOPIC_COLUMNS, [_treg("大模型与智能体")])
    tsv.write_rows(labels, contract.LABEL_COLUMNS,
                   [_lrow("art1", "大模型与智能体; AI辅助开发", "AI辅助开发")])
    monkeypatch.setattr(update, "cfg", c)

    update.cmd_proposals(accept=True)

    assert "AI辅助开发" in registry.load(topics).active_names()
