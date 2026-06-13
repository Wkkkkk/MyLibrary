"""Synthetic end-to-end pipeline (spec §11): a handful of plain-markdown nodes
flow adapter -> inbox -> manifest -> build_wave -> ingest_wave -> materialize ->
verify, exercising every seam against real manifest.build output."""
import json

from librarian import config, contract, tsv, manifest, registry, store, update
from librarian.adapters import base, markdown_passthrough as mp
from librarian.orchestrate import build_wave, ingest_wave


def test_end_to_end_adapter_to_verify(tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    data = tmp_path / "data"
    data.mkdir()
    cfg = config.Config(
        corpus_path=inbox, library_path=inbox, data_dir=data,
        categories={"Literature"}, label_language="en", hub_min_articles=1)
    monkeypatch.setattr(update, "cfg", cfg)

    # 1. a source directory of plain-markdown nodes (title/source/url + body)
    src = tmp_path / "src"
    src.mkdir()
    for i in range(3):
        (src / f"a{i}.md").write_text(
            f'---\ntitle: "T{i}"\nsource: blog\nurl: "https://x/{i}"\n---\n\nBody {i}.\n',
            encoding="utf-8")

    # 2. adapter normalizes them into the inbox under blog/
    written, rejected, skipped = base.ingest_to_inbox(
        mp.MarkdownPassthroughAdapter("blog"), src, cfg)
    assert len(written) == 3 and not rejected and not skipped

    # 3. manifest from the real inbox
    man = manifest.build(inbox, cfg)
    tsv.write_rows(cfg.manifest_path, contract.MANIFEST_COLUMNS, man)
    assert {r[0] for r in man} == {"blog/a0.md", "blog/a1.md", "blog/a2.md"}

    # 4. a registry with one active topic
    tsv.write_rows(cfg.topics_path, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "2026-06-13", ""]])
    reg = registry.load(cfg.topics_path)

    # 5. build a wave — selection + per-agent assignment files
    files, canon = build_wave.build(man, [], reg, {}, cfg.wave_assign_dir,
                                    inbox, cfg, wave_no=1)
    assert files and canon == "Lit Crit"

    # 6. simulate the agents' JSON output, keyed by the manifest's real paths
    # each agent object carries a WRONG title; ingest_wave must discard it and
    # use the FROZEN manifest title instead (anti-fabrication property)
    objs = [{"relative_path": r[0], "title": "WRONG_AGENT_TITLE",
             "primary_category": "Literature",
             "topics": ["Lit Crit"], "tags": [], "article_type": "essay",
             "summary": "s", "confidence": "high", "needs_review": False,
             "review_reason": "", "proposed_topics": []} for r in man]
    jp = data / "wave01.json"
    jp.write_text(json.dumps(objs), encoding="utf-8")

    # 7. ingest the wave — reconstructs rows from FROZEN manifest fields
    summary = ingest_wave.ingest([str(jp)], man, {}, reg, cfg, "2026-06-13",
                                 run_id="r1")
    assert summary["errors"] == [] and summary["merged"] == 3
    fsr = contract.LABEL_COLUMNS.index("first_seen_run")
    assert all(row[fsr] == "r1" for row in store.load(cfg.labels_path))
    # frozen title came from the manifest, NOT the agent JSON (which supplied
    # "WRONG_AGENT_TITLE" — proving agent-supplied provenance is discarded)
    title_i = contract.LABEL_COLUMNS.index("title")
    assert {row[title_i] for row in store.load(cfg.labels_path)} == {"T0", "T1", "T2"}

    # 8. materialize — files into Literature/, writes topic hubs
    update.cmd_materialize(write=True)
    assert (inbox / "Literature").is_dir()
    assert (inbox / cfg.hub_dir / "Lit Crit.md").exists()

    # 9. verify — closure holds end-to-end
    assert update.verify_problems() == []
