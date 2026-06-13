import unicodedata

from librarian import verify, registry, tsv, contract


def reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T0001", "文学评论", "", "", "active", "", "", ""]])
    return registry.load(p)

def lrow(rel, primary="文学", topics="文学评论"):
    return [rel, "", "", primary, topics, "", "", "s", "high", "false", "",
            "", "h" * 16, "v1", "d"]

def make_vault(tmp_path, rels):
    v = tmp_path / "vault"
    for rel in rels:
        p = v / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return v

def test_green(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md"])
    assert verify.run([lrow("文学/a.md")], reg(tmp_path), v, {"文学"}, cfg) == []

def test_violations(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md", "文学/ghost.md"])
    problems = verify.run(
        [lrow("文学/a.md", topics="未注册话题"), lrow("文学/missing.md")],
        reg(tmp_path), v, {"文学"}, cfg)
    text = "\n".join(problems)
    assert "ghost" in text          # on disk, not in labels
    assert "missing" in text        # in labels, not on disk
    assert "未注册话题" in text      # unresolvable topic


def test_nfc_closure_no_false_ghost(tmp_path, cfg):
    # disk filename composed NFD, label path NFC — must NOT produce ghost/missing
    nfc_name = "文学/café.md"            # café with composed é (NFC)
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    v = make_vault(tmp_path, [nfd_name])   # write the NFD form to disk
    problems = verify.run([lrow(nfc_name)], reg(tmp_path), v, {"文学"}, cfg)
    assert problems == [], problems


def test_manifest_leg_closure(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md"])
    manifest = [["文学/a.md", "", "文学", "h"],
                ["文学/ghost.md", "", "文学", "h"]]
    problems = verify.run([lrow("文学/a.md")], reg(tmp_path), v, {"文学"}, cfg,
                          manifest_rows=manifest)
    text = "\n".join(problems)
    assert "in manifest but unlabeled" in text
    assert "ghost" in text
    # backward-compat: call without manifest_rows still green for match
    assert verify.run([lrow("文学/a.md")], reg(tmp_path), v, {"文学"}, cfg) == []


def hub_reg(tmp_path):
    p = tmp_path / "topics.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T0001", "文学评论", "", "", "active", "", "", ""]])
    return registry.load(p)


def write_hub(vault, stem, body, cfg):
    d = vault / cfg.hub_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text(body, encoding="utf-8")


