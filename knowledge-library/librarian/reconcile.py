"""Reconcile label paths to the real 知乎收藏_v2 library locations.

The v2 library was built by the original full materialization, which re-filed
articles into <primary_category>/ folders and resolved basename collisions with
_N suffixes — a mapping recorded only in migration_log_newfolder.tsv. To let the
update --out <v2> flow describe v2 directly, each label's relative_path
is translated to its actual v2 location via that map.
"""


def translate(rows, migration_map):
    """Set each row's relative_path to its v2 location via migration_map; a path
    that is not a migration key (already at its v2 location) is left unchanged.
    Mutates rows in place and returns them."""
    for r in rows:
        r[0] = migration_map.get(r[0], r[0])
    return rows
