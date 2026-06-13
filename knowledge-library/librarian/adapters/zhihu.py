"""Lead adapter (spec §6): the zhihu-fetcher producer already emits the node
contract verbatim (title / source: zhihu / url / interaction_time frontmatter),
so this adapter only reads the producer's output directory and passes each
article through unchanged. The fetcher is opaque — referenced, never forked."""
from pathlib import Path
from librarian.adapters import base


class ZhihuAdapter(base.Adapter):
    name = "zhihu"

    def nodes(self, src_dir):
        for f in sorted(Path(src_dir).glob("*.md")):
            yield f.name, f.read_text(encoding="utf-8")
