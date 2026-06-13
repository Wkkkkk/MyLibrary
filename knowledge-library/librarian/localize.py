"""Display localization for materialize (spec §4b layer 2). The controlled
vocabulary is English-canonical in the TSVs; these helpers render it into a
target display language at materialize time. Category display names come from
cfg.localize_category (Plan 1); topic display names come from the registry's
name_zh column; section headers are fixed per-language strings here."""

# Hub-note section headers per display language. `en` is the no-lookup default
# (the canon language); `zh` is the worked example (spec §4b keeps it to zh for
# now — YAGNI). Unknown languages fall back to English.
SECTION_HEADERS = {
    "en": {"reading_list": "Reading list", "related": "Related topics",
           "parent": "Parent topic", "children": "Subtopics"},
    "zh": {"reading_list": "阅读清单", "related": "相关话题",
           "parent": "父话题", "children": "子话题"},
}


def headers(lang):
    """The section-header strings for `lang`, falling back to English."""
    return SECTION_HEADERS.get(lang, SECTION_HEADERS["en"])


def topic_name(cfg, reg, name, lang):
    """The display name for a canonical topic in `lang`. Returns the canonical
    name unchanged when lang is the canon language, the topic is unknown, or it
    has no name_zh; otherwise the registry's name_zh value (TOPIC_COLUMNS[7])."""
    if lang == cfg.label_language:
        return name
    row = reg.by_name.get(name)
    if row is not None and len(row) > 7 and row[7]:
        return row[7]
    return name
