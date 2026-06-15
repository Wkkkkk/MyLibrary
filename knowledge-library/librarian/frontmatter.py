import re
from librarian import tsv

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
    new = "---\n" + "\n".join(kept + _block(row)) + rest
    if new != text:
        path.write_text(new, encoding="utf-8")
        return "written"
    return "unchanged"
