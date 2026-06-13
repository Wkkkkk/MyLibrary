"""Loads config.yaml into a Config dataclass, replacing every tunable constant
that the original schema.py used to hardcode. The fixed data contract lives in
contract.py, not here."""
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _nfc_set(values):
    return {unicodedata.normalize("NFC", v) for v in values}


@dataclass
class Config:
    corpus_path: Path                 # was schema.VAULT — the inbox / source vault
    library_path: Path                # the materialized output vault
    data_dir: Path                    # was schema.DATA — TSV state directory
    categories: set                   # was schema.CATEGORIES_V1 — primary canon
    hub_dir: str = "_topics"
    skip_dirs: set = field(
        default_factory=lambda: {"_images", "分类视图", "话题", "_topics"})
    generated_marker: str = "generated: knowledge-library"
    hub_min_articles: int = 3
    topic_split_threshold: int = 40
    batch_size: int = 30
    legacy_labels_name: str = "legacy_category_labels.tsv"
    # Labeling knobs (spec §4): the wave loop dispatches `agents_per_wave`
    # parallel agents, each handling `articles_per_agent` articles. The value
    # written to a label row's extractor_version column traces which run/version
    # produced it.
    agents_per_wave: int = 4
    articles_per_agent: int = 15
    extractor_version: str = "knowledge-library"
    # Language (spec §4b): the controlled vocabulary is canonical in
    # label_language; category_localization maps a canonical category name to
    # its display names per language, e.g. {"Literature": {"zh": "文学"}}.
    label_language: str = "en"
    category_localization: dict = field(default_factory=dict)

    def localize_category(self, canonical, lang):
        """The display name for a canonical category in `lang`. Returns the
        canonical name unchanged when lang is the canon language or no mapping
        exists (consumed by the language-aware materialize in Plan 2)."""
        if lang == self.label_language:
            return canonical
        return self.category_localization.get(canonical, {}).get(lang, canonical)

    @property
    def labels_path(self):
        return self.data_dir / "article_labels.tsv"

    @property
    def topics_path(self):
        return self.data_dir / "topics.tsv"

    @property
    def manifest_path(self):
        return self.data_dir / "manifest.tsv"

    @property
    def batches_dir(self):
        return self.data_dir / "batches"

    @property
    def wave_assign_dir(self):
        return self.data_dir / "wave_assign"

    @property
    def wave_out_dir(self):
        return self.data_dir / "wave_out"

    @property
    def progress_path(self):
        return self.data_dir / "progress.tsv"

    @property
    def migration_log_path(self):
        return self.data_dir / "migration_log.tsv"

    @property
    def runs_path(self):
        return self.data_dir / "runs.tsv"

    @property
    def legacy_labels(self):
        return self.data_dir / self.legacy_labels_name


def load(path):
    """Read a config.yaml file into a Config. Unknown keys are ignored; missing
    optional keys fall back to dataclass defaults."""
    raw = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8")) or {}
    kwargs = dict(
        corpus_path=Path(raw["corpus_path"]).expanduser(),
        library_path=Path(raw["library_path"]).expanduser(),
        data_dir=Path(raw["data_dir"]).expanduser(),
        categories=_nfc_set(raw.get("categories", [])),
    )
    for key in ("hub_dir", "generated_marker", "hub_min_articles",
                "topic_split_threshold", "batch_size", "legacy_labels_name",
                "label_language", "category_localization",
                "agents_per_wave", "articles_per_agent", "extractor_version"):
        if key in raw:
            kwargs[key] = raw[key]
    if "skip_dirs" in raw:
        kwargs["skip_dirs"] = _nfc_set(raw["skip_dirs"])
    return Config(**kwargs)
