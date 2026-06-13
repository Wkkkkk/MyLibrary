from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:  # stub, fully defined in Task 2
    corpus_path: Path
    library_path: Path
    data_dir: Path
    categories: set = field(default_factory=set)