def test_orphaned_hub_note(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md", "文学/b.md", "文学/c.md"])
    rows = [lrow("文学/a.md"), lrow("文学/b.md"), lrow("文学/c.md")]
    # generated hub for a topic with 0 articles -> orphan
    write_hub(v, "废弃话题",
              f"---\n{cfg.generated_marker}\narticles: 0\n---\n\n"
              f"# 废弃话题\n\n## 阅读清单 (0)\n", cfg)
    # hand-edited note, no marker -> must NOT be flagged
    write_hub(v, "手写", "# 手写\n\nhand written\n", cfg)
    problems = verify.run(rows, hub_reg(tmp_path), v, {"文学"}, cfg)
    text = "\n".join(problems)
    assert "orphaned hub note" in text
    assert "废弃话题" in text
    assert "手写" not in text


def test_hub_list_matches(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md", "文学/b.md", "文学/c.md"])
    rows = [lrow("文学/a.md"), lrow("文学/b.md"), lrow("文学/c.md")]
    # hub missing c
    write_hub(v, "文学评论",
              f"---\n{cfg.generated_marker}\narticles: 2\n---\n\n"
              f"# 文学评论\n\n## 阅读清单 (2)\n\n"
              f"- [[a]] — s\n- [[b]] — s\n", cfg)
    problems = verify.run(rows, hub_reg(tmp_path), v, {"文学"}, cfg)
    text = "\n".join(problems)
    assert "hub list mismatch for 文学评论" in text
    assert "c" in text
    # positive case: hub lists exactly a, b, c -> no mismatch
    write_hub(v, "文学评论",
              f"---\n{cfg.generated_marker}\narticles: 3\n---\n\n"
              f"# 文学评论\n\n## 阅读清单 (3)\n\n"
              f"- [[a]] — s\n- [[b]] — s\n- [[c]] — s\n", cfg)
    problems = verify.run(rows, hub_reg(tmp_path), v, {"文学"}, cfg)
    assert not any("hub list mismatch" in p for p in problems), problems


def test_hub_list_matches_bracket_terminated_basename(tmp_path, cfg):
    # basename ends in ']' — the regex must capture the full name including ']'
    v = make_vault(tmp_path, ["文学/CP或AP [译文].md", "文学/b.md", "文学/c.md"])
    rows = [lrow("文学/CP或AP [译文].md"), lrow("文学/b.md"), lrow("文学/c.md")]
    write_hub(v, "文学评论",
              f"---\n{cfg.generated_marker}\narticles: 3\n---\n\n"
              f"# 文学评论\n\n## 阅读清单 (3)\n\n"
              f"- [[CP或AP [译文]]] — s\n- [[b]] — s\n- [[c]] — s\n", cfg)
    problems = verify.run(rows, hub_reg(tmp_path), v, {"文学"}, cfg)
    assert not any("hub list mismatch" in p for p in problems), problems


def test_per_row_violations(tmp_path, cfg):
    v = make_vault(tmp_path, ["文学/a.md"])
    rows = [lrow("文学/a.md", primary="历史人文"),   # folder != primary
            lrow("文学/a.md"),                        # duplicate path
            lrow("文学/a.md")]
    # give the third row a bad confidence
    rows[2][8] = "HIGH"
    text = "\n".join(verify.run(rows, reg(tmp_path), v, {"文学", "历史人文"}, cfg))
    assert "folder" in text
    assert "duplicate" in text
    assert "confidence" in text


def test_lang_zh_localized_vault_verifies_clean(tmp_path):
    from librarian import config
    cfg = config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "d", categories={"Literature"},
        label_language="en", category_localization={"Literature": {"zh": "文学"}},
        hub_min_articles=1)
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    reg_zh = registry.load(p)
    # on disk: localized folder 文学/, localized hub 文学评论.md
    v = make_vault(tmp_path, ["文学/a.md"])
    write_hub(v, "文学评论",
              f"---\n{cfg.generated_marker}\narticles: 1\n---\n\n"
              f"# 文学评论\n\n## 阅读清单 (1)\n\n- [[a]] — s\n", cfg)
    # label row: canonical primary Literature + canonical topic Lit Crit
    lr = ["文学/a.md", "", "", "Literature", "Lit Crit", "", "", "s",
          "high", "false", "", "", "h" * 16, "v1", "d"]
    problems = verify.run([lr], reg_zh, v, {"Literature"}, cfg, lang="zh")
    assert problems == [], problems


def test_lang_zh_wrong_localized_folder_flagged(tmp_path):
    from librarian import config
    cfg = config.Config(
        corpus_path=tmp_path / "vault", library_path=tmp_path / "vault",
        data_dir=tmp_path / "d", categories={"Literature", "History"},
        label_language="en",
        category_localization={"Literature": {"zh": "文学"}, "History": {"zh": "历史"}},
        hub_min_articles=1)
    p = tmp_path / "topics_zh.tsv"
    tsv.write_rows(p, contract.TOPIC_COLUMNS,
                   [["T1", "Lit Crit", "", "", "active", "", "", "文学评论"]])
    reg_zh = registry.load(p)
    v = make_vault(tmp_path, ["历史/a.md"])   # filed under 历史 ...
    lr = ["历史/a.md", "", "", "Literature", "Lit Crit", "", "", "s",   # ... but primary is Literature->文学
          "high", "false", "", "", "h" * 16, "v1", "d"]
    problems = verify.run([lr], reg_zh, v, {"Literature", "History"}, cfg, lang="zh")
    assert any("folder" in p for p in problems)
