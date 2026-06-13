from librarian import tsv, contract


def load(path):
    if not path.exists():
        return []
    _header, rows = tsv.read_rows(path, contract.LABEL_COLUMNS)
    return rows


def _save(path, rows):
    tsv.write_rows(path, contract.LABEL_COLUMNS, sorted(rows, key=lambda r: r[0]))


def merge(path, new_rows):
    rows = {r[0]: r for r in load(path)}
    for r in new_rows:
        rows[r[0]] = r
    _save(path, list(rows.values()))


def delete(path, paths_to_remove):
    gone = set(paths_to_remove)
    _save(path, [r for r in load(path) if r[0] not in gone])
