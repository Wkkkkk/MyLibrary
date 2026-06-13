from pathlib import Path

from librarian import config


def test_defaults_match_legacy_schema():
    c = config.Config(corpus_path=Path("/v"), library_path=Path("/v"),
                       data_dir=Path("/d"), categories={"文学"})
    assert c.hub_dir == "_topics"
    assert c.skip_dirs == {"_images", "分类视图", "话题", "_topics"}
    assert c.hub_min_articles == 3
    assert c.topic_split_threshold == 40
    assert c.batch_size == 30
    assert c.generated_marker == "generated: knowledge-library"
    assert c.label_language == "en"          # English-canonical vocab (spec §4b)
    assert c.category_localization == {}      # no display map by default


def test_derived_paths():
    c = config.Config(corpus_path=Path("/v"), library_path=Path("/v"),
                      data_dir=Path("/d"), categories={"文学"})
    assert c.labels_path == Path("/d/article_labels.tsv")
    assert c.topics_path == Path("/d/topics.tsv")
    assert c.manifest_path == Path("/d/manifest.tsv")
    assert c.batches_dir == Path("/d/batches")
    assert c.progress_path == Path("/d/progress.tsv")
    assert c.migration_log_path == Path("/d/migration_log.tsv")
    assert c.legacy_labels == Path("/d/legacy_category_labels.tsv")


def test_load_from_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "corpus_path: /inbox\n"
        "library_path: /lib\n"
        "data_dir: /data\n"
        "categories: [文学, 历史人文]\n"
        "hub_min_articles: 5\n",
        encoding="utf-8")
    c = config.load(tmp_path / "config.yaml")
    assert c.corpus_path == Path("/inbox")
    assert c.library_path == Path("/lib")
    assert c.categories == {"文学", "历史人文"}
    assert c.hub_min_articles == 5          # overridden
    assert c.topic_split_threshold == 40    # default preserved


def test_load_nfc_normalizes_categories(tmp_path):
    import unicodedata
    nfd = unicodedata.normalize("NFD", "café")
    (tmp_path / "c.yaml").write_text(
        f"corpus_path: /v\nlibrary_path: /v\ndata_dir: /d\n"
        f"categories: ['{nfd}']\n", encoding="utf-8")
    c = config.load(tmp_path / "c.yaml")
    assert unicodedata.normalize("NFC", "café") in c.categories


def test_localize_category_round_trips(tmp_path):
    (tmp_path / "c.yaml").write_text(
        "corpus_path: /v\nlibrary_path: /v\ndata_dir: /d\n"
        "categories: [Literature, History]\n"
        "category_localization:\n"
        "  Literature: {zh: 文学}\n"
        "  History: {zh: 历史人文}\n",
        encoding="utf-8")
    c = config.load(tmp_path / "c.yaml")
    # canonical language (en) returns the canonical name verbatim, no lookup
    assert c.localize_category("Literature", "en") == "Literature"
    # zh looks up the display map
    assert c.localize_category("Literature", "zh") == "文学"
    # unknown language or unmapped category falls back to the canonical name
    assert c.localize_category("Literature", "fr") == "Literature"
    assert c.localize_category("Unmapped", "zh") == "Unmapped"


def test_labeling_knob_defaults(cfg):
    assert cfg.agents_per_wave == 4
    assert cfg.articles_per_agent == 15
    assert cfg.extractor_version == "knowledge-library"


def test_wave_directory_properties(cfg):
    assert cfg.wave_assign_dir == cfg.data_dir / "wave_assign"
    assert cfg.wave_out_dir == cfg.data_dir / "wave_out"


def test_loader_reads_labeling_knobs(tmp_path):
    from librarian import config
    p = tmp_path / "config.yaml"
    p.write_text(
        "corpus_path: ./v\nlibrary_path: ./l\ndata_dir: ./d\n"
        "categories: [Literature]\n"
        "agents_per_wave: 6\narticles_per_agent: 20\n"
        "extractor_version: pilot-2026\n",
        encoding="utf-8")
    c = config.load(p)
    assert c.agents_per_wave == 6
    assert c.articles_per_agent == 20
    assert c.extractor_version == "pilot-2026"


def test_label_model_default(cfg):
    assert cfg.label_model == "sonnet"


def test_loader_reads_label_model(tmp_path):
    from librarian import config
    p = tmp_path / "config.yaml"
    p.write_text(
        "corpus_path: ./v\nlibrary_path: ./l\ndata_dir: ./d\n"
        "categories: [Literature]\nlabel_model: opus\n", encoding="utf-8")
    assert config.load(p).label_model == "opus"
