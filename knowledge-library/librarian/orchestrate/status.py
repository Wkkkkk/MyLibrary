"""Render the on-demand library status (spec §9): library size + canon size,
last run, pending queues, run history. Reads the ledger, labels store, registry,
and the audit queues — never mutates."""
from librarian import store, registry, audit, ledger, contract


def render(cfg):
    rows = store.load(cfg.labels_path)
    reg = registry.load_or_empty(cfg.topics_path)
    rep = audit.report(rows, cfg, reg=reg)
    i = contract.RUN_COLUMNS.index
    runs = ledger.load(cfg.runs_path)          # single read; latest = last row
    last = runs[-1] if runs else None
    lines = [f"Library: {len(rows)} articles · canon {len(reg.active_names())} topics"]

    if last is None:
        lines.append("Last run: never")
    else:
        lines.append(
            f"Last run: {last[i('finished_at')]}  "
            f"+{last[i('new')]} new, {last[i('flagged')]} flagged   "
            f"[{last[i('status')]}]")

    lines.append(
        f"Pending: {len(rep['proposals'])} proposed topics · "
        f"{rep['review_open']} needs-review")

    if runs:
        auth = [r for r in runs if r[i('status')] == "auth_failed"]
        last_auth = auth[-1][i('finished_at')] if auth else "never"
        lines.append(
            f"History: {len(runs)} runs since {runs[0][i('started_at')]} "
            f"(last auth_failed: {last_auth})")
    else:
        lines.append("History: 0 runs")
    return "\n".join(lines)
