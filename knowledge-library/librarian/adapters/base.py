"""The normalized-node contract (spec §4): every source unit, whatever its
origin, becomes one Markdown file whose frontmatter carries the fields below.
An adapter's only job is to yield (filename, text) pairs already in this shape;
`ingest_to_inbox` validates each and writes the survivors into the inbox
(cfg.corpus_path). A node that violates the contract is rejected, never written.
"""
import re
import unicodedata
from pathlib import Path

# Stable identity + provenance the rest of the toolkit relies on. `url` is the
# dedup key (manifest.read_url) — language-neutral and surviving re-fetch +
# frontmatter rewrite, unlike a content hash (spec §4).
REQUIRED_FIELDS = ("title", "source", "url")

# Closing frontmatter fence: a line that is exactly '---' (optional trailing
# whitespace) — NOT dashes inside a multi-line quoted title (lessons §8 fence
# bug). Mirrors frontmatter._FENCE.
_FENCE = re.compile(r"\n---[ \t]*(?:\n|$)")
_KV = re.compile(r'(?m)^([A-Za-z0-9_]+):[ \t]*"?(.*?)"?[ \t]*$')


def parse(text):
    """Split a node Markdown string into (frontmatter: dict, body: str).
    Frontmatter is the block between the leading `---\\n` and the next bare
    `---` line; returns ({}, text) when absent. Only flat scalar `key: value`
    pairs are read (the contract fields are all scalars)."""
    if not text.startswith("---\n"):
        return {}, text
    m = _FENCE.search(text, 4)
    if not m:
        return {}, text
    head = text[4:m.start()]
    body = text[m.end():]
    fm = {km.group(1): km.group(2) for km in _KV.finditer(head)}
    return fm, body


def validate(frontmatter, body):
    """Return a list of contract-violation messages; [] means a valid node."""
    errors = []
    for f in REQUIRED_FIELDS:
        if not str(frontmatter.get(f, "")).strip():
            errors.append(f"missing required field: {f}")
    if not body.strip():
        errors.append("empty body")
    return errors


def set_field(text, key, value):
    """Insert or replace a scalar frontmatter `key: "value"` line, fence-safe.
    Returns text unchanged if it has no leading `---\\n` frontmatter block."""
    if not text.startswith("---\n"):
        return text
    m = _FENCE.search(text, 4)
    if not m:
        return text
    head, rest = text[4:m.start()], text[m.start():]
    line = f'{key}: "{value}"'
    lines = head.split("\n")
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:[ \t]", ln):
            lines[i] = line
            break
    else:
        lines.append(line)
    return "---\n" + "\n".join(lines) + rest


class Adapter:
    """Base class. A concrete adapter sets `name` and implements `nodes`. The
    `name` doubles as the inbox subfolder the adapter's nodes land in."""
    name = "base"

    def nodes(self, src_dir):
        """Yield (filename, text) per source unit, where text is a full node
        Markdown string and filename is the bare destination file name."""
        raise NotImplementedError


def ingest_to_inbox(adapter, src_dir, cfg):
    """Walk an adapter's nodes, validate each against the contract, and write
    the valid, not-yet-seen ones into cfg.corpus_path/<adapter.name>/ verbatim
    (NFC-normalized). Dedup is by the `url` frontmatter key across the whole
    inbox (idempotent re-runs). A same-name/different-url collision appends _N
    rather than overwriting (lessons §8). Returns
    (written: list[str], rejected: list[(filename, errors)], skipped: list[str]).
    """
    from librarian import manifest
    inbox = Path(cfg.corpus_path)
    dest_dir = inbox / adapter.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen_urls = {u for u in (manifest.read_url(p) for p in inbox.rglob("*.md")) if u}
    taken = {p.name for p in dest_dir.glob("*.md")}
    written, rejected, skipped = [], [], []
    for filename, text in adapter.nodes(src_dir):
        fm, body = parse(text)
        errs = validate(fm, body)
        if errs:
            rejected.append((filename, errs))
            continue
        url = fm["url"]
        if url in seen_urls:
            skipped.append(filename)
            continue
        seen_urls.add(url)
        dest = unicodedata.normalize("NFC", filename)
        stem = dest[:-3] if dest.endswith(".md") else dest
        n = 2
        while dest in taken:
            dest = f"{stem}_{n}.md"
            n += 1
        taken.add(dest)
        (dest_dir / dest).write_text(unicodedata.normalize("NFC", text), encoding="utf-8")
        written.append(f"{adapter.name}/{dest}")
    return written, rejected, skipped
