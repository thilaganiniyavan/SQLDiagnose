# spider.py
# Loading the Spider benchmark (queries + real SQLite databases).

import json
import zipfile
from pathlib import Path
from typing import Dict, List

from analysis.schema import DatabaseSchema

SPIDER_URL = "https://huggingface.co/datasets/HAL-9001/spider-databases/resolve/main/spider_data.zip"
DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "spider_data"


def download_spider(raw_dir: Path) -> Path:
    """Downloads and extracts Spider 1.0 (queries, tables.json and the SQLite databases)."""
    import urllib.request

    raw_dir.mkdir(parents=True, exist_ok=True)
    root = raw_dir / "spider_data"
    if (root / "tables.json").exists():
        return root
    zip_path = raw_dir / "spider_data.zip"
    if not zip_path.exists():
        print(f"Downloading Spider from {SPIDER_URL} ...")
        urllib.request.urlretrieve(SPIDER_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(raw_dir)
    return root


class SpiderCorpus:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = Path(root)
        if not (self.root / "tables.json").exists():
            raise FileNotFoundError(
                f"Spider not found under {self.root}. Run `python -m data_pipeline.build_dataset --download`.")
        self._tables = {e["db_id"]: e for e in json.loads((self.root / "tables.json").read_text())}
        self._schemas: Dict[str, DatabaseSchema] = {}

    def db_path(self, db_id: str) -> Path:
        return self.root / "database" / db_id / f"{db_id}.sqlite"

    def schema(self, db_id: str) -> DatabaseSchema:
        """Schema read from the real SQLite file (declared types), falling back to tables.json."""
        if db_id not in self._schemas:
            path = self.db_path(db_id)
            if path.exists():
                self._schemas[db_id] = DatabaseSchema.from_sqlite(str(path), db_id)
            else:
                self._schemas[db_id] = DatabaseSchema.from_spider(self._tables[db_id])
        return self._schemas[db_id]

    def db_ids(self) -> List[str]:
        return sorted(self._tables)

    def examples(self, split: str) -> List[Dict]:
        """split: 'train' (train_spider.json) or 'dev' (dev.json)."""
        name = {"train": "train_spider.json", "dev": "dev.json"}[split]
        return json.loads((self.root / name).read_text())
