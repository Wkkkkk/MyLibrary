import hashlib
import re
import unicodedata
from librarian import contract


def _title(text, fallback):
    m = re.search(r"(?m)^title:\s*\"?(.+?)\"?\s*$", text[:2000])
    return m.group(1) if m else fallback


def read_url(path):
    """The article's stable zhihu `url` from frontmatter, or None. Used as the
    cross-vault identity (survives re-fetch + frontmatter rewrite, unlike a
    content hash)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return None
    m = re.search(r"(?m)^url:\s*\"?(.+?)\"?\s*$", text[:2000])
    return m.group(1) if m else None


def build(vault, cfg):
    rows = []
    for d in sorted(p for p in vault.iterdir() if p.is_dir()):
        if d.name in cfg.skip_dirs:
            continue
        for f in sorted(d.glob("*.md")):
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                raise ValueError(f"{f}: not valid UTF-8: {e}") from e
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
            rel = unicodedata.normalize("NFC", f"{d.name}/{f.name}")
            title = unicodedata.normalize("NFC", _title(text, f.stem))
            rows.append([rel, title, d.name, h])
    return rows


def diff(old_rows, new_rows):
    path_i = contract.MANIFEST_COLUMNS.index("relative_path")
    hash_i = contract.MANIFEST_COLUMNS.index("content_hash")
    old = {r[path_i]: r[hash_i] for r in old_rows}
    new = {r[path_i]: r[hash_i] for r in new_rows}
    added = sorted(p for p in new if p not in old)
    changed = sorted(p for p in new if p in old and new[p] != old[p])
    deleted = sorted(p for p in old if p not in new)
    return added, changed, deleted
