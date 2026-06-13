"""Append-only run ledger (spec §9): one row per run in data/runs.tsv — the
human-facing answer to 'what did this run pull'. It sits above the fetcher
history + manifest dedup (which prevent re-download / re-label); the §7 digest
renders the latest row. The actual writing of rows during a run is the
steady-state orchestrator's job (deferred); this module is the primitive."""
from librarian import tsv, contract


def load(path):
    """All run rows in append order, or [] when the ledger does not exist yet."""
    if not path.exists():
        return []
    _header, rows = tsv.read_rows(path, contract.RUN_COLUMNS)
    return rows


def append(path, row):
    """Append one run row to the ledger (creating it with a header if absent).
    Raises ValueError on a wrong-width row. Returns all rows after the append."""
    if len(row) != len(contract.RUN_COLUMNS):
        raise ValueError(
            f"run row width {len(row)} != {len(contract.RUN_COLUMNS)}")
    rows = load(path) + [row]
    tsv.write_rows(path, contract.RUN_COLUMNS, rows)
    return rows


def latest(path):
    """The most recently appended run row, or None when the ledger is empty."""
    rows = load(path)
    return rows[-1] if rows else None


def digest(row):
    """The one-line steady-state digest (spec §7): 'N new · M proposed · K flagged'."""
    i = contract.RUN_COLUMNS.index
    return (f"{row[i('new')]} new · {row[i('proposed_topics')]} proposed · "
            f"{row[i('flagged')]} flagged")
