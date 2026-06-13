"""Tests for reconciling label paths to the real v2 library locations."""
from librarian import reconcile, contract


def _row(rel):
    r = [""] * len(contract.LABEL_COLUMNS)
    r[0] = rel
    return r


def test_translate_maps_via_migration_else_keeps_path():
    rows = [_row("AI与人工智能/a.md"), _row("文学/b.md")]
    mp = {"AI与人工智能/a.md": "效率与工具/a.md"}  # moved during the v2 build
    out = reconcile.translate(rows, mp)
    assert [r[0] for r in out] == ["效率与工具/a.md", "文学/b.md"]


def test_translate_is_idempotent_on_already_v2_paths():
    rows = [_row("效率与工具/a.md")]
    mp = {"AI与人工智能/a.md": "效率与工具/a.md"}
    # a path that is already the v2 target is not a migration key -> unchanged
    out = reconcile.translate(rows, mp)
    assert [r[0] for r in out] == ["效率与工具/a.md"]
