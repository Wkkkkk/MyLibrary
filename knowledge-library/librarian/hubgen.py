import json
from collections import defaultdict
from librarian import tsv, cooccur, localize


def plan(label_rows, reg, vault, cfg, lang="en"):
    def disp(name):
        return localize.topic_name(cfg, reg, name, lang)
    h = localize.headers(lang)
    by_topic = defaultdict(list)
    for r in label_rows:
        for t in tsv.split_multi(r[4]):
            by_topic[t].append(r)
    w = cooccur.weights(label_rows)
    children = defaultdict(list)
    for row in reg.rows:
        if row[3]:
            children[row[3]].append(row[1])
    plans = []
    for topic in sorted(by_topic):
        arts = by_topic[topic]
        if len(arts) < cfg.hub_min_articles or topic not in reg.active_names():
            continue
        row = reg.by_name[topic]
        parent, desc = row[3], row[5]
        lines = ["---", cfg.generated_marker, f"articles: {len(arts)}"]
        aliases = tsv.split_multi(row[2])
        if aliases:
            joined = ", ".join(json.dumps(a, ensure_ascii=False) for a in aliases)
            lines.append(f"aliases: [{joined}]")
        lines += ["---", "", f"# {disp(topic)}", ""]
        if desc:
            lines += [desc, ""]
        if parent:
            lines += [f"{h['parent']}: [[{disp(parent)}]]", ""]
        if children.get(topic):
            lines += [f"{h['children']}: " +
                      " · ".join(f"[[{disp(c)}]]" for c in sorted(children[topic])), ""]
        lines += [f"## {h['reading_list']} ({len(arts)})", ""]
        for r in sorted(arts, key=lambda r: r[0]):
            note = r[0].rsplit("/", 1)[-1][:-3]
            lines.append(f"- [[{note}]] — {r[7]}")
        rel = cooccur.related(w, topic, k=8)
        if rel:
            lines += ["", f"## {h['related']}", ""]
            lines.append(" · ".join(f"[[{disp(t)}]] ({n})" for t, n in rel))
        plans.append((vault / cfg.hub_dir / f"{disp(topic)}.md", "\n".join(lines) + "\n"))
    return plans


def apply(plans, vault, cfg):
    (vault / cfg.hub_dir).mkdir(parents=True, exist_ok=True)
    skipped = []
    for path, text in plans:
        if path.exists() and cfg.generated_marker not in path.read_text(encoding="utf-8"):
            skipped.append(path.name)
            continue
        path.write_text(text, encoding="utf-8")
    return skipped
