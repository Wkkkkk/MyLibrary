"""Generic adapter for a directory of Markdown files that already carry
frontmatter. Injects `source: <source_name>` when absent; everything else must
already satisfy the node contract (notably a stable `url` dedup key) or the node
is rejected by ingest_to_inbox."""
from pathlib import Path
from librarian.adapters import base


class MarkdownPassthroughAdapter(base.Adapter):
    def __init__(self, source_name):
        self.name = source_name

    def nodes(self, src_dir):
        for f in sorted(Path(src_dir).rglob("*.md")):
            text = f.read_text(encoding="utf-8")
            fm, _ = base.parse(text)
            if not fm.get("source"):
                text = base.set_field(text, "source", self.name)
            yield f.name, text
