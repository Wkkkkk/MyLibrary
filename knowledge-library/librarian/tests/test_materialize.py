"""Direct test of the extracted orchestrate.materialize (cfg passed explicitly,
not via update.py's module global)."""
from librarian import config, contract, tsv, manifest, store
from librarian.orchestrate import materialize


def _cfg(tmp_path):
    c = config.Config(corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
                      data_dir=tmp_path / "data", categories={"文学", "历史人文"})
    c.data_dir.mkdir(parents=True, exist_ok=True)
    return c


def _lrow(rel, primary):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0], r[1], r[3], r[12] = rel, "t", primary, "h0"
    return r


def _article(vault, rel, primary):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f'---\ntitle: "t"\nprimary_category: "{primary}"\n---\n\n# t\n',
                 encoding="utf-8")


def test_materialize_refiles_in_place(tmp_path):
    cfg = _cfg(tmp_path)
    _article(cfg.corpus_path, "文学/a.md", "历史人文")
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS, [])
    tsv.write_rows(cfg.labels_path, contract.LABEL_COLUMNS, [_lrow("文学/a.md", "历史人文")])
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))

    materialize.materialize(cfg, write=True)

    assert [r[0] for r in store.load(cfg.labels_path)] == ["历史人文/a.md"]
    assert (cfg.corpus_path / "历史人文" / "a.md").exists()


def test_materialize_tolerates_missing_topics_tsv(tmp_path):
    # Bootstrap: a fresh library has no topics.tsv until proposals are accepted
    # (GATE 2). materialize must treat the absent canon as empty and still
    # refile by primary_category (writing no hubs) — not crash on registry.load.
    cfg = _cfg(tmp_path)
    _article(cfg.corpus_path, "文学/a.md", "历史人文")
    assert not cfg.topics_path.exists()
    tsv.write_rows(cfg.labels_path, contract.LABEL_COLUMNS, [_lrow("文学/a.md", "历史人文")])
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, manifest.build(cfg.corpus_path, cfg))

    materialize.materialize(cfg, write=True)

    assert (cfg.corpus_path / "历史人文" / "a.md").exists()
