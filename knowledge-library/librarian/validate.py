from librarian import tsv, contract

PATH_I = contract.LABEL_COLUMNS.index("relative_path")
PRIMARY_I = contract.LABEL_COLUMNS.index("primary_category")
TOPICS_I = contract.LABEL_COLUMNS.index("topics")
CONF_I = contract.LABEL_COLUMNS.index("confidence")
REVIEW_I = contract.LABEL_COLUMNS.index("needs_review")
PROPOSED_I = contract.LABEL_COLUMNS.index("proposed_topics")

PATH_UNSAFE = set("/\\:")


def check(rows, expected_paths, reg, categories):
    """Validate one batch's output rows. Returns (normalized_rows, errors).
    Rows are normalized in place: topic aliases resolved to canonical names."""
    errors = []
    expected = set(expected_paths)
    if len(rows) != len(expected_paths):
        errors.append(f"row count {len(rows)} != batch size {len(expected_paths)}")
    for i, r in enumerate(rows, start=1):
        tag = f"row {i}"
        if len(r) != len(contract.LABEL_COLUMNS):
            errors.append(f"{tag}: {len(r)} fields, want {len(contract.LABEL_COLUMNS)}")
            continue
        if r[PATH_I] not in expected:
            errors.append(f"{tag}: path not in batch manifest (fabricated?): {r[PATH_I]}")
        if r[PRIMARY_I] not in categories:
            hint = " (is a topic name, not a category)" if r[PRIMARY_I] in reg.active_names() else ""
            errors.append(f"{tag}: primary off canon: {r[PRIMARY_I]!r}{hint}")
        proposed = set(tsv.split_multi(r[PROPOSED_I]))
        topics = tsv.split_multi(r[TOPICS_I])
        for t in proposed - set(topics):
            if any(c in PATH_UNSAFE for c in t):
                errors.append(f"{tag}: topic {t!r} has a path-unsafe character (/ \\ :)")
        resolved = []
        for t in topics:
            if any(c in PATH_UNSAFE for c in t):
                errors.append(f"{tag}: topic {t!r} has a path-unsafe character (/ \\ :)")
            canon = reg.resolve(t)
            # active_names(), not resolve() is not None: a registry topic with
            # status `proposed` resolves to itself but must still be re-declared
            # in the row's proposed_topics column to be accepted.
            if canon and canon in reg.active_names():
                resolved.append(canon)
            elif t in proposed:
                resolved.append(t)
            else:
                errors.append(f"{tag}: topic {t!r} not in canon and not proposed")
        if not resolved:
            errors.append(f"{tag}: no topics")
        r[TOPICS_I] = tsv.join_multi(resolved)
        if r[CONF_I] not in contract.CONFIDENCE:
            errors.append(f"{tag}: confidence {r[CONF_I]!r}")
        if r[REVIEW_I] not in contract.BOOL:
            errors.append(f"{tag}: needs_review {r[REVIEW_I]!r}")
    seen = set()
    for i, r in enumerate(rows, start=1):
        if len(r) == len(contract.LABEL_COLUMNS):
            if r[PATH_I] in seen:
                errors.append(f"row {i}: duplicate path in batch: {r[PATH_I]}")
            seen.add(r[PATH_I])
    return rows, errors


def log_progress(log_path, batch_name, n_rows, n_review):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{batch_name}\tvalidated\t{n_rows}\t{n_review}\n")
