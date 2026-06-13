import sys
from pathlib import Path

import pytest

# Put knowledge-library/ on sys.path so `import librarian` resolves when
# pytest is invoked from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from librarian import config  # noqa: E402


@pytest.fixture
def cfg(tmp_path):
    """A throwaway Config pointing at tmp_path. The default `cfg` for tests that
    only need config values (skip_dirs, thresholds, hub_dir, marker)."""
    return config.Config(
        corpus_path=tmp_path / "vault",
        library_path=tmp_path / "vault",
        data_dir=tmp_path / "data",
        categories={"文学", "历史人文", "AI与机器学习"},
    )
