import os
import unicodedata


def _resolve_name(target_basename, existing_names):
    """Return the member of `existing_names` whose NFC form equals the NFC
    form of `target_basename`, else None. Tolerates NFC/NFD drift between a
    TSV-derived name and the actual on-disk entry (APFS stores either form)."""
    target_nfc = unicodedata.normalize("NFC", target_basename)
    for name in existing_names:
        if unicodedata.normalize("NFC", name) == target_nfc:
            return name
    return None


def plan(label_rows, vault):
    taken = set()
    for r in label_rows:  # pass 1: in-place rows claim their names first
        base = r[0].rsplit("/", 1)[-1]
        if r[0] == f"{r[3]}/{base}":
            taken.add(r[0])
    # seed `taken` with the actual on-disk contents of every target folder so a
    # pre-existing file NOT in label_rows can never be clobbered by a mover.
    # A mover's own source file vacates its slot, so it must not block itself:
    # exclude every row's current path (NFC) from the seeded set.
    own = {unicodedata.normalize("NFC", r[0]) for r in label_rows}
    for category in {r[3] for r in label_rows}:
        folder = vault / category
        if folder.exists():
            for entry in os.listdir(folder):
                rel = f"{category}/{unicodedata.normalize('NFC', entry)}"
                if rel not in own:
                    taken.add(rel)
    moves = []
    for r in label_rows:
        base = r[0].rsplit("/", 1)[-1]
        stem, ext = os.path.splitext(base)
        new_rel = f"{r[3]}/{base}"
        if r[0] == new_rel:
            continue
        n = 2
        while new_rel in taken:
            new_rel = f"{r[3]}/{stem}_{n}{ext}"
            n += 1
        taken.add(new_rel)
        moves.append((r[0], new_rel, r))
    return moves


def apply(moves, vault):
    """Execute the planned moves via a two-phase (stage-to-temp, then finalize)
    rename so name-swaps between folders are safe.

    NOTE: the caller MUST persist the returned log to disk for recovery; this
    function does not write a journal itself.
    """
    for _, new_rel, _ in moves:
        (vault / new_rel).parent.mkdir(parents=True, exist_ok=True)
    for old_rel, new_rel, _ in moves:  # phase A: stage to temp names
        # resolve the real on-disk source tolerant of NFC/NFD drift
        parent = (vault / old_rel).parent
        base = old_rel.rsplit("/", 1)[-1]
        src = vault / old_rel
        if not src.exists() and parent.exists():
            match = _resolve_name(base, os.listdir(parent))
            if match is not None:
                src = parent / match
        tmp = vault / (new_rel + ".__mv")
        if src.exists():
            os.rename(src, tmp)
        else:
            assert tmp.exists() or (vault / new_rel).exists(), (old_rel, new_rel)
    log = []
    for old_rel, new_rel, r in moves:  # phase B: finalize
        tmp, dst = vault / (new_rel + ".__mv"), vault / new_rel
        if tmp.exists():
            assert not dst.exists(), (old_rel, new_rel)
            os.rename(tmp, dst)
        assert dst.exists(), (old_rel, new_rel)
        r[0] = new_rel
        log.append((old_rel, new_rel))
    return log
