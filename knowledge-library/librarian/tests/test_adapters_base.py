import unicodedata

from librarian.adapters import base

VALID = ('---\ntitle: "T"\nsource: zhihu\nurl: "https://z/p/1"\n---\n\nBody text.\n')


class ListAdapter(base.Adapter):
    """Test adapter that yields a fixed list of (filename, text) pairs."""
    name = "test"

    def __init__(self, items):
        self.items = items

    def nodes(self, src_dir):
        yield from self.items


def test_parse_splits_frontmatter_and_body():
    fm, body = base.parse(VALID)
    assert fm["title"] == "T"
    assert fm["source"] == "zhihu"
    assert fm["url"] == "https://z/p/1"
    assert body.strip() == "Body text."


def test_parse_fence_safe_with_dashes_in_title():
    text = '---\ntitle: "a\n------ b"\nsource: x\nurl: "u"\n---\nBody\n'
    fm, body = base.parse(text)
    # The bare closing fence is the real `---` line, not the `------` in the title.
    assert fm["source"] == "x"
    assert body.strip() == "Body"


def test_parse_no_frontmatter_returns_empty():
    fm, body = base.parse("no frontmatter here")
    assert fm == {} and body == "no frontmatter here"


def test_validate_accepts_complete_node():
    fm, body = base.parse(VALID)
    assert base.validate(fm, body) == []


def test_validate_rejects_missing_url():
    fm, body = base.parse('---\ntitle: "T"\nsource: zhihu\n---\nBody\n')
    errs = base.validate(fm, body)
    assert any("url" in e for e in errs)


def test_validate_rejects_empty_body():
    fm, body = base.parse('---\ntitle: "T"\nsource: zhihu\nurl: "u"\n---\n\n')
    assert base.validate(fm, body) != []


def test_set_field_injects_missing_key():
    text = '---\ntitle: "T"\nurl: "u"\n---\nBody\n'
    out = base.set_field(text, "source", "blog")
    fm, _ = base.parse(out)
    assert fm["source"] == "blog"


def test_set_field_replaces_existing_key():
    out = base.set_field(VALID, "source", "blog")
    fm, _ = base.parse(out)
    assert fm["source"] == "blog"


def test_ingest_writes_valid_node_under_source_subfolder(cfg):
    adapter = ListAdapter([("a.md", VALID)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md"]
    assert rejected == [] and skipped == []
    assert (cfg.corpus_path / "test" / "a.md").read_text(encoding="utf-8") == VALID


def test_ingest_rejects_contract_violation(cfg):
    bad = '---\ntitle: "T"\nsource: zhihu\n---\nBody\n'  # no url
    adapter = ListAdapter([("bad.md", bad)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == []
    assert rejected and rejected[0][0] == "bad.md"
    assert any("url" in e for e in rejected[0][1])
    assert not (cfg.corpus_path / "test" / "bad.md").exists()


def test_ingest_skips_duplicate_url(cfg):
    adapter = ListAdapter([("a.md", VALID), ("b.md", VALID)])  # same url
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md"]
    assert skipped == ["b.md"]


def test_ingest_collision_keeps_both_when_url_differs(cfg):
    other = VALID.replace("https://z/p/1", "https://z/p/2")
    adapter = ListAdapter([("a.md", VALID), ("a.md", other)])
    written, rejected, skipped = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/a.md", "test/a_2.md"]


def test_ingest_nfc_normalizes_filename(cfg):
    nfd_name = unicodedata.normalize("NFD", "ポップ.md")
    assert nfd_name != "ポップ.md"
    adapter = ListAdapter([(nfd_name, VALID)])
    written, _, _ = base.ingest_to_inbox(adapter, "ignored", cfg)
    assert written == ["test/" + unicodedata.normalize("NFC", "ポップ.md")]
