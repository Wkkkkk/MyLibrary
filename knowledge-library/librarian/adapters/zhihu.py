"""Lead adapter (spec §6): the zhihu-fetcher producer already emits the node
contract verbatim (title / source: zhihu / url / interaction_time frontmatter),
so this adapter only reads the producer's output directory and passes each
article through unchanged. The fetcher is opaque — referenced, never forked."""
from pathlib import Path
from librarian.adapters import base


class ZhihuAdapter(base.Adapter):
    name = "zhihu"

    def nodes(self, src_dir):
        # rglob, not glob: the fetcher emits a flat directory, but an
        # organized/exported corpus nests articles under category folders
        # (finding #1). ingest_to_inbox dedups by url + resolves name collisions.
        for f in sorted(Path(src_dir).rglob("*.md")):
            yield f.name, f.read_text(encoding="utf-8")
