from librarian import tsv, contract


class Registry:
    def __init__(self, rows):
        self.rows = rows
        self.by_name = {}
        for r in rows:
            name, status = r[1], r[4]
            if status not in contract.TOPIC_STATUS:
                raise ValueError(f"{name}: bad status {status!r}")
            if name in self.by_name:
                raise ValueError(f"duplicate topic name: {name}")
            self.by_name[name] = r
        alias_map = {}
        for r in rows:
            name = r[1]
            for a in tsv.split_multi(r[2]):
                # An alias may shadow a *merged* topic's name (redirect),
                # but not an active/proposed name or another alias.
                named = self.by_name.get(a)
                if a in alias_map or (named is not None and named[4] != "merged"):
                    raise ValueError(f"duplicate alias: {a}")
                alias_map[a] = name
        self.alias_map = alias_map
        for r in rows:
            name, parent = r[1], r[3]
            if parent and parent not in self.by_name:
                raise ValueError(f"{name}: unknown parent {parent!r}")
        for r in rows:
            seen, cur = set(), r[1]
            while cur:
                if cur in seen:
                    raise ValueError(f"parent cycle at {cur}")
                seen.add(cur)
                cur = self.by_name[cur][3]

    def resolve(self, name):
        """Resolve a name or alias to a canonical topic name: alias mapping
        wins; active/proposed names resolve to themselves; a merged name with
        no alias redirect resolves to None."""
        if name in self.alias_map:
            return self.alias_map[name]
        r = self.by_name.get(name)
        if r is not None and r[4] != "merged":
            return name
        return None

    def active_names(self):
        return {r[1] for r in self.rows if r[4] == "active"}


def load(path):
    _, rows = tsv.read_rows(path, contract.TOPIC_COLUMNS)
    return Registry(rows)


def load_or_empty(path):
    """Like load(), but a missing topics.tsv yields an empty Registry. During
    bootstrap the canon does not exist until the first proposals are accepted,
    so the wave-builder/ingest/audit paths must tolerate its absence."""
    return load(path) if path.exists() else Registry([])
