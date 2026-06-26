import re
from datetime import datetime

from librarian import tsv

# A bare calendar date with no time component (e.g. "2026-06-23").
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _interaction_time(val):
    """Value to inject as interaction_time, derived from collected_at.

    Obsidian Bases sorts the `_view.base` "按互动时间" table on interaction_time
    as a *datetime*; a bare date (no time component) is a type mismatch and the
    row drops out of that view. Local/storm sources often supply only a date, so
    promote a date-only value to 09:00 local time (keeping the host's UTC offset)
    so it sorts as a datetime. Values that already carry a time component — or
    that aren't a plain date — pass through unchanged.
    """
    if not _DATE_ONLY.match(val):
        return val
    try:
        dt = datetime.strptime(val, "%Y-%m-%d").replace(hour=9)
    except ValueError:
        return val
    return dt.astimezone().isoformat()

# `category` is managed (stripped): the source `category:` is a now-redundant
# duplicate of the canonical primary_category (its value is preserved as
# original_category in the label TSV), so it must not linger in materialized
# frontmatter (finding #3).
MANAGED = ("tags", "primary_category", "topics", "summary", "label_confidence",
           "category")

# Closing frontmatter fence: a line that is exactly '---' (optional trailing
# whitespace). Must NOT match dashes inside a multi-line quoted title such as
# a continuation line "------大总结" — matching those splits the frontmatter.
_FENCE = re.compile(r"\n---[ \t]*(?:\n|$)")


def _yq(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tagify(v):
    v = v.replace("C++", "Cpp").replace("c++", "cpp").replace("C#", "CSharp")
    v = re.sub(r"[^\w/À-￿-]+", "-", v)
    return re.sub(r"-{2,}", "-", v).strip("-")


def _block(row):
    tags = []
    for v in tsv.split_multi(row[5]):
        t = _tagify(v)
        if t and t not in tags:
            tags.append(t)
    return (["tags:"] + [f"  - {t}" for t in tags] + [
        f"primary_category: {_yq(row[3])}",
        f"topics: {_yq(row[4])}",
        f"summary: {_yq(row[7])}",
        f"label_confidence: {_yq(row[8])}",
    ])


def apply(path, row):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return "no-frontmatter"
    m = _FENCE.search(text, 4)
    if not m:
        return "no-frontmatter"
    end = m.start()
    head, rest = text[4:end], text[end:]
    kept, skipping = [], False
    for ln in head.split("\n"):
        if ln[:1] in (" ", "\t", "-") or ":" not in ln:
            if not skipping:
                kept.append(ln)
            continue
        skipping = ln.split(":")[0].strip() in MANAGED
        if not skipping:
            kept.append(ln)
    while kept and kept[-1] == "":
        kept.pop()
    if not any(":" in ln and ln.split(":")[0].strip() == "interaction_time" for ln in kept):
        new_kept = []
        for ln in kept:
            new_kept.append(ln)
            if ":" in ln and ln.split(":")[0].strip() == "collected_at":
                val = ln.split(":", 1)[1].strip().strip("'\"")
                new_kept.append(f"interaction_time: {_interaction_time(val)}")
        kept = new_kept
    new = "---\n" + "\n".join(kept + _block(row)) + rest
    if new != text:
        path.write_text(new, encoding="utf-8")
        return "written"
    return "unchanged"
