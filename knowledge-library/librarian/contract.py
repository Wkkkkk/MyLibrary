"""The fixed data contract: TSV column schemas and value enums. Unlike the
environmental values in config.py, these define the normalized-node / label
record shape and are not user-tunable."""

MANIFEST_COLUMNS = ["relative_path", "title", "folder", "content_hash"]

# name_zh is appended LAST: registry.py and proposals.py read topic rows
# positionally (r[1]=name … r[6]=created_at), so appending leaves them intact.
# It carries the Chinese display name beside the canonical English `name`
# (spec §4b); unused until the language-aware materialize in Plan 2.
TOPIC_COLUMNS = ["topic_id", "name", "aliases", "parent_topic", "status",
                 "description", "created_at", "name_zh"]

# first_seen_run is APPENDED last (spec §9): it traces an article to the run
# that introduced it. Appended so store/validate/verify/ingest_wave positional
# reads (r[0]..r[14]) are unchanged — same discipline as TOPIC_COLUMNS.name_zh.
LABEL_COLUMNS = ["relative_path", "title", "original_category",
                 "primary_category", "topics", "tags", "article_type",
                 "summary", "confidence", "needs_review", "review_reason",
                 "proposed_topics", "content_hash", "extractor_version",
                 "labeled_at", "first_seen_run"]

CONFIDENCE = {"high", "medium", "low"}
BOOL = {"true", "false"}
TOPIC_STATUS = {"active", "proposed", "merged"}
