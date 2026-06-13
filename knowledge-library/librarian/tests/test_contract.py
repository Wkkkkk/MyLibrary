from librarian import contract


def test_label_columns_complete_and_ordered():
    assert contract.LABEL_COLUMNS[0] == "relative_path"
    # first_seen_run is APPENDED last (spec §9 provenance) so positional reads
    # r[0]..r[14] in store/validate/verify/ingest_wave stay unchanged; labeled_at
    # is now second-to-last.
    assert contract.LABEL_COLUMNS[-2] == "labeled_at"
    assert contract.LABEL_COLUMNS[-1] == "first_seen_run"
    assert len(contract.LABEL_COLUMNS) == 16
    assert len(set(contract.LABEL_COLUMNS)) == 16


def test_manifest_and_topic_columns():
    assert contract.MANIFEST_COLUMNS == [
        "relative_path", "title", "folder", "content_hash"]
    # name_zh is APPENDED last so registry/proposals positional reads (r[1]..r[6])
    # are unchanged; it holds the Chinese display name for the canonical English name.
    assert contract.TOPIC_COLUMNS == [
        "topic_id", "name", "aliases", "parent_topic", "status",
        "description", "created_at", "name_zh"]
    assert contract.TOPIC_COLUMNS[-1] == "name_zh"


def test_enums():
    assert contract.CONFIDENCE == {"high", "medium", "low"}
    assert contract.BOOL == {"true", "false"}
    assert contract.TOPIC_STATUS == {"active", "proposed", "merged"}
